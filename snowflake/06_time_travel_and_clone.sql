-- ============================================================================
-- PremiumPulse Snowflake Script 06: Time Travel & Zero-Copy Clone
-- ============================================================================

USE WAREHOUSE PP_WH;
USE DATABASE PREMIUMPULSE_DB;

-- 1. Demonstrate Snowflake Time Travel
-- Query quotes exactly 5 minutes ago before any rate update
SELECT
    quote_id,
    driver_id,
    monthly_premium,
    generated_at
FROM MART.QUOTES
AT(OFFSET => -60*5);

-- Inspect rate factors at an exact timestamp
SELECT *
FROM MART.RATE_FACTORS
AT(TIMESTAMP => '2025-01-01 00:00:00'::TIMESTAMP_NTZ);

-- 2. Demonstrate Snowflake Zero-Copy Cloning for Sandbox What-If Scenarios
-- Instantaneous, zero-storage clone of production database for underwriter experimentation
CREATE OR REPLACE DATABASE PREMIUMPULSE_DB_WHATIF
    CLONE PREMIUMPULSE_DB
    COMMENT = 'Zero-copy clone sandbox for actuarial scenario testing';

-- In the cloned database, underwriters can simulate rate updates without affecting production
USE DATABASE PREMIUMPULSE_DB_WHATIF;

UPDATE MART.RATE_FACTORS
SET factor_value = 0.75  -- Deepen Band A discount to 25%
WHERE factor_type = 'BAND_MULTIPLIER' AND factor_key = 'A';

-- Compare quotes between production and clone
SELECT
    prod.driver_id,
    prod.monthly_premium AS prod_premium,
    whatif.monthly_premium AS whatif_premium,
    ROUND(prod.monthly_premium - whatif.monthly_premium, 2) AS savings
FROM PREMIUMPULSE_DB.MART.QUOTES prod
JOIN PREMIUMPULSE_DB_WHATIF.MART.QUOTES whatif ON prod.driver_id = whatif.driver_id
WHERE prod.risk_band = 'A'
LIMIT 10;
