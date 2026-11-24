"""Parity tests asserting mathematical equivalence between Python pricing engine and SQL QUOTES."""

from decimal import Decimal
import pytest
from premiumpulse.db.client_factory import get_db_client
from premiumpulse.domain.pricing_engine import compute_monthly_premium


def test_pricing_parity_across_20_driver_fixtures():
    """Verify that Python pricing_engine and SQL QUOTES logic produce identical results (tolerance <= 0.01)."""
    db = get_db_client()

    # Query 20 drivers with all attributes and their recorded quote from the database
    query = """
    SELECT
        d.driver_id,
        d.licence_years,
        v.vehicle_class,
        v.vehicle_age_years,
        v.annual_km_declared,
        q.risk_band,
        q.monthly_premium AS sql_monthly_premium,
        q.base_rate AS sql_base_rate,
        q.band_multiplier AS sql_band_multiplier,
        q.mileage_factor AS sql_mileage_factor,
        q.vehicle_age_factor AS sql_vehicle_age_factor,
        q.experience_factor AS sql_experience_factor
    FROM drivers d
    JOIN vehicles v ON d.driver_id = v.driver_id
    JOIN quotes q ON d.driver_id = q.driver_id
    LIMIT 20;
    """
    rows = db.execute_query(query)
    assert len(rows) >= 20, f"Expected at least 20 fixtures, got {len(rows)}"

    for r in rows:
        driver_id = r["driver_id"]
        v_class = r["vehicle_class"]
        v_age = int(r["vehicle_age_years"])
        ann_km = int(r["annual_km_declared"])
        lic_years = int(r["licence_years"])
        band = r["risk_band"]
        sql_premium = float(r["sql_monthly_premium"])

        # Compute with pure Python pricing engine
        python_quote = compute_monthly_premium(
            vehicle_class=v_class,
            risk_band=band,
            annual_km_declared=ann_km,
            vehicle_age_years=v_age,
            licence_years=lic_years,
        )
        python_premium = float(python_quote.final_monthly_premium)

        # Check multiplier parity
        assert pytest.approx(float(python_quote.base_rate), 0.01) == float(r["sql_base_rate"])
        assert pytest.approx(float(python_quote.band_multiplier), 0.01) == float(r["sql_band_multiplier"])
        assert pytest.approx(float(python_quote.mileage_factor), 0.01) == float(r["sql_mileage_factor"])
        assert pytest.approx(float(python_quote.vehicle_age_factor), 0.01) == float(r["sql_vehicle_age_factor"])
        assert pytest.approx(float(python_quote.experience_factor), 0.01) == float(r["sql_experience_factor"])

        # Check final premium parity with tolerance 0.01
        diff = abs(python_premium - sql_premium)
        assert diff <= 0.01, (
            f"Parity mismatch on {driver_id}: Python={python_premium}, SQL={sql_premium}, diff={diff}"
        )
