-- ============================================================================
-- fisheries_dw : load cleaned staging rows into the data warehouse
--
-- PRE-CONDITIONS
--   * database/staging_tables.sql has been run
--   * Python ETL has inserted a completed run with status = 'CLEANED'
--   * stg.clean_landing contains rows with status = 'READY'
--
-- SAFETY
--   * This script does not DROP, TRUNCATE, or DELETE anything.
--   * It updates existing SCD rows and inserts new warehouse rows.
--   * It is wrapped in a transaction. Any error rolls the transaction back.
--   * Run this only after reviewing the staging summary and obtaining approval
--     to modify warehouse data.
--
-- USAGE (manual alternative to etl/load.py)
--   psql -h localhost -p 5434 -U postgres -d fisheries_dw -f database/lab2_dw_load.sql
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

CREATE TEMP TABLE _run ON COMMIT DROP AS
SELECT run_id
FROM stg.etl_run_log
WHERE status = 'CLEANED'
ORDER BY started_at DESC
LIMIT 1;

DO $$
DECLARE
    v_runs integer;
BEGIN
    SELECT COUNT(*) INTO v_runs FROM _run;
    IF v_runs <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one CLEANED run in stg.etl_run_log. Run the Python ETL first.';
    END IF;
END $$;

-- Serialize SCD changes. This does not modify rows by itself.
LOCK TABLE dw.dim_vessel IN EXCLUSIVE MODE;

-- One row per vessel for the current/current-period portion of the batch.
-- Historical rows before the current version's start date are excluded from
-- SCD change detection and are matched to their existing historical version.
CREATE TEMP TABLE _vessel_batch ON COMMIT DROP AS
WITH src AS (
    SELECT c.*
    FROM stg.clean_landing c
    JOIN _run r ON r.run_id = c.run_id
    WHERE c.status = 'READY'
),
cur AS (
    SELECT *
    FROM dw.dim_vessel
    WHERE is_current
),
batch AS (
    SELECT
        s.vessel_id_raw,
        MIN(s.landing_date) AS first_landing_date,
        (ARRAY_AGG(s.vessel_name_raw ORDER BY s.landing_date, s.source_row)
            FILTER (WHERE s.vessel_name_raw IS NOT NULL))[1] AS vessel_name_raw,
        (ARRAY_AGG(s.cooperative_name_raw ORDER BY s.landing_date, s.source_row)
            FILTER (WHERE s.cooperative_name_raw IS NOT NULL))[1] AS cooperative_name_raw,
        COUNT(DISTINCT s.cooperative_name_raw) AS cooperative_name_count,
        COUNT(DISTINCT s.vessel_name_raw) AS vessel_name_count
    FROM src s
    LEFT JOIN cur ON cur.vessel_id = s.vessel_id_raw
    WHERE cur.vessel_key IS NULL
       OR s.landing_date >= cur.effective_start_date
    GROUP BY s.vessel_id_raw
)
SELECT
    b.*,
    cur.vessel_key AS current_vessel_key,
    cur.vessel_name AS current_vessel_name,
    cur.cooperative_name AS current_cooperative_name,
    cur.effective_start_date AS current_start_date,
    COALESCE(b.vessel_name_raw, cur.vessel_name) AS new_vessel_name,
    COALESCE(b.cooperative_name_raw, cur.cooperative_name) AS new_cooperative_name
FROM batch b
LEFT JOIN cur ON cur.vessel_id = b.vessel_id_raw;

DO $$
DECLARE
    v_conflicts integer;
    v_missing_new integer;
    v_bad_start integer;
BEGIN
    SELECT COUNT(*) INTO v_conflicts
    FROM _vessel_batch
    WHERE cooperative_name_count > 1
       OR vessel_name_count > 1;

    IF v_conflicts > 0 THEN
        RAISE EXCEPTION
            'Conflicting vessel names or cooperative names within the batch. Review stg.clean_landing.';
    END IF;

    SELECT COUNT(*) INTO v_missing_new
    FROM _vessel_batch
    WHERE current_vessel_key IS NULL
      AND (new_vessel_name IS NULL OR new_cooperative_name IS NULL);

    IF v_missing_new > 0 THEN
        RAISE EXCEPTION
            'A new vessel is missing vessel_name or cooperative_name. Cannot create a new dimension row.';
    END IF;

    SELECT COUNT(*) INTO v_bad_start
    FROM _vessel_batch
    WHERE current_vessel_key IS NOT NULL
      AND new_cooperative_name IS DISTINCT FROM current_cooperative_name
      AND first_landing_date <= current_start_date;

    IF v_bad_start > 0 THEN
        RAISE EXCEPTION
            'A cooperative change starts on or before the current version start date. Resolve the SCD history manually.';
    END IF;
