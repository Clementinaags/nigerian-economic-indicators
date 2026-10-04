-- ============================================================
-- NIGERIAN ECONOMIC INDICATORS PIPELINE
-- Schema: raw → staging → marts
-- Author: Clementina Chukwu | Datara.Insight
-- ============================================================

-- ── DROP TABLES IF REBUILDING ──────────────────────────────
DROP TABLE IF EXISTS marts.fact_inflation CASCADE;
DROP TABLE IF EXISTS marts.fact_exchange_rates CASCADE;
DROP TABLE IF EXISTS staging.stg_inflation CASCADE;
DROP TABLE IF EXISTS staging.stg_exchange_rates CASCADE;
DROP TABLE IF EXISTS marts.dim_currency CASCADE;
DROP TABLE IF EXISTS marts.dim_date CASCADE;
DROP TABLE IF EXISTS raw.raw_cbn_exchange_rates CASCADE;
DROP TABLE IF EXISTS raw.raw_nbs_inflation CASCADE;
DROP TABLE IF EXISTS public.pipeline_assertions CASCADE;
DROP TABLE IF EXISTS public.pipeline_runs CASCADE;

-- ── DROP SCHEMAS ────────────────────────────────────────────
DROP SCHEMA IF EXISTS marts CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;
DROP SCHEMA IF EXISTS raw CASCADE;

-- ── CREATE SCHEMAS ──────────────────────────────────────────
CREATE SCHEMA raw;
CREATE SCHEMA staging;
CREATE SCHEMA marts;

-- ============================================================
-- RAW LAYER
-- Stores data exactly as extracted — no transformation
-- ============================================================

CREATE TABLE raw.raw_cbn_exchange_rates (
    id                  SERIAL PRIMARY KEY,
    extracted_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    rate_date           TEXT,           -- raw date string from CBN
    currency            TEXT,           -- raw currency name from CBN
    buying_rate         TEXT,           -- raw string — may contain commas
    central_rate        TEXT,
    selling_rate        TEXT,
    source_url          TEXT,
    extraction_notes    TEXT            -- any warnings during extraction
);

CREATE TABLE raw.raw_nbs_inflation (
    id                  SERIAL PRIMARY KEY,
    extracted_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    report_period       TEXT,           -- e.g. "September 2025"
    report_year         INTEGER,
    report_month        INTEGER,
    headline_inflation  TEXT,           -- raw string from PDF/Excel
    food_inflation      TEXT,
    core_inflation      TEXT,
    mom_change          TEXT,           -- month on month
    yoy_change          TEXT,           -- year on year
    source_file         TEXT,           -- filename it came from
    extraction_notes    TEXT
);

-- ============================================================
-- STAGING LAYER
-- Cleaned, typed, validated — ready for star schema
-- ============================================================

CREATE TABLE staging.stg_exchange_rates (
    id                  SERIAL PRIMARY KEY,
    rate_date           DATE NOT NULL,
    currency_code       VARCHAR(10) NOT NULL,
    currency_name       VARCHAR(100) NOT NULL,
    buying_rate         NUMERIC(12, 4),
    central_rate        NUMERIC(12, 4),
    selling_rate        NUMERIC(12, 4),
    spread              NUMERIC(12, 4),  -- selling - buying
    is_valid            BOOLEAN DEFAULT TRUE,
    validation_notes    TEXT,
    loaded_at           TIMESTAMP DEFAULT NOW()
);

