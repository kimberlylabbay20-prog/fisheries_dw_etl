-- ============================================================================
-- fisheries_dw : SQL-side pipeline orchestration
--
-- This wrapper is optional. The Python pipeline performs extraction and
-- cleaning, then stages rows. This script creates the staging objects (if
-- needed), loads the latest CLEANED staging run into the warehouse, and runs
-- read-only quality checks.
--
-- IMPORTANT
--   * Running this script modifies warehouse data through lab2_dw_load.sql.
--   * Review stg.clean_landing first and obtain approval before running it.
--   * This wrapper uses \ir, so the included files resolve relative to this
--     script's directory.
--   * It requires a host psql client, or the database/ directory copied into
--     the PostgreSQL container. The individual SQL files can also be run
--     separately through `docker exec ... psql -f -`.
--
-- Usage:
--   psql -h localhost -p 5434 -U postgres -d fisheries_dw -f database/lab2_etl_pipeline.sql
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

\echo 'Step 1/3: ensuring staging objects exist'
\ir staging_tables.sql

\echo 'Step 2/3: loading the latest CLEANED staging run into dw'
\ir lab2_dw_load.sql

\echo 'Step 3/3: running read-only data quality checks'
\ir data_quality_checks.sql

\echo 'SQL pipeline wrapper finished.'
