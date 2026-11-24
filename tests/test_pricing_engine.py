"""Unit tests for deterministic pricing engine."""

from decimal import Decimal
import pytest
from premiumpulse.domain.models import RiskBand, VehicleClass
from premiumpulse.domain.pricing_engine import (
    compute_monthly_premium,
    get_base_rate,
    get_band_multiplier,
    get_mileage_factor,
    get_vehicle_age_factor,
    get_experience_factor,
    MIN_PREMIUM,
    MAX_PREMIUM,
)


def test_pricing_base_rates():
    """Verify base rates across vehicle classes."""
    assert get_base_rate(VehicleClass.HATCHBACK) == Decimal("38.00")
    assert get_base_rate(VehicleClass.SEDAN) == Decimal("45.00")
    assert get_base_rate(VehicleClass.SUV) == Decimal("55.00")
    assert get_base_rate(VehicleClass.EV) == Decimal("52.00")
    assert get_base_rate(VehicleClass.PICKUP) == Decimal("58.00")


def test_pricing_band_multipliers():
    """Verify risk band multipliers."""
    assert get_band_multiplier(RiskBand.A) == Decimal("0.80")
    assert get_band_multiplier(RiskBand.B) == Decimal("0.95")
    assert get_band_multiplier(RiskBand.C) == Decimal("1.10")
    assert get_band_multiplier(RiskBand.D) == Decimal("1.35")
    assert get_band_multiplier(RiskBand.E) == Decimal("1.70")
    assert get_band_multiplier(RiskBand.UNRATED) == Decimal("1.00")


def test_pricing_factors():
    """Verify step factor lookups for mileage, age, experience."""
    # Mileage
    assert get_mileage_factor(5000) == Decimal("0.92")
    assert get_mileage_factor(8000) == Decimal("0.92")
    assert get_mileage_factor(12000) == Decimal("1.00")
    assert get_mileage_factor(20000) == Decimal("1.12")
    assert get_mileage_factor(35000) == Decimal("1.25")

    # Vehicle Age
    assert get_vehicle_age_factor(1) == Decimal("1.05")
    assert get_vehicle_age_factor(3) == Decimal("1.05")
    assert get_vehicle_age_factor(5) == Decimal("1.00")
    assert get_vehicle_age_factor(9) == Decimal("1.08")

    # Experience (Licence years)
    assert get_experience_factor(1) == Decimal("1.25")
    assert get_experience_factor(2) == Decimal("1.25")
    assert get_experience_factor(4) == Decimal("1.10")
    assert get_experience_factor(10) == Decimal("1.00")


def test_pricing_calculation_and_rounding():
    """Worked example: Sedan, Band B, 10,000 km, 4 yrs old, 6 yrs experience.

    Formula:
    Base: 45.00
    Band B: 0.95
    Mileage 10,000 km: 1.00
    Veh age 4 yrs: 1.00
    Licence 6 yrs: 1.00
    Product: 45.00 * 0.95 * 1.00 * 1.00 * 1.00 = 42.75
    """
    quote = compute_monthly_premium(
        vehicle_class=VehicleClass.SEDAN,
        risk_band=RiskBand.B,
        annual_km_declared=10000,
        vehicle_age_years=4,
        licence_years=6,
    )
    assert quote.final_monthly_premium == Decimal("42.75")


def test_pricing_clamping_bounds():
    """Ensure premiums are clamped to min ($25) and max ($220)."""
    # Low extreme: Hatchback (38), Band A (0.80), Low km (0.92), Mid age (1.00), Exp (1.00)
    # Product = 38 * 0.8 * 0.92 * 1 * 1 = 27.968 -> 27.97 (above min 25)
    quote_low = compute_monthly_premium(
        vehicle_class=VehicleClass.HATCHBACK,
        risk_band=RiskBand.A,
        annual_km_declared=5000,
        vehicle_age_years=5,
        licence_years=10,
    )
    assert quote_low.final_monthly_premium >= MIN_PREMIUM

    # High extreme: Pickup (58), Band E (1.70), 30k km (1.25), 10yr age (1.08), 1yr exp (1.25)
    # Product = 58 * 1.70 * 1.25 * 1.08 * 1.25 = 166.3875 -> 166.39
    quote_high = compute_monthly_premium(
        vehicle_class=VehicleClass.PICKUP,
        risk_band=RiskBand.E,
        annual_km_declared=30000,
        vehicle_age_years=10,
        licence_years=1,
    )
    assert quote_high.final_monthly_premium <= MAX_PREMIUM
    assert quote_high.final_monthly_premium == Decimal("166.39")
