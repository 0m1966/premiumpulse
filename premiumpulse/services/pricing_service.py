"""Shared business logic and domain service layer for PremiumPulse.

Consistently consumed by both FastAPI REST endpoints and Streamlit portal pages.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from premiumpulse.db.client_factory import get_db_client
from premiumpulse.domain.models import (
    DriverProfile,
    DriverQuote,
    DriverRiskScore,
    FactorPenalty,
    PortfolioSummary,
    QuoteBreakdown,
    QuoteSimulationRequest,
    QuoteSimulationResponse,
    RiskBand,
    VehicleClass,
    VehicleProfile,
)
from premiumpulse.domain.pricing_engine import compute_monthly_premium
from premiumpulse.domain.scorecard import compute_driver_scorecard


class PricingService:
    """Service layer coordinating telematics scoring, quoting, and simulations."""

    def __init__(self, db_client: Any | None = None):
        self.db = db_client or get_db_client()

    def list_drivers(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List drivers with current pricing overview."""
        return self.db.list_drivers(limit=limit, offset=offset)

    def get_driver_profile(self, driver_id: str) -> DriverProfile | None:
        """Fetch full driver profile."""
        row = self.db.get_driver_profile(driver_id)
        if not row:
            return None
        return DriverProfile(
            driver_id=row["driver_id"],
            full_name=row["full_name"],
            email=row["email"],
            age_band=row["age_band"],
            licence_years=int(row["licence_years"]),
            city=row["city"],
            created_at=datetime.fromisoformat(row["created_at"].replace(" ", "T")),
        )

    def get_vehicle_profile(self, driver_id: str) -> VehicleProfile | None:
        """Fetch vehicle profile for driver."""
        row = self.db.get_driver_profile(driver_id)
        if not row:
            return None
        return VehicleProfile(
            vehicle_id=row["vehicle_id"],
            driver_id=row["driver_id"],
            vehicle_class=VehicleClass(row["vehicle_class"].upper()),
            vehicle_age_years=int(row["vehicle_age_years"]),
            annual_km_declared=int(row["annual_km_declared"]),
        )

    def get_driver_score(self, driver_id: str) -> DriverRiskScore | None:
        """Fetch calculated telematics score and per-factor penalties."""
        row = self.db.get_driver_score(driver_id)
        if not row:
            return None

        # Recompute factor penalties for display
        _, _, penalties = compute_driver_scorecard(
            distance_km=float(row["distance_km"]),
            hard_brake_per_100km=float(row["hard_brake_per_100km"]),
            speeding_pct=float(row["speeding_pct"]),
            phone_min_per_100km=float(row["phone_min_per_100km"]),
            night_pct=float(row["night_pct"]),
            hard_accel_per_100km=float(row["hard_accel_per_100km"]),
        )

        return DriverRiskScore(
            driver_id=row["driver_id"],
            window_start=date.fromisoformat(row["window_start"]),
            window_end=date.fromisoformat(row["window_end"]),
            distance_km=float(row["distance_km"]),
            hard_brake_per_100km=float(row["hard_brake_per_100km"]),
            hard_accel_per_100km=float(row["hard_accel_per_100km"]),
            speeding_pct=float(row["speeding_pct"]),
            night_pct=float(row["night_pct"]),
            phone_min_per_100km=float(row["phone_min_per_100km"]),
            risk_score=float(row["risk_score"]),
            risk_band=RiskBand(row["risk_band"].upper()),
            scorecard_version=row.get("scorecard_version", "v1"),
            factor_penalties=penalties,
        )

    def get_driver_quote(self, driver_id: str) -> DriverQuote | None:
        """Fetch official issued quote for driver."""
        row = self.db.get_driver_quote(driver_id)
        if not row:
            return None

        breakdown = QuoteBreakdown(
            base_rate=Decimal(str(row["base_rate"])),
            band_multiplier=Decimal(str(row["band_multiplier"])),
            mileage_factor=Decimal(str(row["mileage_factor"])),
            vehicle_age_factor=Decimal(str(row["vehicle_age_factor"])),
            experience_factor=Decimal(str(row["experience_factor"])),
            uncapped_premium=Decimal(str(row["monthly_premium"])),
            final_monthly_premium=Decimal(str(row["monthly_premium"])),
            min_premium=Decimal("25.00"),
            max_premium=Decimal("220.00"),
            effective_rate_date=date.fromisoformat(str(row["effective_rate_date"])[:10]),
        )

        return DriverQuote(
            quote_id=row["quote_id"],
            driver_id=row["driver_id"],
            vehicle_id=row["vehicle_id"],
            vehicle_class=VehicleClass(row["vehicle_class"].upper()),
            risk_score=float(row["risk_score"]),
            risk_band=RiskBand(row["risk_band"].upper()),
            monthly_premium=Decimal(str(row["monthly_premium"])),
            annual_premium=Decimal(str(row["annual_premium"])),
            breakdown=breakdown,
            generated_at=datetime.fromisoformat(str(row["generated_at"]).replace(" ", "T")[:19]),
        )

    def get_driver_trips(self, driver_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch historical trip details."""
        return self.db.get_driver_trips(driver_id, limit=limit)

    def get_portfolio_summary(self) -> PortfolioSummary:
        """Fetch aggregated portfolio metrics."""
        data = self.db.portfolio_summary()
        return PortfolioSummary(
            total_drivers=data.get("total_drivers", 0),
            average_risk_score=float(data.get("average_risk_score", 0.0)),
            average_monthly_premium=Decimal(str(data.get("average_monthly_premium", "0.00"))),
            band_distribution=data.get("band_distribution", {}),
            vehicle_distribution=data.get("vehicle_distribution", {}),
            city_distribution=data.get("city_distribution", {}),
        )

    def simulate_quote(self, request: QuoteSimulationRequest) -> QuoteSimulationResponse:
        """Execute deterministic what-if pricing simulation."""
        # 1. Fetch current driver baseline
        current_quote = self.get_driver_quote(request.driver_id)
        driver_prof = self.get_driver_profile(request.driver_id)
        veh_prof = self.get_vehicle_profile(request.driver_id)

        if not current_quote or not driver_prof or not veh_prof:
            raise ValueError(f"Driver {request.driver_id} not found for simulation.")

        # 2. Score simulated driving behavior using Scorecard v1
        # Assume standard 30-day baseline mileage if distance not provided in request
        score_rec = self.get_driver_score(request.driver_id)
        sim_dist = score_rec.distance_km if score_rec else 500.0

        sim_score, sim_band, sim_penalties = compute_driver_scorecard(
            distance_km=sim_dist,
            hard_brake_per_100km=request.hard_brake_per_100km,
            speeding_pct=request.speeding_pct,
            phone_min_per_100km=request.phone_min_per_100km,
            night_pct=request.night_pct,
            hard_accel_per_100km=request.hard_accel_per_100km,
        )

        # 3. Price simulated policy using Pricing Engine
        projected_quote = compute_monthly_premium(
            vehicle_class=veh_prof.vehicle_class,
            risk_band=sim_band,
            annual_km_declared=request.annual_km_declared,
            vehicle_age_years=veh_prof.vehicle_age_years,
            licence_years=driver_prof.licence_years,
        )

        monthly_savings = current_quote.monthly_premium - projected_quote.final_monthly_premium
        annual_savings = monthly_savings * 12
        score_delta = round(sim_score - current_quote.risk_score, 1)

        return QuoteSimulationResponse(
            driver_id=request.driver_id,
            current_risk_score=current_quote.risk_score,
            current_risk_band=current_quote.risk_band,
            current_monthly_premium=current_quote.monthly_premium,
            projected_risk_score=sim_score,
            projected_risk_band=sim_band,
            projected_monthly_premium=projected_quote.final_monthly_premium,
            monthly_savings=monthly_savings,
            annual_savings=annual_savings,
            score_delta=score_delta,
            projected_penalties=sim_penalties,
        )