END $$;

-- Close the current version when a cooperative change is detected.
UPDATE dw.dim_vessel v
SET effective_end_date = b.first_landing_date - 1,
    is_current = FALSE
FROM _vessel_batch b
WHERE v.vessel_key = b.current_vessel_key
  AND b.current_vessel_key IS NOT NULL
  AND b.new_cooperative_name IS DISTINCT FROM b.current_cooperative_name
  AND b.first_landing_date > b.current_start_date;

-- Insert new current versions for new vessels or changed vessels.
INSERT INTO dw.dim_vessel (
    vessel_key,
    vessel_id,
    vessel_name,
    cooperative_name,
    effective_start_date,
    effective_end_date,
    is_current
)
SELECT
    nextval('dw.dim_vessel_vessel_key_seq'),
    b.vessel_id_raw,
    b.new_vessel_name,
    b.new_cooperative_name,
    b.first_landing_date,
    DATE '9999-12-31',
    TRUE
FROM _vessel_batch b
WHERE b.current_vessel_key IS NULL
   OR (
        b.first_landing_date > b.current_start_date
        AND b.new_cooperative_name IS DISTINCT FROM b.current_cooperative_name
      );

-- Audit the SCD changes made in this run.
INSERT INTO stg.vessel_change_log (
    run_id,
    vessel_id,
    old_vessel_key,
    new_vessel_key,
    old_cooperative_name,
    new_cooperative_name,
    effective_start_date,
    effective_end_date
)
SELECT
    (SELECT run_id FROM _run),
    b.vessel_id_raw,
    b.current_vessel_key,
    v.vessel_key,
    b.current_cooperative_name,
    b.new_cooperative_name,
    v.effective_start_date,
    v.effective_end_date
FROM _vessel_batch b
JOIN dw.dim_vessel v
  ON v.vessel_id = b.vessel_id_raw
 AND v.is_current
WHERE b.current_vessel_key IS NULL
   OR (
        b.first_landing_date > b.current_start_date
        AND b.new_cooperative_name IS DISTINCT FROM b.current_cooperative_name
      );

-- Fail safely before matching if any ready row matches more than one vessel version.
DO $$
DECLARE
    v_ambiguous integer;
BEGIN
    SELECT COUNT(*) INTO v_ambiguous
    FROM (
        SELECT c.stg_id
        FROM stg.clean_landing c
        JOIN _run r ON r.run_id = c.run_id
        JOIN dw.dim_vessel v
          ON v.vessel_id = c.vessel_id_raw
         AND c.landing_date BETWEEN v.effective_start_date AND v.effective_end_date
        WHERE c.status = 'READY'
        GROUP BY c.stg_id
        HAVING COUNT(*) > 1
    ) d;

    IF v_ambiguous > 0 THEN
        RAISE EXCEPTION
            '% ready rows match more than one vessel version. Review SCD history.',
            v_ambiguous;
    END IF;
END $$;

-- Match every ready row to the vessel version whose date range contains it.
UPDATE stg.clean_landing c
SET vessel_key = v.vessel_key
FROM dw.dim_vessel v
WHERE c.run_id = (SELECT run_id FROM _run)
  AND c.status = 'READY'
  AND v.vessel_id = c.vessel_id_raw
  AND c.landing_date BETWEEN v.effective_start_date AND v.effective_end_date;

DO $$
DECLARE
    v_missing integer;
BEGIN
    SELECT COUNT(*) INTO v_missing
    FROM stg.clean_landing c
    WHERE c.run_id = (SELECT run_id FROM _run)
      AND c.status = 'READY'
      AND c.vessel_key IS NULL;

    IF v_missing > 0 THEN
        RAISE EXCEPTION
            '% ready rows could not be matched to a vessel version. Check vessel dates and SCD history.',
            v_missing;
    END IF;
END $$;

-- Reject duplicate landing_id values within the batch, keeping the first.
WITH ranked AS (
    SELECT
        c.stg_id,
        ROW_NUMBER() OVER (
            PARTITION BY c.landing_id
            ORDER BY c.source_row, c.stg_id
        ) AS duplicate_rank
    FROM stg.clean_landing c
    JOIN _run r ON r.run_id = c.run_id
    WHERE c.status = 'READY'
      AND c.landing_id IS NOT NULL
)
UPDATE stg.clean_landing c
SET status = 'REJECTED',
    rejection_reason = 'duplicate landing_id within batch'
