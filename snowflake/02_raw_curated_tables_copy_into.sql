-- ============================================================================
-- PremiumPulse Snowflake Script 02: Raw/Curated Tables & COPY INTO Ingestion
-- ============================================================================

USE WAREHOUSE PP_WH;
USE DATABASE PREMIUMPULSE_DB;

-- 1. Create RAW Staging Tables
CREATE OR REPLACE TABLE RAW.STG_DRIVER_RISK_SCORE (
    driver_id VARCHAR(32),
    window_start DATE,
    window_end DATE,
    distance_km NUMBER(10,2),
    hard_brake_per_100km NUMBER(6,2),
    hard_accel_per_100km NUMBER(6,2),
    speeding_pct NUMBER(5,2),
    night_pct NUMBER(5,2),
    phone_min_per_100km NUMBER(6,2),
    risk_score NUMBER(4,1),
    risk_band VARCHAR(16),
    scorecard_version VARCHAR(16)
);

CREATE OR REPLACE TABLE RAW.STG_DRIVERS (
    driver_id VARCHAR(32),
    full_name VARCHAR(128),
    email VARCHAR(128),
    age_band VARCHAR(16),
    licence_years INTEGER,
    city VARCHAR(64),
    created_at TIMESTAMP_NTZ
);

CREATE OR REPLACE TABLE RAW.STG_VEHICLES (
    vehicle_id VARCHAR(32),
    driver_id VARCHAR(32),
    vehicle_class VARCHAR(32),
    vehicle_age_years INTEGER,
    annual_km_declared INTEGER
);

-- 2. COPY INTO Commands from Internal Stage
-- (Run after uploading Parquet files via SnowSQL: PUT file://... @PREMIUMPULSE_STAGE)
COPY INTO RAW.STG_DRIVER_RISK_SCORE
FROM @RAW.PREMIUMPULSE_STAGE/gold_driver_risk_score
FILE_FORMAT = (FORMAT_NAME = 'RAW.PARQUET_FORMAT')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = 'CONTINUE';

COPY INTO RAW.STG_DRIVERS
FROM @RAW.PREMIUMPULSE_STAGE/gold_dim_driver
FILE_FORMAT = (FORMAT_NAME = 'RAW.PARQUET_FORMAT')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = 'CONTINUE';

COPY INTO RAW.STG_VEHICLES
FROM @RAW.PREMIUMPULSE_STAGE/gold_dim_vehicle
FILE_FORMAT = (FORMAT_NAME = 'RAW.PARQUET_FORMAT')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = 'CONTINUE';

-- 3. Populate CURATED Layer
CREATE OR REPLACE TABLE CURATED.DRIVERS AS
SELECT
    driver_id,
    full_name,
    email,
    age_band,
    licence_years,
    city,
    created_at
FROM RAW.STG_DRIVERS;

CREATE OR REPLACE TABLE CURATED.VEHICLES AS
SELECT
    vehicle_id,
    driver_id,
    UPPER(vehicle_class) AS vehicle_class,
    vehicle_age_years,
    annual_km_declared
FROM RAW.STG_VEHICLES;

CREATE OR REPLACE TABLE CURATED.DRIVER_RISK_SCORES AS
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
    UPPER(risk_band) AS risk_band,
    scorecard_version
FROM RAW.STG_DRIVER_RISK_SCORE;
