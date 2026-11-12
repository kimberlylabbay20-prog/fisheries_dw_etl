-- ============================================================================
-- fisheries_dw : read-only database inspection
-- Safe to run repeatedly. This file contains SELECT statements only.
-- Usage:
--   psql -h localhost -p 5434 -U postgres -d fisheries_dw -f database/inspect_database.sql
-- ============================================================================

\pset pager off

\echo '=== Database and server ==='
SELECT
    current_database() AS database_name,
    current_user AS connected_as,
    current_setting('server_version') AS postgres_version,
    current_setting('TimeZone') AS timezone;

\echo '=== User schemas ==='
SELECT nspname AS schema_name
FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%'
  AND nspname <> 'information_schema'
ORDER BY nspname;

\echo '=== Tables and estimated row counts ==='
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.reltuples::bigint AS estimated_rows,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;

\echo '=== Exact row counts ==='
SELECT 'dw.dim_date' AS table_name, COUNT(*) AS row_count FROM dw.dim_date
UNION ALL
SELECT 'dw.dim_port', COUNT(*) FROM dw.dim_port
UNION ALL
SELECT 'dw.dim_species', COUNT(*) FROM dw.dim_species
UNION ALL
SELECT 'dw.dim_vessel', COUNT(*) FROM dw.dim_vessel
UNION ALL
SELECT 'dw.fact_landing', COUNT(*) FROM dw.fact_landing
ORDER BY table_name;

\echo '=== Columns and data types ==='
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    character_maximum_length,
    numeric_precision,
    numeric_scale
FROM information_schema.columns
WHERE table_schema = 'dw'
ORDER BY table_name, ordinal_position;

\echo '=== Constraints ==='
SELECT
    conrelid::regclass AS table_name,
    conname AS constraint_name,
    CASE contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'c' THEN 'CHECK'
        WHEN 'n' THEN 'NOT NULL'
        ELSE contype::text
    END AS constraint_type,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'dw'::regnamespace
ORDER BY conrelid::regclass::text, conname;

\echo '=== Indexes ==='
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'dw'
ORDER BY tablename, indexname;

\echo '=== Sequences ==='
SELECT
    schemaname,
    sequencename,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    last_value
FROM pg_sequences
WHERE schemaname = 'dw'
ORDER BY sequencename;

\echo '=== Dimension data ranges ==='
SELECT 'dim_date' AS item, MIN(full_date)::text AS min_value, MAX(full_date)::text AS max_value
FROM dw.dim_date
UNION ALL
SELECT 'fact_landing.date_key', MIN(date_key)::text, MAX(date_key)::text
FROM dw.fact_landing;

\echo '=== SCD Type 2 vessel summary ==='
SELECT
    vessel_id,
    COUNT(*) AS version_count,
    COUNT(*) FILTER (WHERE is_current) AS current_versions,
    MIN(effective_start_date) AS first_start_date,
    MAX(effective_end_date) AS last_end_date
FROM dw.dim_vessel
GROUP BY vessel_id
ORDER BY vessel_id;

\echo '=== Current vessel versions ==='
SELECT
    vessel_key,
    vessel_id,
    vessel_name,
    cooperative_name,
    effective_start_date,
    effective_end_date,
    is_current
FROM dw.dim_vessel
WHERE is_current
ORDER BY vessel_id;

\echo '=== Staging schema status (informational) ==='
SELECT
    to_regclass('stg.raw_landing') AS raw_landing_table,
    to_regclass('stg.clean_landing') AS clean_landing_table,
    to_regclass('stg.etl_run_log') AS etl_run_log_table,
    to_regclass('stg.etl_reject_log') AS etl_reject_log_table;
