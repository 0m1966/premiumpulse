-- ============================================================================
-- PremiumPulse Snowflake Script 01: Setup Database, Warehouse & Schemas
-- ============================================================================

USE ROLE SYSADMIN;

-- 1. Create Dedicated Compute Warehouse
CREATE WAREHOUSE IF NOT EXISTS PP_WH
    WITH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Dedicated compute warehouse for PremiumPulse telematics and pricing mart';

USE WAREHOUSE PP_WH;

-- 2. Create Database
CREATE DATABASE IF NOT EXISTS PREMIUMPULSE_DB
    COMMENT = 'Telematics underwriting and dynamic pricing database';

USE DATABASE PREMIUMPULSE_DB;

-- 3. Create Schemas
CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Staging layer for incoming Databricks Gold exports and Parquet batches';

CREATE SCHEMA IF NOT EXISTS CURATED
    COMMENT = 'Validated, typed driver dimensions, vehicle dimensions and telematics risk scores';

CREATE SCHEMA IF NOT EXISTS MART
    COMMENT = 'Consumption layer holding RATE_FACTORS, QUOTES dynamic table, and executive views';

-- 4. Create Parquet File Format
CREATE OR REPLACE FILE FORMAT RAW.PARQUET_FORMAT
    TYPE = 'PARQUET'
    COMPRESSION = 'AUTO'
    BINARY_AS_TEXT = FALSE;

-- 5. Create Internal Staging Area
CREATE OR REPLACE STAGE RAW.PREMIUMPULSE_STAGE
    FILE_FORMAT = RAW.PARQUET_FORMAT
    COMMENT = 'Internal stage for staging Gold Parquet exports from Databricks';
