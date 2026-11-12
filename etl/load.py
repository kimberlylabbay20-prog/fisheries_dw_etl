"""Warehouse load logic for cleaned staging rows."""

from __future__ import annotations

from typing import Any
from uuid import UUID


class LoadError(RuntimeError):
    """Raised when the warehouse load cannot proceed safely."""


def _scalar(cursor, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return row[0] if row else None


def load_warehouse(connection, run_id: UUID) -> dict[str, Any]:
    """Load one CLEANED staging run into dw dimensions and fact.

    The caller owns the transaction. Commit on success, rollback on failure.
    This function never drops or truncates warehouse tables.
    """
    with connection.cursor() as cursor:
        cursor.execute("LOCK TABLE dw.dim_vessel IN EXCLUSIVE MODE")

        cursor.execute(
            """
            CREATE TEMP TABLE _vessel_batch ON COMMIT DROP AS
            WITH src AS (
                SELECT c.*
                FROM stg.clean_landing c
                WHERE c.run_id = %s
                  AND c.status = 'READY'
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
            LEFT JOIN cur ON cur.vessel_id = b.vessel_id_raw
            """,
            (str(run_id),),
        )

        conflicts = _scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM _vessel_batch
            WHERE cooperative_name_count > 1
               OR vessel_name_count > 1
            """,
        )
        if conflicts:
            raise LoadError(
                "Conflicting vessel names or cooperative names within the batch."
            )

        missing_new = _scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM _vessel_batch
            WHERE current_vessel_key IS NULL
              AND (new_vessel_name IS NULL OR new_cooperative_name IS NULL)
            """,
        )
        if missing_new:
            raise LoadError(
                "A new vessel is missing vessel_name or cooperative_name."
            )

        bad_start = _scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM _vessel_batch
            WHERE current_vessel_key IS NOT NULL
              AND new_cooperative_name IS DISTINCT FROM current_cooperative_name
              AND first_landing_date <= current_start_date
            """,
        )
        if bad_start:
            raise LoadError(
                "A cooperative change starts on or before the current version start date."
            )

        cursor.execute(
            """
            UPDATE dw.dim_vessel v
            SET effective_end_date = b.first_landing_date - 1,
                is_current = FALSE
            FROM _vessel_batch b
            WHERE v.vessel_key = b.current_vessel_key
              AND b.current_vessel_key IS NOT NULL
              AND b.new_cooperative_name IS DISTINCT FROM b.current_cooperative_name
              AND b.first_landing_date > b.current_start_date
            """
        )
        closed_rows = cursor.rowcount

        cursor.execute(
            """
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
                  )
            """
        )
        inserted_versions = cursor.rowcount

        cursor.execute(
            """
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
                %s,
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
                  )
            """,
            (str(run_id),),
        )

        ambiguous_vessel_matches = _scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM (
                SELECT c.stg_id
                FROM stg.clean_landing c
                JOIN dw.dim_vessel v
                  ON v.vessel_id = c.vessel_id_raw
                 AND c.landing_date BETWEEN v.effective_start_date AND v.effective_end_date
                WHERE c.run_id = %s
                  AND c.status = 'READY'
                GROUP BY c.stg_id
                HAVING COUNT(*) > 1
            ) duplicates
            """,
            (str(run_id),),
        )
        if ambiguous_vessel_matches:
            raise LoadError(
                "At least one landing matches more than one vessel version."
            )

        cursor.execute(
            """
            UPDATE stg.clean_landing c
            SET vessel_key = v.vessel_key
            FROM dw.dim_vessel v
            WHERE c.run_id = %s
              AND c.status = 'READY'
              AND v.vessel_id = c.vessel_id_raw
              AND c.landing_date BETWEEN v.effective_start_date AND v.effective_end_date
            """,
            (str(run_id),),
        )

        missing_vessel_keys = _scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM stg.clean_landing
            WHERE run_id = %s
              AND status = 'READY'
              AND vessel_key IS NULL
            """,
            (str(run_id),),
        )
        if missing_vessel_keys:
            raise LoadError(
                f"{missing_vessel_keys} ready rows could not be matched to a vessel version."
            )

        cursor.execute(
            """
            WITH ranked AS (
                SELECT
                    c.stg_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.landing_id
                        ORDER BY c.source_row, c.stg_id
                    ) AS duplicate_rank
                FROM stg.clean_landing c
                WHERE c.run_id = %s
                  AND c.status = 'READY'
                  AND c.landing_id IS NOT NULL
            )
            UPDATE stg.clean_landing c
            SET status = 'REJECTED',
                rejection_reason = 'duplicate landing_id within batch'
            FROM ranked x
            WHERE c.stg_id = x.stg_id
              AND x.duplicate_rank > 1
            """,
            (str(run_id),),
        )

        cursor.execute(
            """
            UPDATE stg.clean_landing c
            SET status = 'REJECTED',
                rejection_reason = 'landing_id already exists in dw.fact_landing'
            WHERE c.run_id = %s
              AND c.status = 'READY'
              AND c.landing_id IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM dw.fact_landing f
                  WHERE f.landing_id = c.landing_id
              )
            """,
            (str(run_id),),
        )

        ready_count = _scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM stg.clean_landing
            WHERE run_id = %s
              AND status = 'READY'
            """,
            (str(run_id),),
        ) or 0

        cursor.execute(
            """
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
            WHERE c.run_id = %s
              AND c.status = 'READY'
              AND c.landing_id IS NOT NULL
            ON CONFLICT (landing_id) DO NOTHING
            """,
            (str(run_id),),
        )
        inserted_with_id = cursor.rowcount

        cursor.execute(
            """
            SELECT setval(
                'dw.fact_landing_landing_id_seq',
                GREATEST(
                    (SELECT COALESCE(MAX(landing_id), 1) FROM dw.fact_landing),
                    (SELECT last_value FROM dw.fact_landing_landing_id_seq)
                )
            )
            """
        )

        cursor.execute(
            """
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
            WHERE c.run_id = %s
              AND c.status = 'READY'
              AND c.landing_id IS NULL
            """,
            (str(run_id),),
        )
        inserted_without_id = cursor.rowcount

        inserted_total = inserted_with_id + inserted_without_id
        if inserted_total != ready_count:
            raise LoadError(
                f"Fact insert count mismatch: ready={ready_count}, inserted={inserted_total}."
            )

        cursor.execute(
            """
            UPDATE stg.clean_landing
            SET status = 'LOADED'
            WHERE run_id = %s
              AND status = 'READY'
            """,
            (str(run_id),),
        )

        cursor.execute(
            """
            UPDATE stg.etl_run_log
            SET status = 'LOADED',
                finished_at = now(),
                loaded_fact_rows = %s,
                rejected_rows = (
                    SELECT COUNT(*)
                    FROM stg.clean_landing
                    WHERE run_id = %s
                      AND status = 'REJECTED'
                ),
                cleaned_rows = (
                    SELECT COUNT(*)
                    FROM stg.clean_landing
                    WHERE run_id = %s
                      AND status IN ('LOADED', 'READY')
                ),
                notes = COALESCE(notes || ' | ', '') || 'Loaded by etl/load.py'
            WHERE run_id = %s
            """,
            (inserted_total, str(run_id), str(run_id), str(run_id)),
        )

    return {
        "run_id": str(run_id),
        "closed_scd_versions": closed_rows,
        "inserted_scd_versions": inserted_versions,
        "inserted_fact_rows": inserted_total,
        "inserted_with_source_id": inserted_with_id,
        "inserted_with_generated_id": inserted_without_id,
    }