CREATE TABLE staging.stg_inflation (
    id                  SERIAL PRIMARY KEY,
    report_date         DATE NOT NULL,   -- first day of report month
    report_year         INTEGER NOT NULL,
    report_month        INTEGER NOT NULL,
    report_month_name   VARCHAR(20),
    headline_inflation  NUMERIC(8, 4),
    food_inflation      NUMERIC(8, 4),
    core_inflation      NUMERIC(8, 4),
    mom_change          NUMERIC(8, 4),
    yoy_change          NUMERIC(8, 4),
    rebase_period       VARCHAR(20),     -- 'pre_2024' or 'post_2024'
    is_valid            BOOLEAN DEFAULT TRUE,
    validation_notes    TEXT,
    loaded_at           TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

CREATE TABLE marts.dim_date (
    date_id             SERIAL PRIMARY KEY,
    full_date           DATE NOT NULL UNIQUE,
    year                INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    month_name          VARCHAR(20) NOT NULL,
    quarter             INTEGER NOT NULL,
    quarter_label       VARCHAR(10),     -- e.g. Q1 2024
    day_of_week         INTEGER,
    day_name            VARCHAR(20),
    is_business_day     BOOLEAN DEFAULT TRUE,
    is_weekend          BOOLEAN DEFAULT FALSE
);

CREATE TABLE marts.dim_currency (
    currency_id         SERIAL PRIMARY KEY,
    currency_code       VARCHAR(10) NOT NULL UNIQUE,
    currency_name       VARCHAR(100) NOT NULL,
    region              VARCHAR(100),
    is_major            BOOLEAN DEFAULT FALSE,   -- USD, GBP, EUR, CNY
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- FACT TABLES
-- ============================================================

CREATE TABLE marts.fact_exchange_rates (
    id                  SERIAL PRIMARY KEY,
    date_id             INTEGER REFERENCES marts.dim_date(date_id),
    currency_id         INTEGER REFERENCES marts.dim_currency(currency_id),
    buying_rate         NUMERIC(12, 4) NOT NULL,
    central_rate        NUMERIC(12, 4) NOT NULL,
    selling_rate        NUMERIC(12, 4) NOT NULL,
    spread              NUMERIC(12, 4),
    yoy_change_pct      NUMERIC(8, 4),   -- calculated vs same date prior year
    source              VARCHAR(100) DEFAULT 'CBN',
    loaded_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (date_id, currency_id)
);

CREATE TABLE marts.fact_inflation (
    id                  SERIAL PRIMARY KEY,
    date_id             INTEGER REFERENCES marts.dim_date(date_id),
    headline_inflation  NUMERIC(8, 4) NOT NULL,
    food_inflation      NUMERIC(8, 4),
    core_inflation      NUMERIC(8, 4),
    mom_change          NUMERIC(8, 4),
    yoy_change          NUMERIC(8, 4),
    rebase_period       VARCHAR(20),
    source              VARCHAR(100) DEFAULT 'NBS',
    loaded_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (date_id)
);

-- ============================================================
-- PIPELINE MONITORING TABLES
-- ============================================================

CREATE TABLE public.pipeline_runs (
    id                  SERIAL PRIMARY KEY,
    run_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    pipeline_name       VARCHAR(100) NOT NULL,
    status              VARCHAR(20) NOT NULL,  -- success, failed, partial
    rows_extracted      INTEGER DEFAULT 0,
    rows_loaded         INTEGER DEFAULT 0,
    error_message       TEXT,
    duration_seconds    NUMERIC(10, 2)
);

CREATE TABLE public.pipeline_assertions (
    id                  SERIAL PRIMARY KEY,
    run_id              INTEGER REFERENCES public.pipeline_runs(id),
    checked_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    assertion_name      VARCHAR(200) NOT NULL,
    layer               VARCHAR(50) NOT NULL,   -- raw, staging, marts
    scope               VARCHAR(100),
    rows_checked        INTEGER,
    rows_failed         INTEGER DEFAULT 0,
    status              VARCHAR(10) NOT NULL,   -- PASS, FAIL, WARN
    message             TEXT
);

-- ============================================================
-- SEED DIM_CURRENCY
-- ============================================================

INSERT INTO marts.dim_currency 
    (currency_code, currency_name, region, is_major) 
VALUES
    ('USD', 'US DOLLAR',        'Americas',     TRUE),
    ('GBP', 'POUNDS STERLING',  'Europe',       TRUE),
    ('EUR', 'EURO',             'Europe',       TRUE),
    ('CNY', 'YUAN/RENMINBI',    'Asia',         TRUE),
    ('JPY', 'YEN',              'Asia',         FALSE),
    ('CHF', 'SWISS FRANC',      'Europe',       FALSE),
    ('SAR', 'RIYAL',            'Middle East',  FALSE),
    ('ZAR', 'SOUTH AFRICAN RAND', 'Africa',     FALSE),
    ('DKK', 'DANISH KRONA',     'Europe',       FALSE),
    ('CFA', 'CFA FRANC',        'Africa',       FALSE);