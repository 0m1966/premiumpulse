"""Anti-hallucination and containment guardrails for PremiumPulse AI layer.

Enforces:
1. Strict input regex validation and injection detection.
2. NumberGrounder: Rejects any number not present in the verified FACTS payload.
3. CitationVerifier: Rejects non-existent or empty citations.
4. BannedContentChecker: Rejects URLs, SQL, code blocks, and off-topic leaks.
5. Deterministic fallback generation on any failure.
"""

import re
import unicodedata
from typing import Any
from premiumpulse.ai.facts import FactsPayload

DRIVER_ID_REGEX = re.compile(r"^DRV-\d{5}$")

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions?",
    r"system\s+prompt",
    r"reveal\s+(the\s+)?(instructions?|prompt|keys?|secrets?)",
    r"act\s+as\s+",
    r"jailbreak",
    r"base64",
    r"delete\s+from",
    r"drop\s+table",
    r"<script",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
]

BANNED_OUTPUT_PATTERNS = [
    r"https?://",
    r"www\.",
    r"```(?:sql|python|bash|sh|javascript)",
    r"\b(SELECT|DROP|INSERT|DELETE|UNION|UPDATE)\s+[a-zA-Z0-9_*]",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
]


class GuardrailError(ValueError):
    """Raised when an AI input or output fails security validation."""


def validate_driver_id(driver_id: str) -> str:
    """Validate driver_id strictly against allow-list pattern."""
    clean_id = driver_id.strip().upper()
    if not DRIVER_ID_REGEX.match(clean_id):
        raise GuardrailError(f"Invalid driver ID: {driver_id}. Must match pattern DRV-XXXXX.")
    return clean_id


def sanitize_user_question(question: str) -> str:
    """Sanitize user free-text query, checking for length and injection patterns."""
    if not question:
        raise GuardrailError("User question cannot be empty.")

    # Strip control characters and normalize unicode
    clean_q = "".join(ch for ch in question if unicodedata.category(ch)[0] != "C").strip()

    if len(clean_q) > 300:
        raise GuardrailError("User question exceeds maximum allowed length of 300 characters.")

    # Injection pattern filter
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, clean_q, re.IGNORECASE):
            raise GuardrailError(f"Potential prompt injection pattern detected in input: '{pattern}'")

    return clean_q


def verify_number_grounding(text: str, facts: FactsPayload) -> None:
    """NumberGrounder: Asserts that every number in the LLM text exists in the verified facts."""
    # Find all standalone numbers (integers, floats, percentages, dollars)
    found_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", text)

    for num_str in found_numbers:
        # Check standard normalizations (e.g. 85.0 vs 85)
        try:
            f_val = float(num_str)
            normalized_variants = {
                num_str,
                f"{f_val:.2f}",
                f"{f_val:.1f}",
                str(int(f_val)),
            }
        except ValueError:
            normalized_variants = {num_str}

        # Check if any variant exists in facts.raw_numbers
        if not any(v in facts.raw_numbers for v in normalized_variants):
            raise GuardrailError(
                f"NumberGrounder rejected output: ungrounded number '{num_str}' was not found in verified FACTS."
            )


def verify_citations(cited_ids: list[str], allowed_ids: set[str]) -> None:
    """Verify that cited IDs are valid, non-empty, and subset of provided facts/clauses."""
    if not cited_ids:
        raise GuardrailError("Citation verification failed: cited IDs list cannot be empty.")

    for cid in cited_ids:
        if cid not in allowed_ids:
            raise GuardrailError(
                f"Citation verification failed: cited ID '{cid}' does not exist in provided reference set."
            )


def verify_banned_content(text: str) -> None:
    """Assert output does not contain URLs, executable code blocks, SQL keywords, or emails."""
    for pattern in BANNED_OUTPUT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            raise GuardrailError(f"Banned content detected in AI output matching pattern: '{pattern}'")


def build_deterministic_fallback(facts: FactsPayload) -> dict[str, Any]:
    """Construct deterministic template explanation from verified facts when AI fails or is offline."""
    # Extract key values
    f_map = {f.fact_key: f.value for f in facts.facts}
    score = f_map.get("risk_score", "N/A")
    band = f_map.get("risk_band", "N/A")
    monthly_prem = f_map.get("monthly_premium", "N/A")
    base_rate = f_map.get("base_rate", "N/A")
    band_mult = f_map.get("band_multiplier", "N/A")

    return {
        "summary": (
            f"Driver {facts.driver_id} achieved a telematics risk score of {score} points (Band {band}). "
            f"Based on certified rating factors, the monthly premium is set to {monthly_prem}."
        ),
        "top_drivers_of_price": [
            {
                "factor_name": "Risk Band Rating",
                "impact_description": f"Assigned Risk Band {band} with a rating multiplier of {band_mult}.",
                "cited_fact_id": "F3",
            },
            {
                "factor_name": "Vehicle Base Rate",
                "impact_description": f"Base vehicle classification monthly rate of {base_rate}.",
                "cited_fact_id": "F7",
            },
        ],
        "cited_fact_ids": ["F2", "F3", "F4", "F7"],
        "fallback_used": True,
        "notice": "AI explanation unavailable; standard deterministic summary rendered.",
    }
