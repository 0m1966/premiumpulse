-- ============================================================================
-- PremiumPulse Snowflake Script 04: QUOTES Dynamic Table & Portfolio Views
-- ============================================================================

USE WAREHOUSE PP_WH;
USE DATABASE PREMIUMPULSE_DB;
USE SCHEMA MART;

-- 1. Create QUOTES Dynamic Table
-- Implements the exact same deterministic formula as pricing_engine.py
CREATE OR REPLACE DYNAMIC TABLE MART.QUOTES
    TARGET_LAG = '5 MINUTES'
    WAREHOUSE = PP_WH
AS
WITH base_calcs AS (
    SELECT
        s.driver_id,
        v.vehicle_id,
        v.vehicle_class,
        s.risk_score,
        s.risk_band,

        -- Base rate lookup
        COALESCE(rf_base.factor_value, 45.00) AS base_rate,

        -- Band multiplier lookup
        COALESCE(rf_band.factor_value, 1.00) AS band_multiplier,

        -- Mileage factor lookup
        CASE
            WHEN v.annual_km_declared <= 8000 THEN 0.92
            WHEN v.annual_km_declared <= 15000 THEN 1.00
            WHEN v.annual_km_declared <= 25000 THEN 1.12
            ELSE 1.25
        END AS mileage_factor,

        -- Vehicle age factor lookup
        CASE
            WHEN v.vehicle_age_years <= 3 THEN 1.05
            WHEN v.vehicle_age_years <= 8 THEN 1.00
            ELSE 1.08
        END AS vehicle_age_factor,

        -- Experience factor lookup
        CASE
            WHEN d.licence_years <= 2 THEN 1.25
            WHEN d.licence_years <= 5 THEN 1.10
            ELSE 1.00
        END AS experience_factor,

        '2025-01-01'::DATE AS effective_rate_date

    FROM PREMIUMPULSE_DB.CURATED.DRIVER_RISK_SCORES s
    JOIN PREMIUMPULSE_DB.CURATED.VEHICLES v ON s.driver_id = v.driver_id
    JOIN PREMIUMPULSE_DB.CURATED.DRIVERS d ON s.driver_id = d.driver_id
    LEFT JOIN PREMIUMPULSE_DB.MART.RATE_FACTORS rf_base
        ON rf_base.factor_type = 'BASE_RATE'
        AND rf_base.factor_key = v.vehicle_class
        AND CURRENT_DATE() BETWEEN rf_base.effective_from AND rf_base.effective_to
    LEFT JOIN PREMIUMPULSE_DB.MART.RATE_FACTORS rf_band
        ON rf_band.factor_type = 'BAND_MULTIPLIER'
        AND rf_band.factor_key = s.risk_band
        AND CURRENT_DATE() BETWEEN rf_band.effective_from AND rf_band.effective_to
),
multiplied AS (
    SELECT
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
        effective_rate_date,
        -- Multiplicative product clamped between 25.00 and 220.00
        ROUND(
            LEAST(
                GREATEST(
                    (base_rate * band_multiplier * mileage_factor * vehicle_age_factor * experience_factor),
                    25.00
                ),
                220.00
            ),
            2
        ) AS monthly_premium
    FROM base_calcs
)
SELECT
    CONCAT('QTE-', SUBSTR(driver_id, 5), '-2025') AS quote_id,
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
    ROUND(monthly_premium * 12.0, 2) AS annual_premium,
    effective_rate_date,
    CURRENT_TIMESTAMP() AS generated_at
FROM multiplied;

-- 2. Create Portfolio Summary Aggregate View
CREATE OR REPLACE VIEW MART.PORTFOLIO_SUMMARY AS
SELECT
    COUNT(driver_id) AS total_drivers,
    ROUND(AVG(risk_score), 1) AS average_risk_score,
    ROUND(AVG(monthly_premium), 2) AS average_monthly_premium,
    ROUND(SUM(annual_premium), 2) AS total_portfolio_annual_premium,
    CURRENT_TIMESTAMP() AS refreshed_at
FROM MART.QUOTES;
