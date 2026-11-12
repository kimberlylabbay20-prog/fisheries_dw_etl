"""PostgreSQL helpers for the fisheries ETL pipeline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import UUID

import psycopg2
from psycopg2.extras import Json, execute_values

from .cleaning import (
    CleanRow,
    Dimensions,
    PortRecord,
    SpeciesRecord,
    VesselVersion,
)
from .config import Settings


def connect(settings: Settings, readonly: bool = False):
    connection = psycopg2.connect(**settings.connection_kwargs())
    if readonly:
        connection.set_session(readonly=True)
    return connection


def staging_exists(connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                to_regclass('stg.raw_landing') IS NOT NULL
                AND to_regclass('stg.clean_landing') IS NOT NULL
                AND to_regclass('stg.etl_run_log') IS NOT NULL
                AND to_regclass('stg.etl_reject_log') IS NOT NULL
                AND to_regclass('stg.vessel_change_log') IS NOT NULL
            """
        )
        return bool(cursor.fetchone()[0])


def execute_sql_file(connection, path: Path | str) -> None:
    sql_path = Path(path)
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    sql = sql_path.read_text(encoding="utf-8")
    with connection.cursor() as cursor:
        cursor.execute(sql)


def fetch_dimensions(connection) -> Dimensions:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT port_id, port_name, municipality
            FROM dw.dim_port
            ORDER BY port_id
            """
        )
        ports = [PortRecord(*row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT species_id, species_name
            FROM dw.dim_species
            ORDER BY species_id
            """
        )
        species = [SpeciesRecord(*row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT
                vessel_key,
                vessel_id,
                vessel_name,
                cooperative_name,
                effective_start_date,
                effective_end_date,
                is_current
            FROM dw.dim_vessel
            ORDER BY vessel_id, effective_start_date
            """
        )
        vessels = [VesselVersion(*row) for row in cursor.fetchall()]

        cursor.execute("SELECT date_key FROM dw.dim_date")
        date_keys = {int(row[0]) for row in cursor.fetchall()}

        cursor.execute("SELECT landing_id FROM dw.fact_landing")
        existing_landing_ids = {int(row[0]) for row in cursor.fetchall()}

    return Dimensions(
        ports=ports,
        species=species,
        vessels=vessels,
        date_keys=date_keys,
        existing_landing_ids=existing_landing_ids,
    )


def dimensions_from_json(path: Path | str) -> Dimensions:
    """Load a read-only dimension snapshot for offline dry runs."""
    snapshot_path = Path(path)
    data = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    return Dimensions(
        ports=[
            PortRecord(
                port_id=int(item["port_id"]),
                port_name=str(item["port_name"]),
                municipality=item.get("municipality"),
            )
            for item in data.get("ports", [])
        ],
        species=[
            SpeciesRecord(
                species_id=int(item["species_id"]),
                species_name=str(item["species_name"]),
            )
            for item in data.get("species", [])
        ],
        vessels=[
            VesselVersion(
                vessel_key=int(item["vessel_key"]),
                vessel_id=str(item["vessel_id"]),
                vessel_name=str(item["vessel_name"]),
                cooperative_name=str(item["cooperative_name"]),
                effective_start_date=date.fromisoformat(item["effective_start_date"]),
                effective_end_date=date.fromisoformat(item["effective_end_date"]),
                is_current=bool(item["is_current"]),
            )
            for item in data.get("vessels", [])
        ],
        date_keys={int(value) for value in data.get("date_keys", [])},
        existing_landing_ids={
            int(value) for value in data.get("existing_landing_ids", [])
        },
    )


def create_run(connection, run_id: UUID, source_file: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO stg.etl_run_log (run_id, source_file, status)
            VALUES (%s, %s, 'STARTED')
            """,
            (str(run_id), source_file),
        )


def insert_raw_rows(
    connection,
    run_id: UUID,
    source_file: str,
    rows: Sequence[tuple[int, dict[str, Any]]],
) -> None:
    if not rows:
        return
    values = [
        (str(run_id), source_file, source_row, Json(raw_record))
        for source_row, raw_record in rows
    ]
    with connection.cursor() as cursor:
        execute_values(
            cursor,
            """
            INSERT INTO stg.raw_landing (run_id, source_file, source_row, raw_record)
            VALUES %s
            """,
            values,
            page_size=500,
        )


def insert_clean_rows(connection, run_id: UUID, rows: Iterable[CleanRow]) -> None:
    values = [
        (
            str(run_id),
            row.source_row,
            row.landing_id,
            row.landing_date,
            row.date_key,
            row.port_raw,
            row.port_id,
            row.species_raw,
            row.species_id,
            row.vessel_id_raw,
            row.vessel_name_raw,
            row.cooperative_name_raw,
            row.quantity_kg,
            row.value_php,
            row.status,
            row.rejection_reason,
            row.source_hash,
        )
        for row in rows
    ]
    if not values:
        return
    with connection.cursor() as cursor:
        execute_values(
            cursor,
            """
            INSERT INTO stg.clean_landing (
                run_id,
                source_row,
                landing_id,
                landing_date,
                date_key,
                port_raw,
                port_id,
                species_raw,
                species_id,
                vessel_id_raw,
                vessel_name_raw,
                cooperative_name_raw,
                quantity_kg,
                value_php,
                status,
                rejection_reason,
                source_hash
            )
            VALUES %s
            """,
            values,
            page_size=500,
        )


def insert_reject_logs(
    connection,
    run_id: UUID,
    rows: Iterable[CleanRow],
) -> None:
    values = [
        (str(run_id), row.source_row, row.rejection_reason or "unknown", Json(row.raw_record))
        for row in rows
        if row.status == "REJECTED"
    ]
    if not values:
        return
    with connection.cursor() as cursor:
        execute_values(
            cursor,
            """
            INSERT INTO stg.etl_reject_log (run_id, source_row, reason, raw_record)
            VALUES %s
            """,
            values,
            page_size=500,
        )


def mark_run_cleaned(
    connection,
    run_id: UUID,
    extracted_rows: int,
    cleaned_rows: int,
    rejected_rows: int,
    duplicate_rows: int,
    notes: str | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE stg.etl_run_log
            SET status = 'CLEANED',
                extracted_rows = %s,
                cleaned_rows = %s,
                rejected_rows = %s,
                duplicate_rows = %s,
                notes = %s
            WHERE run_id = %s
            """,
            (
                extracted_rows,
                cleaned_rows,
                rejected_rows,
                duplicate_rows,
                notes,
                str(run_id),
            ),
        )


def mark_run_failed(connection, run_id: UUID, error: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE stg.etl_run_log
            SET status = 'FAILED',
                finished_at = now(),
                notes = %s
            WHERE run_id = %s
            """,
            (error[:2000], str(run_id)),
        )


def latest_cleaned_run(connection) -> UUID | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_id
            FROM stg.etl_run_log
            WHERE status = 'CLEANED'
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        return row[0] if row else None


def fetch_run_summary(connection, run_id: UUID) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
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
                loaded_fact_rows,
                notes
            FROM stg.etl_run_log
            WHERE run_id = %s
            """,
            (str(run_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))
