"""Domain models and data schemas for PremiumPulse."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class RiskBand(str, Enum):
    """Telematics risk scoring bands."""
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    UNRATED = "UNRATED"


class VehicleClass(str, Enum):
    """Allowed rating vehicle classes."""
    HATCHBACK = "HATCHBACK"
    SEDAN = "SEDAN"
    SUV = "SUV"
    EV = "EV"
    PICKUP = "PICKUP"


class FactorPenalty(BaseModel):
    """Individual penalty points calculated for a single telematics risk factor."""
    factor_name: str
    metric_value: float
    cap_value: float
    weight: float
    penalty_points: float


class DriverRiskScore(BaseModel):
    """Complete telematics scorecard evaluation for a driver over a rolling 30-day window."""
    driver_id: str
    window_start: date
    window_end: date
    distance_km: float
    hard_brake_per_100km: float
    hard_accel_per_100km: float
    speeding_pct: float
    night_pct: float
    phone_min_per_100km: float
    risk_score: float
    risk_band: RiskBand
    scorecard_version: str = "v1"
    factor_penalties: list[FactorPenalty] = Field(default_factory=list)


class DriverProfile(BaseModel):
    """Driver master record."""
    driver_id: str
    full_name: str
    email: str
    age_band: str
    licence_years: int
    city: str
    created_at: datetime


class VehicleProfile(BaseModel):
    """Vehicle master record."""
    vehicle_id: str
    driver_id: str
    vehicle_class: VehicleClass
    vehicle_age_years: int
    annual_km_declared: int


class QuoteBreakdown(BaseModel):
    """Transparent pricing breakdown showing each multiplier applied to the base rate."""
    base_rate: Decimal
    band_multiplier: Decimal
    mileage_factor: Decimal
    vehicle_age_factor: Decimal
    experience_factor: Decimal
    uncapped_premium: Decimal
    final_monthly_premium: Decimal
    min_premium: Decimal
    max_premium: Decimal
    effective_rate_date: date


class DriverQuote(BaseModel):
    """Official quote issued for an insured driver."""
    quote_id: str
    driver_id: str
    vehicle_id: str
    vehicle_class: VehicleClass
    risk_score: float
    risk_band: RiskBand
    monthly_premium: Decimal
    annual_premium: Decimal
    breakdown: QuoteBreakdown
    generated_at: datetime


class QuoteSimulationRequest(BaseModel):
    """What-if simulation input parameters."""
    driver_id: str
    hard_brake_per_100km: float = Field(ge=0.0, le=50.0)
    hard_accel_per_100km: float = Field(ge=0.0, le=50.0)
    speeding_pct: float = Field(ge=0.0, le=100.0)
    night_pct: float = Field(ge=0.0, le=100.0)
    phone_min_per_100km: float = Field(ge=0.0, le=120.0)
    annual_km_declared: int = Field(ge=1000, le=100000)


class QuoteSimulationResponse(BaseModel):
    """What-if simulation output comparing baseline and projected figures."""
    driver_id: str
    current_risk_score: float
    current_risk_band: RiskBand
    current_monthly_premium: Decimal
    projected_risk_score: float
    projected_risk_band: RiskBand
    projected_monthly_premium: Decimal
    monthly_savings: Decimal
    annual_savings: Decimal
    score_delta: float
    projected_penalties: list[FactorPenalty]


class PortfolioSummary(BaseModel):
    """Aggregated portfolio metrics for underwriter dashboards."""
    total_drivers: int
    average_risk_score: float
    average_monthly_premium: Decimal
    band_distribution: dict[str, int]
    vehicle_distribution: dict[str, int]
    city_distribution: dict[str, int]
