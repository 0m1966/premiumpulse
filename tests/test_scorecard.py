"""Unit tests for telematics scorecard (v1)."""

import pytest
from premiumpulse.domain.models import RiskBand
from premiumpulse.domain.scorecard import (
    compute_driver_scorecard,
    calculate_factor_penalty,
    determine_risk_band,
    MIN_DISTANCE_FOR_RATING_KM,
)


def test_scorecard_zero_metrics_yields_100():
    """All 0 metrics must yield exactly 100.0 points."""
    score, band, penalties = compute_driver_scorecard(
        distance_km=0.0,
        hard_brake_per_100km=0.0,
        speeding_pct=0.0,
        phone_min_per_100km=0.0,
        night_pct=0.0,
        hard_accel_per_100km=0.0,
    )
    assert score == 100.0
    assert band == RiskBand.UNRATED
    assert all(p.penalty_points == 0.0 for p in penalties)


def test_scorecard_safe_driver_band_a():
    """Safe driver with 500 km and zero infractions has minimal exposure penalty and gets Band A."""
    score, band, penalties = compute_driver_scorecard(
        distance_km=500.0,
        hard_brake_per_100km=0.0,
        speeding_pct=0.0,
        phone_min_per_100km=0.0,
        night_pct=0.0,
        hard_accel_per_100km=0.0,
    )
    # Mileage penalty: 5 * (500 / 3000) = 0.8333 -> 99.2
    assert score == 99.2
    assert band == RiskBand.A
    assert len(penalties) == 6


def test_scorecard_worst_driver_all_caps_exceeded():
    """Driver exceeding all caps must receive maximum penalty (100 pts) and clamp to 0.0 / Band E."""
    score, band, penalties = compute_driver_scorecard(
        distance_km=5000.0,  # Cap is 3000 -> 5 pts
        hard_brake_per_100km=50.0,  # Cap is 15 -> 25 pts
        speeding_pct=80.0,  # Cap is 20 -> 25 pts
        phone_min_per_100km=60.0,  # Cap is 30 -> 20 pts
        night_pct=50.0,  # Cap is 25 -> 15 pts
        hard_accel_per_100km=30.0,  # Cap is 12 -> 10 pts
    )
    # Total penalties: 25 + 25 + 20 + 15 + 10 + 5 = 100
    assert score == 0.0
    assert band == RiskBand.E
    total_penalty = sum(p.penalty_points for p in penalties)
    assert pytest.approx(total_penalty, 0.01) == 100.0


def test_scorecard_band_boundaries():
    """Verify exact score band cutoffs."""
    # Distance >= 50 km
    assert determine_risk_band(100.0, 100.0) == RiskBand.A
    assert determine_risk_band(85.0, 100.0) == RiskBand.A
    assert determine_risk_band(84.99, 100.0) == RiskBand.B
    assert determine_risk_band(70.0, 100.0) == RiskBand.B
    assert determine_risk_band(69.99, 100.0) == RiskBand.C
    assert determine_risk_band(55.0, 100.0) == RiskBand.C
    assert determine_risk_band(54.99, 100.0) == RiskBand.D
    assert determine_risk_band(40.0, 100.0) == RiskBand.D
    assert determine_risk_band(39.99, 100.0) == RiskBand.E
    assert determine_risk_band(0.0, 100.0) == RiskBand.E


def test_scorecard_unrated_below_minimum_mileage():
    """Drivers with under 50 km driven must be UNRATED."""
    score, band, _ = compute_driver_scorecard(
        distance_km=45.0,
        hard_brake_per_100km=0.0,
        speeding_pct=0.0,
        phone_min_per_100km=0.0,
        night_pct=0.0,
        hard_accel_per_100km=0.0,
    )
    assert band == RiskBand.UNRATED
    # 45 km / 3000 * 5 = 0.075 penalty -> score 99.9
    assert score == 99.9


def test_scorecard_monotonicity():
    """Increasing phone usage must monotonically decrease or equal risk score."""
    scores = []
    for phone_min in [0.0, 5.0, 10.0, 20.0, 30.0, 40.0]:
        s, _, _ = compute_driver_scorecard(
            distance_km=200.0,
            hard_brake_per_100km=2.0,
            speeding_pct=5.0,
            phone_min_per_100km=phone_min,
            night_pct=2.0,
            hard_accel_per_100km=1.0,
        )
        scores.append(s)

    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1]
