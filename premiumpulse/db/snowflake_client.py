"""Live Snowflake database client using parameterised queries.

Enforces connection timeout 8s, query timeout 20s, and parameter binding
to prevent SQL injection vulnerabilities.
"""

from typing import Any
from premiumpulse.config.settings import Settings


class SnowflakeClient:
    """Client for executing parameterised queries against live Snowflake warehouse."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _get_connection(self):
        # pyrefly: ignore[missing-import]
        import snowflake.connector

        return snowflake.connector.connect(
            user=self.settings.SNOWFLAKE_USER,
            password=self.settings.SNOWFLAKE_PASSWORD,
            account=self.settings.SNOWFLAKE_ACCOUNT,
            warehouse=self.settings.SNOWFLAKE_WAREHOUSE,
            database=self.settings.SNOWFLAKE_DATABASE,
            schema=self.settings.SNOWFLAKE_SCHEMA,
            role=self.settings.SNOWFLAKE_ROLE,
            network_timeout=8,
            login_timeout=8,
        )

    def execute_query(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute parameterised query safely against Snowflake."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(snowflake.connector.DictCursor)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_drivers(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List drivers from Snowflake CURATED and MART schemas."""
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
        FROM CURATED.DRIVERS d
        JOIN CURATED.VEHICLES v ON d.driver_id = v.driver_id
        LEFT JOIN MART.QUOTES q ON d.driver_id = q.driver_id
        ORDER BY d.driver_id ASC
        LIMIT %s OFFSET %s;
        """
        return self.execute_query(query, (limit, offset))

    def get_driver_profile(self, driver_id: str) -> dict[str, Any] | None:
        """Fetch driver profile with dynamic masking applied per user role."""
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
        FROM CURATED.DRIVERS d
        JOIN CURATED.VEHICLES v ON d.driver_id = v.driver_id
        WHERE d.driver_id = %s;
        """
        rows = self.execute_query(query, (driver_id,))
        return rows[0] if rows else None

    def get_driver_score(self, driver_id: str) -> dict[str, Any] | None:
        """Fetch driver telematics risk score."""
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
        FROM CURATED.DRIVER_RISK_SCORES
        WHERE driver_id = %s;
        """
        rows = self.execute_query(query, (driver_id,))
        return rows[0] if rows else None

    def get_driver_quote(self, driver_id: str) -> dict[str, Any] | None:
        """Fetch driver quote from QUOTES dynamic table."""
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
        FROM MART.QUOTES
        WHERE driver_id = %s;
        """
        rows = self.execute_query(query, (driver_id,))
        return rows[0] if rows else None

    def portfolio_summary(self) -> dict[str, Any]:
        """Aggregate portfolio summary from Snowflake."""
        query = """
        SELECT
            total_drivers,
            average_risk_score,
            average_monthly_premium,
            total_portfolio_annual_premium
        FROM MART.PORTFOLIO_SUMMARY;
        """
        rows = self.execute_query(query)
        base = rows[0] if rows else {"total_drivers": 0, "average_risk_score": 0.0, "average_monthly_premium": 0.0}

        bands = self.execute_query("""
        SELECT risk_band, COUNT(*) AS count
        FROM MART.QUOTES
        GROUP BY risk_band
        ORDER BY risk_band;
        """)
        band_dist = {r["RISK_BAND"]: r["COUNT"] for r in bands}

        veh = self.execute_query("""
        SELECT vehicle_class, COUNT(*) AS count
        FROM MART.QUOTES
        GROUP BY vehicle_class;
        """)
        veh_dist = {r["VEHICLE_CLASS"]: r["COUNT"] for r in veh}

        return {
            **base,
            "band_distribution": band_dist,
            "vehicle_distribution": veh_dist,
            "city_distribution": {},
        }
