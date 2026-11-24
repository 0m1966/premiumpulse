"""Deterministic rate-factor pricing engine.

Mirrors the exact mathematical formula implemented in Snowflake SQL (QUOTES dynamic table).
Enforces Decimal arithmetic and half-up rounding.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from premiumpulse.domain.models import QuoteBreakdown, RiskBand, VehicleClass

# Pricing seed configuration
BASE_RATES: dict[VehicleClass, Decimal] = {
    VehicleClass.HATCHBACK: Decimal("38.00"),
    VehicleClass.SEDAN: Decimal("45.00"),
    VehicleClass.SUV: Decimal("55.00"),
    VehicleClass.EV: Decimal("52.00"),
    VehicleClass.PICKUP: Decimal("58.00"),
}

BAND_MULTIPLIERS: dict[RiskBand, Decimal] = {
    RiskBand.A: Decimal("0.80"),
    RiskBand.B: Decimal("0.95"),
    RiskBand.C: Decimal("1.10"),
    RiskBand.D: Decimal("1.35"),
    RiskBand.E: Decimal("1.70"),
    RiskBand.UNRATED: Decimal("1.00"),
}

MIN_PREMIUM = Decimal("25.00")
MAX_PREMIUM = Decimal("220.00")


def get_base_rate(vehicle_class: VehicleClass | str) -> Decimal:
    """Return base rate for vehicle class."""
    if isinstance(vehicle_class, str):
        vehicle_class = VehicleClass(vehicle_class.upper())
    return BASE_RATES.get(vehicle_class, Decimal("45.00"))


def get_band_multiplier(band: RiskBand | str) -> Decimal:
    """Return risk band multiplier."""
    if isinstance(band, str):
        band = RiskBand(band.upper())
    return BAND_MULTIPLIERS.get(band, Decimal("1.00"))


def get_mileage_factor(annual_km_declared: int) -> Decimal:
    """Return mileage factor based on declared annual kilometers."""
    if annual_km_declared <= 8000:
        return Decimal("0.92")
    elif annual_km_declared <= 15000:
        return Decimal("1.00")
    elif annual_km_declared <= 25000:
        return Decimal("1.12")
    else:
        return Decimal("1.25")


def get_vehicle_age_factor(vehicle_age_years: int) -> Decimal:
    """Return vehicle age multiplier."""
    if vehicle_age_years <= 3:
        return Decimal("1.05")
    elif vehicle_age_years <= 8:
        return Decimal("1.00")
    else:
        return Decimal("1.08")


def get_experience_factor(licence_years: int) -> Decimal:
    """Return driver driving experience multiplier."""
    if licence_years <= 2:
        return Decimal("1.25")
    elif licence_years <= 5:
        return Decimal("1.10")
    else:
        return Decimal("1.00")


def compute_monthly_premium(
    vehicle_class: VehicleClass | str,
    risk_band: RiskBand | str,
    annual_km_declared: int,
    vehicle_age_years: int,
    licence_years: int,
    effective_rate_date: date | None = None,
) -> QuoteBreakdown:
    """Compute monthly insurance premium using strictly audited multiplicative formula.

    Formula:
        uncapped = base_rate * band_multiplier * mileage_factor * vehicle_age_factor * experience_factor
        final_premium = clamp(uncapped, min_premium, max_premium)
    """
    base_rate = get_base_rate(vehicle_class)
    band_mult = get_band_multiplier(risk_band)
    mileage_f = get_mileage_factor(annual_km_declared)
    veh_age_f = get_vehicle_age_factor(vehicle_age_years)
    exp_f = get_experience_factor(licence_years)

    # Compute unrounded product using high precision
    uncapped = base_rate * band_mult * mileage_f * veh_age_f * exp_f
    clamped = max(MIN_PREMIUM, min(uncapped, MAX_PREMIUM))

    # Round half-up to 2 decimal places at the very end
    final_premium = clamped.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    uncapped_rounded = uncapped.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return QuoteBreakdown(
        base_rate=base_rate,
        band_multiplier=band_mult,
        mileage_factor=mileage_f,
        vehicle_age_factor=veh_age_f,
        experience_factor=exp_f,
        uncapped_premium=uncapped_rounded,
        final_monthly_premium=final_premium,
        min_premium=MIN_PREMIUM,
        max_premium=MAX_PREMIUM,
        effective_rate_date=effective_rate_date or date(2025, 1, 1),
    )
