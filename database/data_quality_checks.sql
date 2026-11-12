-- ============================================================================
-- fisheries_dw : read-only data quality checks
--
-- This file contains SELECT statements only. It does not modify data.
-- Staging checks run only when the stg schema has been created.
--
-- Usage:
--   psql -h localhost -p 5434 -U postgres -d fisheries_dw -f database/data_quality_checks.sql
-- ============================================================================

\pset pager off
\set ON_ERROR_STOP on

\echo '=== 1. Warehouse row counts ==='
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

\echo '=== 2. Fact table numeric summary ==='
SELECT
    COUNT(*) AS fact_rows,
    MIN(quantity_kg) AS min_quantity_kg,
    MAX(quantity_kg) AS max_quantity_kg,
    SUM(quantity_kg) AS total_quantity_kg,
    MIN(value_php) AS min_value_php,
    MAX(value_php) AS max_value_php,
    SUM(value_php) AS total_value_php
FROM dw.fact_landing;

\echo '=== 3. Orphan foreign keys ==='
SELECT 'fact_landing -> dim_date' AS relationship, COUNT(*) AS orphan_rows
FROM dw.fact_landing f
LEFT JOIN dw.dim_date d ON d.date_key = f.date_key
WHERE d.date_key IS NULL
UNION ALL
SELECT 'fact_landing -> dim_port', COUNT(*)
FROM dw.fact_landing f
LEFT JOIN dw.dim_port p ON p.port_id = f.port_id
WHERE p.port_id IS NULL
UNION ALL
SELECT 'fact_landing -> dim_species', COUNT(*)
FROM dw.fact_landing f
LEFT JOIN dw.dim_species s ON s.species_id = f.species_id
WHERE s.species_id IS NULL
UNION ALL
SELECT 'fact_landing -> dim_vessel', COUNT(*)
FROM dw.fact_landing f
LEFT JOIN dw.dim_vessel v ON v.vessel_key = f.vessel_key
WHERE v.vessel_key IS NULL;

\echo '=== 4. Duplicate checks ==='
SELECT 'duplicate fact landing_id' AS check_name, COUNT(*) AS issue_groups
FROM (
    SELECT landing_id
    FROM dw.fact_landing
    GROUP BY landing_id
    HAVING COUNT(*) > 1
) d
UNION ALL
SELECT 'exact duplicate fact rows', COUNT(*)
FROM (
    SELECT date_key, port_id, species_id, vessel_key, quantity_kg, value_php
    FROM dw.fact_landing
    GROUP BY date_key, port_id, species_id, vessel_key, quantity_kg, value_php
    HAVING COUNT(*) > 1
) d
UNION ALL
SELECT 'duplicate dim_port name + municipality', COUNT(*)
FROM (
    SELECT port_name, municipality
    FROM dw.dim_port
    GROUP BY port_name, municipality
    HAVING COUNT(*) > 1
) d
UNION ALL
SELECT 'duplicate dim_species name', COUNT(*)
FROM (
    SELECT species_name
    FROM dw.dim_species
    GROUP BY species_name
    HAVING COUNT(*) > 1
) d;

\echo '=== 5. Dimension duplicate detail ==='
SELECT port_id, port_name, municipality
FROM dw.dim_port
WHERE (port_name, municipality) IN (
    SELECT port_name, municipality
    FROM dw.dim_port
    GROUP BY port_name, municipality
    HAVING COUNT(*) > 1
)
ORDER BY port_name, municipality, port_id;

\echo '=== 6. SCD Type 2 integrity ==='
SELECT 'current rows per vessel > 1' AS check_name, COUNT(*) AS issue_count
FROM (
    SELECT vessel_id
    FROM dw.dim_vessel
    WHERE is_current
    GROUP BY vessel_id
    HAVING COUNT(*) > 1
) d
UNION ALL
SELECT 'vessels with no current row', COUNT(*)
FROM (
    SELECT vessel_id
    FROM dw.dim_vessel
    GROUP BY vessel_id
    HAVING COUNT(*) FILTER (WHERE is_current) = 0
) d
UNION ALL
SELECT 'invalid date range', COUNT(*)
FROM dw.dim_vessel
WHERE effective_end_date < effective_start_date
UNION ALL
SELECT 'current row with non-sentinel end date', COUNT(*)
FROM dw.dim_vessel
WHERE is_current
  AND effective_end_date <> DATE '9999-12-31';

