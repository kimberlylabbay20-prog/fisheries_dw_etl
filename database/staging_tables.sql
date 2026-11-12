-- ============================================================================
-- fisheries_dw : staging tables for the Lab 2 / Lab 3 ETL pipeline
--
-- This script is additive only:
--   * no DROP
--   * no TRUNCATE
--   * no DELETE
--   * no changes to existing dw tables
--
-- Run this once before loading CSV data into staging.
-- Usage:
--   psql -h localhost -p 5434 -U postgres -d fisheries_dw -f database/staging_tables.sql
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS stg;

-- Raw CSV records are kept as JSONB so the pipeline can preserve the original
-- row even when the source file has extra or renamed columns.
CREATE TABLE IF NOT EXISTS stg.raw_landing (
    raw_id       bigserial PRIMARY KEY,
    run_id       uuid        NOT NULL,
    source_file  text        NOT NULL,
    source_row   integer     NOT NULL,
    raw_record   jsonb       NOT NULL,
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_landing_run
    ON stg.raw_landing (run_id);

CREATE INDEX IF NOT EXISTS idx_raw_landing_run_row
    ON stg.raw_landing (run_id, source_row);

-- One row per source record after extraction and cleaning. Rows that cannot be
-- loaded remain in this table with status = 'REJECTED' and a reason.
CREATE TABLE IF NOT EXISTS stg.clean_landing (
    stg_id               bigserial PRIMARY KEY,
    run_id               uuid        NOT NULL,
    source_row           integer     NOT NULL,
    landing_id           bigint,
    landing_date         date,
    date_key             integer,
    port_raw             text,
    port_id              integer,
    species_raw          text,
    species_id           integer,
    vessel_id_raw        text,
    vessel_name_raw      text,
    cooperative_name_raw text,
    quantity_kg          numeric(12,2),
    value_php            numeric(14,2),
    vessel_key           bigint,
    status               varchar(20) NOT NULL DEFAULT 'READY'
        CHECK (status IN ('READY', 'REJECTED', 'LOADED', 'SKIPPED')),
    rejection_reason     text,
    source_hash          char(64),
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clean_landing_run
    ON stg.clean_landing (run_id);

CREATE INDEX IF NOT EXISTS idx_clean_landing_run_status
    ON stg.clean_landing (run_id, status);

CREATE INDEX IF NOT EXISTS idx_clean_landing_landing_id
    ON stg.clean_landing (landing_id);

CREATE INDEX IF NOT EXISTS idx_clean_landing_vessel
    ON stg.clean_landing (vessel_id_raw);

-- One row per pipeline execution.
CREATE TABLE IF NOT EXISTS stg.etl_run_log (
    run_id            uuid PRIMARY KEY,
    source_file       text NOT NULL,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    status            varchar(20) NOT NULL
        CHECK (status IN ('STARTED', 'STAGED', 'CLEANED', 'LOADED', 'FAILED', 'DRY_RUN')),
    extracted_rows    integer NOT NULL DEFAULT 0,
    cleaned_rows      integer NOT NULL DEFAULT 0,
    rejected_rows     integer NOT NULL DEFAULT 0,
    duplicate_rows    integer NOT NULL DEFAULT 0,
    loaded_fact_rows  integer NOT NULL DEFAULT 0,
    notes             text
);

-- Rejected source records with enough context for debugging.
CREATE TABLE IF NOT EXISTS stg.etl_reject_log (
    reject_id   bigserial PRIMARY KEY,
    run_id      uuid        NOT NULL,
    source_row  integer     NOT NULL,
    reason      text        NOT NULL,
    raw_record  jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reject_log_run
    ON stg.etl_reject_log (run_id);

-- Audit trail for SCD Type 2 changes made by the load step.
CREATE TABLE IF NOT EXISTS stg.vessel_change_log (
    change_id            bigserial PRIMARY KEY,
    run_id               uuid        NOT NULL,
    vessel_id            text        NOT NULL,
    old_vessel_key       bigint,
    new_vessel_key       bigint,
    old_cooperative_name text,
    new_cooperative_name text,
    effective_start_date date,
    effective_end_date   date,
    changed_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vessel_change_log_run
    ON stg.vessel_change_log (run_id);

COMMENT ON SCHEMA stg IS 'Staging and audit objects for the fisheries ETL pipeline.';
COMMENT ON TABLE stg.raw_landing IS 'Original CSV records preserved as JSONB.';
COMMENT ON TABLE stg.clean_landing IS 'Cleaned source records with validation status.';
COMMENT ON TABLE stg.etl_run_log IS 'One row per ETL execution with row-count summary.';
COMMENT ON TABLE stg.etl_reject_log IS 'Rejected records and rejection reasons.';
COMMENT ON TABLE stg.vessel_change_log IS 'Audit trail for SCD Type 2 vessel changes.';
