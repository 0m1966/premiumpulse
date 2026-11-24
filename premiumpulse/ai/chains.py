"""Stateless LangChain LCEL chains for safe quote explanation and Q&A.

Follows strict LCEL pattern: ChatPromptTemplate | llm | output_parser.
Zero agents, zero tool execution, zero memory loops.
"""

import sqlite3
import time
from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from premiumpulse.ai.facts import (
    FactsPayload,
    build_coaching_facts,
    build_quote_facts,
)
from premiumpulse.ai.guardrails import (
    GuardrailError,
    build_deterministic_fallback,
    sanitize_user_question,
    validate_driver_id,
    verify_banned_content,
    verify_citations,
    verify_number_grounding,
)
from premiumpulse.ai.guideline_retriever import GuidelineRetriever
from premiumpulse.ai.output_schemas import (
    CoachingTips,
    GuidelineAnswer,
    QuoteExplanation,
)
from premiumpulse.ai.prompts import (
    COACHING_TIPS_SYSTEM_PROMPT,
    GUIDELINE_QA_SYSTEM_PROMPT,
    PROMPT_VERSION,
    QUOTE_EXPLAINER_SYSTEM_PROMPT,
)
from premiumpulse.config.settings import get_settings
from premiumpulse.domain.models import DriverQuote, DriverRiskScore


def get_default_llm() -> BaseChatModel:
    """Initialize default Groq Chat LLM if API key is present."""
    settings = get_settings()
    if settings.is_groq_configured:
        try:
            from langchain_groq import ChatGroq

            return ChatGroq(
                api_key=settings.GROQ_API_KEY,
                model_name=settings.GROQ_MODEL,
                temperature=0.0,
                max_tokens=400,
                timeout=15.0,
                max_retries=1,
            )
        except Exception:
            pass

    # Fallback fake model for zero-credentials mode
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    return FakeListChatModel(responses=[
        '{"summary": "Driver achieved 85.0 points in Band A with a monthly quote of $42.75.", "top_drivers_of_price": [{"factor_name": "Band A", "impact_description": "Clean driving discount", "cited_fact_id": "F3"}], "cited_fact_ids": ["F1", "F2", "F3"]}'
    ])


def log_ai_audit(driver_id: str, facts_hash: str, guardrail_result: str, latency_ms: float) -> None:
    """Log non-PII audit record of the AI execution."""
    try:
        from premiumpulse.db.snapshot_client import SNAPSHOT_DB_PATH

        if SNAPSHOT_DB_PATH.exists():
            with sqlite3.connect(SNAPSHOT_DB_PATH, timeout=4.0) as conn:
                conn.execute(
                    """
                    INSERT INTO ai_audit (driver_id, prompt_version, facts_hash, guardrail_result, latency_ms, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'));
                    """,
                    (driver_id, PROMPT_VERSION, facts_hash, guardrail_result, latency_ms),
                )
    except Exception:
        pass


