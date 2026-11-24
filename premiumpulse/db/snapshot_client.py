"""Offline snapshot SQLite database client.

Provides identical query interface to SnowflakeClient, reading from
the bundled snapshot/premiumpulse_snapshot.db file.
"""

import sqlite3
from pathlib import Path
from typing import Any

SNAPSHOT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "snapshot" / "premiumpulse_snapshot.db"


class SnapshotClient:
    """Client for executing parameterised queries against the offline SQLite snapshot."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else SNAPSHOT_DB_PATH

    def _get_connection(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Snapshot database not found at {self.db_path}. Run snapshot/build_snapshot.py first."
            )
        conn = sqlite3.connect(self.db_path, timeout=8.0)
        conn.row_factory = sqlite3.Row
        return conn

    def execute_query(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute parameterised query and return list of dictionaries."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def list_drivers(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List drivers with their current quotes."""
        query = """
        SELECT
            d.driver_id,
            d.full_name,
            d.email,
            d.age_band,
            d.licence_years,
            d.city,
            v.vehicle_class,
            v.annual_km_declared,
            q.risk_score,
            q.risk_band,
            q.monthly_premium,
            q.annual_premium
        FROM drivers d
        JOIN vehicles v ON d.driver_id = v.driver_id
        LEFT JOIN quotes q ON d.driver_id = q.driver_id
        ORDER BY d.driver_id ASC
        LIMIT ? OFFSET ?;
        """
        return self.execute_query(query, (limit, offset))

    def get_driver_profile(self, driver_id: str) -> dict[str, Any] | None:
        """Fetch driver and vehicle master details."""
        query = """
        SELECT
            d.driver_id,
            d.full_name,
            d.email,
            d.age_band,
            d.licence_years,
            d.city,
            d.created_at,
            v.vehicle_id,
            v.vehicle_class,
            v.vehicle_age_years,
            v.annual_km_declared
        FROM drivers d
        JOIN vehicles v ON d.driver_id = v.driver_id
        WHERE d.driver_id = ?;
        """
        rows = self.execute_query(query, (driver_id,))
        return rows[0] if rows else None

    def get_driver_score(self, driver_id: str) -> dict[str, Any] | None:
        """Fetch 30-day telematics scorecard evaluation."""
        query = """
        SELECT
            driver_id,
            window_start,
            window_end,
            distance_km,
            hard_brake_per_100km,
            hard_accel_per_100km,
            speeding_pct,
            night_pct,
            phone_min_per_100km,
            risk_score,
            risk_band,
            scorecard_version
        FROM gold_driver_risk_score
        WHERE driver_id = ?;
        """
        rows = self.execute_query(query, (driver_id,))
        return rows[0] if rows else None

    def get_driver_quote(self, driver_id: str) -> dict[str, Any] | None:
        """Fetch official issued quote and factor breakdown."""
        query = """
        SELECT
            quote_id,
            driver_id,
            vehicle_id,
            vehicle_class,
            risk_score,
            risk_band,
            base_rate,
            band_multiplier,
            mileage_factor,
            vehicle_age_factor,
            experience_factor,
            monthly_premium,
            annual_premium,
            effective_rate_date,
            generated_at
        FROM quotes
        WHERE driver_id = ?;
        """
        rows = self.execute_query(query, (driver_id,))
        return rows[0] if rows else None

    def get_driver_trips(self, driver_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch recent trips for a driver."""
        query = """
        SELECT
            trip_id,
            driver_id,
            vehicle_id,
            trip_start,
            trip_end,
            distance_km,
            duration_min,
            hard_brake_count,
            hard_accel_count,
            speeding_seconds,
            night_seconds,
            phone_seconds
        FROM silver_trips
        WHERE driver_id = ?
        ORDER BY trip_start DESC
        LIMIT ?;
        """
        return self.execute_query(query, (driver_id, limit))

    def portfolio_summary(self) -> dict[str, Any]:
        """Aggregate portfolio metrics for underwriter overview."""
        query = """
        SELECT
            COUNT(driver_id) AS total_drivers,
            ROUND(AVG(risk_score), 1) AS average_risk_score,
            ROUND(AVG(monthly_premium), 2) AS average_monthly_premium,
            ROUND(SUM(annual_premium), 2) AS total_portfolio_annual_premium
        FROM quotes;
        """
        rows = self.execute_query(query)
        res = rows[0] if rows else {"total_drivers": 0, "average_risk_score": 0.0, "average_monthly_premium": 0.0}

        # Band breakdown
        bands = self.execute_query("""
        SELECT risk_band, COUNT(*) AS count
        FROM quotes
        GROUP BY risk_band
        ORDER BY risk_band;
        """)
        band_dist = {r["risk_band"]: r["count"] for r in bands}

        # Vehicle breakdown
        veh = self.execute_query("""
        SELECT vehicle_class, COUNT(*) AS count
        FROM quotes
        GROUP BY vehicle_class;
        """)
        veh_dist = {r["vehicle_class"]: r["count"] for r in veh}

        # City breakdown
        cities = self.execute_query("""
        SELECT d.city, COUNT(*) AS count
        FROM drivers d
        GROUP BY d.city;
        """)
        city_dist = {r["city"]: r["count"] for r in cities}

        return {
            "total_drivers": res.get("total_drivers", 0),
            "average_risk_score": res.get("average_risk_score", 0.0),
            "average_monthly_premium": res.get("average_monthly_premium", 0.0),
            "total_portfolio_annual_premium": res.get("total_portfolio_annual_premium", 0.0),
            "band_distribution": band_dist,
            "vehicle_distribution": veh_dist,
            "city_distribution": city_dist,
        }
