"""Deterministic telematics risk scorecard (Scorecard v1).

Implements the official point deduction logic starting at 100 points,
subtracting weighted penalties per driving metric, clamped to [0, 100].
"""

from typing import Any
from premiumpulse.domain.models import FactorPenalty, RiskBand

SCORECARD_VERSION = "v1"

FACTOR_SPECS = [
    {
        "name": "hard_brake_per_100km",
        "weight": 25.0,
        "cap": 15.0,
        "description": "Hard braking events per 100 km",
    },
    {
        "name": "speeding_pct",
        "weight": 25.0,
        "cap": 20.0,
        "description": "Percentage of driving time exceeding speed limit by >10 km/h",
    },
    {
        "name": "phone_min_per_100km",
        "weight": 20.0,
        "cap": 30.0,
        "description": "Phone usage minutes per 100 km",
    },
    {
        "name": "night_pct",
        "weight": 15.0,
        "cap": 25.0,
        "description": "Percentage of driving time between midnight and 4 AM",
    },
    {
        "name": "hard_accel_per_100km",
        "weight": 10.0,
        "cap": 12.0,
        "description": "Hard acceleration events per 100 km",
    },
    {
        "name": "mileage_exposure",
        "weight": 5.0,
        "cap": 3000.0,
        "description": "Rolling 30-day driving distance (km)",
    },
]

MIN_DISTANCE_FOR_RATING_KM = 50.0


def calculate_factor_penalty(metric_value: float, weight: float, cap: float) -> float:
    """Calculate penalty points for a single factor.

    Formula: penalty_i = weight_i * min(metric_i / cap_i, 1.0)
    """
    if metric_value <= 0.0 or cap <= 0.0:
        return 0.0
    ratio = min(float(metric_value) / float(cap), 1.0)
    return round(float(weight) * ratio, 4)


def determine_risk_band(score: float, distance_km: float) -> RiskBand:
    """Assign driver risk band from A to E, or UNRATED if below minimum threshold."""
    if distance_km < MIN_DISTANCE_FOR_RATING_KM:
        return RiskBand.UNRATED

    # Band boundaries:
    # A: 85 - 100
    # B: 70 - 84.99
    # C: 55 - 69.99
    # D: 40 - 54.99
    # E: 0 - 39.99
    if score >= 85.0:
        return RiskBand.A
    elif score >= 70.0:
        return RiskBand.B
    elif score >= 55.0:
        return RiskBand.C
    elif score >= 40.0:
        return RiskBand.D
    else:
        return RiskBand.E


def compute_driver_scorecard(
    distance_km: float,
    hard_brake_per_100km: float,
    speeding_pct: float,
    phone_min_per_100km: float,
    night_pct: float,
    hard_accel_per_100km: float,
) -> tuple[float, RiskBand, list[FactorPenalty]]:
    """Compute overall risk score, risk band, and per-factor penalty breakdown.

    Returns:
        tuple of (risk_score, risk_band, list_of_penalties)
    """
    metrics = {
        "hard_brake_per_100km": hard_brake_per_100km,
        "speeding_pct": speeding_pct,
        "phone_min_per_100km": phone_min_per_100km,
        "night_pct": night_pct,
        "hard_accel_per_100km": hard_accel_per_100km,
        "mileage_exposure": distance_km,
    }

    penalties: list[FactorPenalty] = []
    total_penalty = 0.0

    for spec in FACTOR_SPECS:
        name = spec["name"]
        val = max(0.0, float(metrics.get(name, 0.0)))
        pts = calculate_factor_penalty(val, spec["weight"], spec["cap"])
        penalties.append(
            FactorPenalty(
                factor_name=name,
                metric_value=round(val, 2),
                cap_value=spec["cap"],
                weight=spec["weight"],
                penalty_points=round(pts, 2),
            )
        )
        total_penalty += pts

    raw_score = max(0.0, 100.0 - total_penalty)
    final_score = round(raw_score, 1)
    band = determine_risk_band(final_score, distance_km)

    return final_score, band, penalties