FROM ranked x
WHERE c.stg_id = x.stg_id
  AND x.duplicate_rank > 1;

-- Reject landing_id values that already exist in the warehouse.
UPDATE stg.clean_landing c
SET status = 'REJECTED',
    rejection_reason = 'landing_id already exists in dw.fact_landing'
FROM _run r
WHERE c.run_id = r.run_id
  AND c.status = 'READY'
  AND c.landing_id IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM dw.fact_landing f
      WHERE f.landing_id = c.landing_id
  );

-- Capture the ready-row count and the pre-load fact count so the script can
-- verify that every ready row was actually inserted.
CREATE TEMP TABLE _ready_check ON COMMIT DROP AS
SELECT COUNT(*) AS ready_rows
FROM stg.clean_landing c
JOIN _run r ON r.run_id = c.run_id
WHERE c.status = 'READY';

CREATE TEMP TABLE _fact_before ON COMMIT DROP AS
SELECT COUNT(*) AS fact_rows FROM dw.fact_landing;

-- Insert source-supplied landing IDs.
INSERT INTO dw.fact_landing (
    landing_id,
    date_key,
    port_id,
    species_id,
    vessel_key,
    quantity_kg,
    value_php
)
OVERRIDING SYSTEM VALUE
SELECT
    c.landing_id,
    c.date_key,
    c.port_id,
    c.species_id,
    c.vessel_key,
    c.quantity_kg,
    c.value_php
FROM stg.clean_landing c
JOIN _run r ON r.run_id = c.run_id
WHERE c.status = 'READY'
  AND c.landing_id IS NOT NULL
ON CONFLICT (landing_id) DO NOTHING;

-- Keep the identity sequence ahead of explicitly loaded landing IDs.
SELECT setval(
    'dw.fact_landing_landing_id_seq',
    GREATEST(
        (SELECT COALESCE(MAX(landing_id), 1) FROM dw.fact_landing),
        (SELECT last_value FROM dw.fact_landing_landing_id_seq)
    )
);

-- Insert rows without a source landing ID using the existing warehouse sequence.
INSERT INTO dw.fact_landing (
    landing_id,
    date_key,
    port_id,
    species_id,
    vessel_key,
    quantity_kg,
    value_php
)
OVERRIDING SYSTEM VALUE
SELECT
    nextval('dw.fact_landing_landing_id_seq'),
    c.date_key,
    c.port_id,
    c.species_id,
    c.vessel_key,
    c.quantity_kg,
    c.value_php
FROM stg.clean_landing c
JOIN _run r ON r.run_id = c.run_id
WHERE c.status = 'READY'
  AND c.landing_id IS NULL;

-- Fail safely if the number of inserted fact rows differs from the ready count.
DO $$
DECLARE
    v_ready integer;
    v_before bigint;
    v_after bigint;
BEGIN
    SELECT ready_rows INTO v_ready FROM _ready_check;
    SELECT fact_rows INTO v_before FROM _fact_before;
    SELECT COUNT(*) INTO v_after FROM dw.fact_landing;

    IF (v_after - v_before) <> v_ready THEN
        RAISE EXCEPTION
            'Fact insert count mismatch: ready=%, inserted=%.',
            v_ready, v_after - v_before;
    END IF;
END $$;

-- Mark successfully loaded rows.
UPDATE stg.clean_landing c
SET status = 'LOADED'
FROM _run r
WHERE c.run_id = r.run_id
  AND c.status = 'READY';

-- Update the execution summary.
UPDATE stg.etl_run_log l
SET status = 'LOADED',
    finished_at = now(),
    loaded_fact_rows = (
        SELECT COUNT(*)
        FROM stg.clean_landing c
        WHERE c.run_id = l.run_id
          AND c.status = 'LOADED'
    ),
    rejected_rows = (
        SELECT COUNT(*)
        FROM stg.clean_landing c
        WHERE c.run_id = l.run_id
          AND c.status = 'REJECTED'
    ),
    cleaned_rows = (
        SELECT COUNT(*)
        FROM stg.clean_landing c
        WHERE c.run_id = l.run_id
          AND c.status IN ('LOADED', 'READY')
    ),
    notes = COALESCE(notes || ' | ', '') || 'Loaded by database/lab2_dw_load.sql'
WHERE l.run_id = (SELECT run_id FROM _run);

COMMIT;

\echo 'Warehouse load completed. Review stg.etl_run_log and run database/data_quality_checks.sql.'