class AIExplanationService:
    """Service orchestrating prompt assembly, chain invocation, and machine verification."""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_default_llm()
        self.retriever = GuidelineRetriever()

    def explain_quote(
        self,
        quote: DriverQuote,
        score: DriverRiskScore | None = None,
    ) -> dict[str, Any]:
        """Generate verified, grounded explanation of driver's quote."""
        start_ts = time.perf_counter()
        driver_id = validate_driver_id(quote.driver_id)
        facts = build_quote_facts(quote, score)

        # Build prompt
        parser = PydanticOutputParser(pydantic_object=QuoteExplanation)
        prompt = ChatPromptTemplate.from_messages([
            ("system", QUOTE_EXPLAINER_SYSTEM_PROMPT.format(prompt_version=PROMPT_VERSION)),
            ("human", (
                "<facts>\n{facts_text}\n</facts>\n\n"
                "Please explain the quote adhering strictly to the schema:\n{format_instructions}"
            )),
        ])

        chain = prompt | self.llm | parser

        facts_text = "\n".join(f"[{f.fact_id}] {f.fact_key}: {f.display_str}" for f in facts.facts)
        allowed_fact_ids = {f.fact_id for f in facts.facts}

        try:
            # Single-pass chain call
            result: QuoteExplanation = chain.invoke({
                "facts_text": facts_text,
                "format_instructions": parser.get_format_instructions(),
            })

            # Machine Verification Guardrails
            verify_number_grounding(result.summary, facts)
            verify_citations(result.cited_fact_ids, allowed_fact_ids)
            verify_banned_content(result.summary)

            latency = round((time.perf_counter() - start_ts) * 1000, 2)
            log_ai_audit(driver_id, facts.facts_hash, "PASS", latency)

            return {
                "summary": result.summary,
                "top_drivers_of_price": [d.model_dump() for d in result.top_drivers_of_price],
                "cited_fact_ids": result.cited_fact_ids,
                "fallback_used": False,
                "latency_ms": latency,
            }

        except Exception as exc:
            # Fall back safely on ANY parsing or guardrail rejection
            latency = round((time.perf_counter() - start_ts) * 1000, 2)
            log_ai_audit(driver_id, facts.facts_hash, f"FALLBACK ({exc})", latency)
            fallback = build_deterministic_fallback(facts)
            fallback["latency_ms"] = latency
            return fallback

    def get_coaching_tips(self, quote: DriverQuote, score: DriverRiskScore) -> dict[str, Any]:
        """Generate 3 verified coaching tips for driver."""
        start_ts = time.perf_counter()
        driver_id = validate_driver_id(quote.driver_id)
        facts = build_coaching_facts(score, quote)

        parser = PydanticOutputParser(pydantic_object=CoachingTips)
        prompt = ChatPromptTemplate.from_messages([
            ("system", COACHING_TIPS_SYSTEM_PROMPT.format(prompt_version=PROMPT_VERSION)),
            ("human", (
                "<facts>\n{facts_text}\n</facts>\n\n"
                "Provide coaching tips adhering strictly to the schema:\n{format_instructions}"
            )),
        ])

        chain = prompt | self.llm | parser
        facts_text = "\n".join(f"[{f.fact_id}] {f.fact_key}: {f.display_str}" for f in facts.facts)
        allowed_fact_ids = {f.fact_id for f in facts.facts}

        try:
            result: CoachingTips = chain.invoke({
                "facts_text": facts_text,
                "format_instructions": parser.get_format_instructions(),
            })

            # Verify grounding
            for tip in result.tips:
                verify_number_grounding(tip.advice, facts)
            verify_citations(result.cited_fact_ids, allowed_fact_ids)

            latency = round((time.perf_counter() - start_ts) * 1000, 2)
            log_ai_audit(driver_id, facts.facts_hash, "PASS", latency)

            return {
                "tips": [t.model_dump() for t in result.tips],
                "cited_fact_ids": result.cited_fact_ids,
                "fallback_used": False,
                "latency_ms": latency,
            }
        except Exception as exc:
            latency = round((time.perf_counter() - start_ts) * 1000, 2)
            log_ai_audit(driver_id, facts.facts_hash, f"FALLBACK ({exc})", latency)
            # Deterministic fallback tips
            return {
                "tips": [
                    {"factor": "Braking", "advice": "Anticipate stops early to reduce hard deceleration events.", "estimated_points_gain_fact_id": "F4"},
                    {"factor": "Speeding", "advice": "Keep within the posted speed limit to maximize risk band discount.", "estimated_points_gain_fact_id": "F6"},
                    {"factor": "Phone Use", "advice": "Use hands-free mounts and avoid screen touches while in motion.", "estimated_points_gain_fact_id": "F8"},
                ],
                "cited_fact_ids": ["F4", "F6", "F8"],
                "fallback_used": True,
                "notice": "AI tips unavailable; standard coaching advice shown.",
                "latency_ms": latency,
            }

    def ask_guidelines(self, question: str) -> dict[str, Any]:
        """Answer question grounded strictly in underwriting guidelines."""
        start_ts = time.perf_counter()

        try:
            clean_q = sanitize_user_question(question)
        except GuardrailError as ge:
            return {
                "answer": "This is not covered by the underwriting guidelines.",
                "cited_clause_ids": [],
                "answerable": False,
                "fallback_used": True,
                "error": str(ge),
                "latency_ms": round((time.perf_counter() - start_ts) * 1000, 2),
            }

        # Retrieve relevant clauses
        clauses = self.retriever.retrieve(clean_q, top_k=3, min_score=0.04)

        # If no clause matches above threshold, return answerable=false WITHOUT LLM call
        if not clauses:
            return {
                "answer": "This is not covered by the underwriting guidelines.",
                "cited_clause_ids": [],
                "answerable": False,
                "fallback_used": False,
                "latency_ms": round((time.perf_counter() - start_ts) * 1000, 2),
            }

        clause_text = "\n\n".join(f"[{c['clause_id']}] {c['title']}:\n{c['content']}" for c in clauses)
        allowed_clause_ids = {c["clause_id"] for c in clauses}

        parser = PydanticOutputParser(pydantic_object=GuidelineAnswer)
        prompt = ChatPromptTemplate.from_messages([
            ("system", GUIDELINE_QA_SYSTEM_PROMPT.format(prompt_version=PROMPT_VERSION)),
            ("human", (
                "<guideline_clauses>\n{clause_text}\n</guideline_clauses>\n\n"
                "<untrusted_user_question>\n{user_question}\n</untrusted_user_question>\n\n"
                "Answer the question adhering strictly to the schema:\n{format_instructions}"
            )),
        ])

        chain = prompt | self.llm | parser

        try:
            result: GuidelineAnswer = chain.invoke({
                "clause_text": clause_text,
                "user_question": clean_q,
                "format_instructions": parser.get_format_instructions(),
            })

            if result.cited_clause_ids:
                verify_citations(result.cited_clause_ids, allowed_clause_ids)
            verify_banned_content(result.answer)

            return {
                "answer": result.answer,
                "cited_clause_ids": result.cited_clause_ids,
                "answerable": result.answerable,
                "fallback_used": False,
                "latency_ms": round((time.perf_counter() - start_ts) * 1000, 2),
            }
        except Exception:
            return {
                "answer": "This is not covered by the underwriting guidelines.",
                "cited_clause_ids": [],
                "answerable": False,
                "fallback_used": True,
                "latency_ms": round((time.perf_counter() - start_ts) * 1000, 2),
            }
