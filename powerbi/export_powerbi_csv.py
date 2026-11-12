"""Read-only CSV export of the fisheries_dw warehouse for Power BI."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.config import Settings
from etl.db import connect

SCHEMA = "dw"
TABLES = (
    "dim_date",
    "dim_port",
    "dim_species",
    "dim_vessel",
    "fact_landing",
)
FETCH_SIZE = 1000


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
              AND table_type = 'BASE TABLE'
        )
        """,
        (SCHEMA, table),
    )
    return bool(cursor.fetchone()[0])


def _table_columns(cursor, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (SCHEMA, table),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _primary_key_columns(cursor, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s
          AND tc.table_name = %s
        ORDER BY kcu.ordinal_position
        """,
        (SCHEMA, table),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _select_sql(
    table: str,
    columns: Sequence[str],
    order_columns: Sequence[str],
) -> str:
    selected = ", ".join(_quote_identifier(column) for column in columns)
    sql = (
        f"SELECT {selected} "
        f"FROM {_quote_identifier(SCHEMA)}.{_quote_identifier(table)}"
    )
    if order_columns:
        ordered = ", ".join(_quote_identifier(column) for column in order_columns)
        sql += f" ORDER BY {ordered}"
    return sql


def _export_table(cursor, table: str, output_path: Path) -> int:
    columns = _table_columns(cursor, table)
    if not columns:
        raise RuntimeError(f"No columns found for {SCHEMA}.{table}")
    order_columns = _primary_key_columns(cursor, table)
    cursor.execute(_select_sql(table, columns, order_columns))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{table}.",
        suffix=".csv.tmp",
        dir=str(output_path.parent),
    )
    temp_path = Path(temp_name)
    rows_written = 0
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [description[0] for description in cursor.description]
            )
            while True:
                rows = cursor.fetchmany(FETCH_SIZE)
                if not rows:
                    break
                for row in rows:
                    writer.writerow(
                        ["" if value is None else value for value in row]
                    )
                    rows_written += 1
        os.replace(temp_path, output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return rows_written


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export dw.dim_date, dw.dim_port, dw.dim_species, "
            "dw.dim_vessel, and dw.fact_landing to UTF-8 CSV files."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "powerbi",
        help="Directory for the CSV files (default: powerbi/).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = args.output_dir

    try:
        settings = Settings.from_env()
    except Exception as error:
        print(
            f"ERROR: could not load project configuration: {error}",
            file=sys.stderr,
        )
        return 1

    print("Connecting to the configured PostgreSQL database in read-only mode.")
    try:
        connection = connect(settings, readonly=True)
    except Exception as error:
        print(f"ERROR: PostgreSQL connection failed: {error}", file=sys.stderr)
        print(
            "Set FISHERIES_DB_PASSWORD and make sure PostgreSQL/Docker is running.",
            file=sys.stderr,
        )
        return 1

    missing: list[str] = []
    exported: list[tuple[str, Path, int]] = []
    try:
        with connection.cursor() as cursor:
            for table in TABLES:
                if not _table_exists(cursor, table):
                    print(
                        f"SKIP: {SCHEMA}.{table} does not exist.",
                        file=sys.stderr,
                    )
                    missing.append(table)
                    continue
                output_path = output_dir / f"{table}.csv"
                row_count = _export_table(cursor, table, output_path)
                exported.append((table, output_path, row_count))
                print(
                    f"EXPORTED: {SCHEMA}.{table} -> {output_path} "
                    f"({row_count} rows)"
                )
    except Exception as error:
        print(f"ERROR: export failed: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    if missing:
        print(
            "ERROR: missing expected tables: "
            + ", ".join(f"{SCHEMA}.{table}" for table in missing),
            file=sys.stderr,
        )
        return 1

    print(f"Done. Wrote {len(exported)} CSV files to {output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