\echo '=== 7. Overlapping SCD Type 2 date ranges ==='
SELECT
    a.vessel_id,
    a.vessel_key AS first_vessel_key,
    a.effective_start_date AS first_start,
    a.effective_end_date AS first_end,
    b.vessel_key AS second_vessel_key,
    b.effective_start_date AS second_start,
    b.effective_end_date AS second_end
FROM dw.dim_vessel a
JOIN dw.dim_vessel b
  ON a.vessel_id = b.vessel_id
 AND a.vessel_key < b.vessel_key
 AND a.effective_start_date <= b.effective_end_date
 AND b.effective_start_date <= a.effective_end_date
ORDER BY a.vessel_id, a.effective_start_date, b.effective_start_date;

\echo '=== 8. Fact date coverage by month ==='
SELECT
    d.year,
    d.month,
    d.month_name,
    COUNT(*) AS fact_rows,
    ROUND(SUM(f.quantity_kg), 2) AS total_quantity_kg,
    ROUND(SUM(f.value_php), 2) AS total_value_php
FROM dw.fact_landing f
JOIN dw.dim_date d ON d.date_key = f.date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

-- Optional staging checks. The \if block is skipped when staging is absent.
SELECT to_regclass('stg.clean_landing') IS NOT NULL AS has_staging \gset

\if :has_staging

\echo '=== 9. Latest staging run ==='
SELECT
    run_id,
    source_file,
    started_at,
    finished_at,
    status,
    extracted_rows,
    cleaned_rows,
    rejected_rows,
    duplicate_rows,
    loaded_fact_rows
FROM stg.etl_run_log
ORDER BY started_at DESC
LIMIT 5;

\echo '=== 10. Staging row status for latest run ==='
SELECT
    status,
    COUNT(*) AS row_count
FROM stg.clean_landing
WHERE run_id = (
    SELECT run_id
    FROM stg.etl_run_log
    ORDER BY started_at DESC
    LIMIT 1
)
GROUP BY status
ORDER BY status;

\echo '=== 11. Staging rejection reasons for latest run ==='
SELECT
    rejection_reason,
    COUNT(*) AS row_count
FROM stg.clean_landing
WHERE run_id = (
    SELECT run_id
    FROM stg.etl_run_log
    ORDER BY started_at DESC
    LIMIT 1
)
  AND status = 'REJECTED'
GROUP BY rejection_reason
ORDER BY row_count DESC, rejection_reason;

\echo '=== 12. Staging referential integrity for latest run ==='
SELECT 'ready rows without date_key' AS check_name, COUNT(*) AS issue_count
FROM stg.clean_landing
WHERE run_id = (SELECT run_id FROM stg.etl_run_log ORDER BY started_at DESC LIMIT 1)
  AND status = 'READY'
  AND date_key IS NULL
UNION ALL
SELECT 'ready rows without port_id', COUNT(*)
FROM stg.clean_landing
WHERE run_id = (SELECT run_id FROM stg.etl_run_log ORDER BY started_at DESC LIMIT 1)
  AND status = 'READY'
  AND port_id IS NULL
UNION ALL
SELECT 'ready rows without species_id', COUNT(*)
FROM stg.clean_landing
WHERE run_id = (SELECT run_id FROM stg.etl_run_log ORDER BY started_at DESC LIMIT 1)
  AND status = 'READY'
  AND species_id IS NULL
UNION ALL
SELECT 'ready rows without vessel_key', COUNT(*)
FROM stg.clean_landing
WHERE run_id = (SELECT run_id FROM stg.etl_run_log ORDER BY started_at DESC LIMIT 1)
  AND status = 'READY'
  AND vessel_key IS NULL;

\endif

\echo '=== Data quality check script finished ==='
