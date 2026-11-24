-- ============================================================================
-- PremiumPulse Snowflake Script 03: Rate Factors Seed Table
-- ============================================================================

USE WAREHOUSE PP_WH;
USE DATABASE PREMIUMPULSE_DB;
USE SCHEMA MART;

CREATE OR REPLACE TABLE MART.RATE_FACTORS (
    factor_type VARCHAR(32) NOT NULL,
    factor_key VARCHAR(32) NOT NULL,
    factor_value NUMBER(10,2) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE NOT NULL,
    PRIMARY KEY (factor_type, factor_key, effective_from)
);

-- Seed Initial Rate Factors
INSERT INTO MART.RATE_FACTORS (factor_type, factor_key, factor_value, effective_from, effective_to)
VALUES
    -- Base rates by vehicle class
    ('BASE_RATE', 'HATCHBACK', 38.00, '2025-01-01', '2099-12-31'),
    ('BASE_RATE', 'SEDAN', 45.00, '2025-01-01', '2099-12-31'),
    ('BASE_RATE', 'SUV', 55.00, '2025-01-01', '2099-12-31'),
    ('BASE_RATE', 'EV', 52.00, '2025-01-01', '2099-12-31'),
    ('BASE_RATE', 'PICKUP', 58.00, '2025-01-01', '2099-12-31'),

    -- Risk Band Multipliers
    ('BAND_MULTIPLIER', 'A', 0.80, '2025-01-01', '2099-12-31'),
    ('BAND_MULTIPLIER', 'B', 0.95, '2025-01-01', '2099-12-31'),
    ('BAND_MULTIPLIER', 'C', 1.10, '2025-01-01', '2099-12-31'),
    ('BAND_MULTIPLIER', 'D', 1.35, '2025-01-01', '2099-12-31'),
    ('BAND_MULTIPLIER', 'E', 1.70, '2025-01-01', '2099-12-31'),
    ('BAND_MULTIPLIER', 'UNRATED', 1.00, '2025-01-01', '2099-12-31'),

    -- Mileage Tiers
    ('MILEAGE_FACTOR', 'TIER_1_8000', 0.92, '2025-01-01', '2099-12-31'),
    ('MILEAGE_FACTOR', 'TIER_2_15000', 1.00, '2025-01-01', '2099-12-31'),
    ('MILEAGE_FACTOR', 'TIER_3_25000', 1.12, '2025-01-01', '2099-12-31'),
    ('MILEAGE_FACTOR', 'TIER_4_ABOVE', 1.25, '2025-01-01', '2099-12-31'),

    -- Vehicle Age Tiers
    ('VEHICLE_AGE_FACTOR', 'AGE_LE_3', 1.05, '2025-01-01', '2099-12-31'),
    ('VEHICLE_AGE_FACTOR', 'AGE_LE_8', 1.00, '2025-01-01', '2099-12-31'),
    ('VEHICLE_AGE_FACTOR', 'AGE_GT_8', 1.08, '2025-01-01', '2099-12-31'),

    -- Driver Experience Tiers
    ('EXPERIENCE_FACTOR', 'EXP_LE_2', 1.25, '2025-01-01', '2099-12-31'),
    ('EXPERIENCE_FACTOR', 'EXP_LE_5', 1.10, '2025-01-01', '2099-12-31'),
    ('EXPERIENCE_FACTOR', 'EXP_GT_5', 1.00, '2025-01-01', '2099-12-31'),

    -- Statutory Premium Clamping
    ('LIMIT', 'MIN_PREMIUM', 25.00, '2025-01-01', '2099-12-31'),
    ('LIMIT', 'MAX_PREMIUM', 220.00, '2025-01-01', '2099-12-31');
