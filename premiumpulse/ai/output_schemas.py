"""Strict Pydantic output schemas for LangChain narration chains."""

from typing import Any
from pydantic import BaseModel, Field


class FactorStatement(BaseModel):
    """Description of a single pricing factor driver."""
    factor_name: str = Field(description="Name of the rating or scorecard factor")
    impact_description: str = Field(description="Brief factual description of the factor's impact")
    cited_fact_id: str = Field(description="Fact ID from the provided <facts> payload")


class QuoteExplanation(BaseModel):
    """Grounded explanation of driver risk score and monthly quote."""
    summary: str = Field(
        description="Factual plain-English summary of the score and quote, maximum 60 words"
    )
    top_drivers_of_price: list[FactorStatement] = Field(
        max_length=3,
        description="Up to 3 primary drivers influencing the premium"
    )
    cited_fact_ids: list[str] = Field(
        min_length=1,
        description="List of all Fact IDs cited from the <facts> block"
    )


class Tip(BaseModel):
    """Actionable coaching tip based on driver's telematics performance."""
    factor: str = Field(description="Driving factor name, e.g. hard_brake_per_100km")
    advice: str = Field(description="Concrete advice to improve safety, maximum 30 words")
    estimated_points_gain_fact_id: str = Field(
        description="Fact ID corresponding to the precomputed points gain"
    )


class CoachingTips(BaseModel):
    """List of exactly 3 safety improvement coaching tips."""
    tips: list[Tip] = Field(
        min_length=3,
        max_length=3,
        description="Exactly 3 personalized coaching tips"
    )
    cited_fact_ids: list[str] = Field(
        min_length=1,
        description="Fact IDs cited from the input facts"
    )


class GuidelineAnswer(BaseModel):
    """Answer to user question grounded strictly in underwriting guidelines."""
    answer: str = Field(
        description="Direct answer using only information from retrieved clauses, maximum 80 words"
    )
    cited_clause_ids: list[str] = Field(
        description="List of clause IDs cited (e.g. UG-103)"
    )
    answerable: bool = Field(
        description="True if question is answered by the clauses, False otherwise"
    )
