"""Verified Facts payload builder for AI narration.

Enforces zero-PII extraction: names, emails, and exact locations are stripped.
Each fact is assigned a numbered reference ID (F1, F2, ...) for deterministic verification.
"""

import hashlib
import json
from decimal import Decimal
from typing import Any
from pydantic import BaseModel

from premiumpulse.domain.models import DriverQuote, DriverRiskScore


class VerifiedFact(BaseModel):
    """Atomic fact with unique identifier and formatted value."""
    fact_id: str
    fact_key: str
    value: Any
    display_str: str


class FactsPayload(BaseModel):
    """Complete collection of verified facts extracted from database/service layer."""
    driver_id: str
    facts: list[VerifiedFact]
    facts_hash: str
    raw_numbers: set[str]  # Normalized strings of numbers for NumberGrounder


def build_quote_facts(quote: DriverQuote, score: DriverRiskScore | None = None) -> FactsPayload:
    """Construct verified, PII-free FACTS payload for quote explanation."""
    facts: list[VerifiedFact] = []
    raw_numbers: set[str] = set()

    def add_fact(fid: str, key: str, val: Any, unit: str = ""):
        s_val = str(val)
        disp = f"{s_val} {unit}".strip()
        facts.append(VerifiedFact(fact_id=fid, fact_key=key, value=val, display_str=disp))
        # Record raw numeric string for NumberGrounder
        if isinstance(val, (int, float, Decimal)):
            raw_numbers.add(f"{float(val):.2f}")
            raw_numbers.add(f"{float(val):.1f}")
            raw_numbers.add(str(int(float(val))))
            raw_numbers.add(str(val))

    add_fact("F1", "driver_id", quote.driver_id)
    add_fact("F2", "risk_score", quote.risk_score, "points")
    add_fact("F3", "risk_band", quote.risk_band.value)
    add_fact("F4", "monthly_premium", f"${quote.monthly_premium:.2f}")
    raw_numbers.add(str(quote.monthly_premium))
    raw_numbers.add(f"{float(quote.monthly_premium):.2f}")

    add_fact("F5", "annual_premium", f"${quote.annual_premium:.2f}")
    raw_numbers.add(str(quote.annual_premium))
    raw_numbers.add(f"{float(quote.annual_premium):.2f}")

    add_fact("F6", "vehicle_class", quote.vehicle_class.value)
    add_fact("F7", "base_rate", f"${quote.breakdown.base_rate:.2f}")
    raw_numbers.add(str(quote.breakdown.base_rate))

    add_fact("F8", "band_multiplier", f"{quote.breakdown.band_multiplier:.2f}x")
    raw_numbers.add(str(quote.breakdown.band_multiplier))

    add_fact("F9", "mileage_factor", f"{quote.breakdown.mileage_factor:.2f}x")
    raw_numbers.add(str(quote.breakdown.mileage_factor))

    add_fact("F10", "vehicle_age_factor", f"{quote.breakdown.vehicle_age_factor:.2f}x")
    raw_numbers.add(str(quote.breakdown.vehicle_age_factor))

    add_fact("F11", "experience_factor", f"{quote.breakdown.experience_factor:.2f}x")
    raw_numbers.add(str(quote.breakdown.experience_factor))

    # Add score penalties if available
    if score and score.factor_penalties:
        for idx, p in enumerate(score.factor_penalties, start=12):
            fid = f"F{idx}"
            add_fact(
                fid,
                f"penalty_{p.factor_name}",
                f"{p.penalty_points} pts (metric: {p.metric_value})",
            )
            raw_numbers.add(str(p.penalty_points))
            raw_numbers.add(str(p.metric_value))

    # Compute deterministic hash of facts
    facts_str = json.dumps([f.model_dump() for f in facts], sort_keys=True)
    facts_hash = hashlib.sha256(facts_str.encode("utf-8")).hexdigest()[:16]

    return FactsPayload(
        driver_id=quote.driver_id,
        facts=facts,
        facts_hash=facts_hash,
        raw_numbers=raw_numbers,
    )


def build_coaching_facts(score: DriverRiskScore, quote: DriverQuote) -> FactsPayload:
    """Construct verified facts for the top 3 driving penalty factors and potential gains."""
    facts: list[VerifiedFact] = []
    raw_numbers: set[str] = set()

    # Sort penalties by impact
    sorted_penalties = sorted(score.factor_penalties, key=lambda x: x.penalty_points, reverse=True)
    top_3 = sorted_penalties[:3]

    facts.append(VerifiedFact(fact_id="F1", fact_key="current_risk_score", value=score.risk_score, display_str=f"{score.risk_score} points"))
    raw_numbers.add(str(score.risk_score))

    facts.append(VerifiedFact(fact_id="F2", fact_key="current_monthly_premium", value=float(quote.monthly_premium), display_str=f"${quote.monthly_premium:.2f}"))
    raw_numbers.add(str(quote.monthly_premium))

    fact_idx = 3
    for p in top_3:
        # Code precomputes potential points gain if driver cuts infraction by 50%
        potential_gain = round(p.penalty_points * 0.5, 1)
        fid_factor = f"F{fact_idx}"
        facts.append(VerifiedFact(
            fact_id=fid_factor,
            fact_key=f"factor_{p.factor_name}",
            value=p.metric_value,
            display_str=f"{p.factor_name}: {p.metric_value} (deducted {p.penalty_points} pts)",
        ))
        raw_numbers.add(str(p.metric_value))
        raw_numbers.add(str(p.penalty_points))
        fact_idx += 1

        fid_gain = f"F{fact_idx}"
        facts.append(VerifiedFact(
            fact_id=fid_gain,
            fact_key=f"potential_gain_{p.factor_name}",
            value=potential_gain,
            display_str=f"+{potential_gain} points potential recovery",
        ))
        raw_numbers.add(str(potential_gain))
        fact_idx += 1

    facts_str = json.dumps([f.model_dump() for f in facts], sort_keys=True)
    facts_hash = hashlib.sha256(facts_str.encode("utf-8")).hexdigest()[:16]

    return FactsPayload(
        driver_id=quote.driver_id,
        facts=facts,
        facts_hash=facts_hash,
        raw_numbers=raw_numbers,
    )
