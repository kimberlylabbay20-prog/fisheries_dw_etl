"""Command-line ETL pipeline for the fisheries data warehouse."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

from . import db
from .cleaning import CleaningOptions, CleanResult, clean_rows
from .config import STAGING_SQL, Settings
from .extract import extract_csv
from .load import load_warehouse


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--limit must be an integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("--limit must be greater than or equal to 0")
    return number


def _rejection_summary(result: CleanResult, limit: int = 10) -> list[tuple[str, int]]:
    counter = Counter(
        row.rejection_reason or "unknown"
        for row in result.rows
        if row.status == "REJECTED"
    )
    return counter.most_common(limit)


def _print_summary(result: CleanResult, extracted_path: Path) -> None:
    print(f"Dataset: {extracted_path}")
    print(f"Extracted rows: {result.extracted_rows}")
    print(f"Ready rows: {result.ready_rows}")
    print(f"Rejected rows: {result.rejected_rows}")
    print(f"Duplicate rows: {result.duplicate_rows}")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings[:10]:
            print(f"  - {warning}")

    rejection_summary = _rejection_summary(result)
    if rejection_summary:
        print("\nTop rejection reasons:")
        for reason, count in rejection_summary:
            print(f"  - {count}: {reason}")

    rejected_examples = [
        row for row in result.rows if row.status == "REJECTED"
    ][:5]
    if rejected_examples:
        print("\nRejected examples:")
        for row in rejected_examples:
            print(
                f"  - source row {row.source_row}: "
                f"{row.rejection_reason}"
            )


def _result_to_dict(result: CleanResult, path: Path) -> dict:
    return {
        "dataset": str(path),
        "extracted_rows": result.extracted_rows,
        "ready_rows": result.ready_rows,
        "rejected_rows": result.rejected_rows,
        "duplicate_rows": result.duplicate_rows,
        "warnings": result.warnings,
        "rejection_reasons": [
            {"reason": reason, "count": count}
            for reason, count in _rejection_summary(result, limit=50)
        ],
    }


def _write_json_summary(path: str | None, payload: dict) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    dataset_path = Path(args.csv) if args.csv else settings.dataset

    try:
        extracted = extract_csv(dataset_path)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        print(
            "The required instructor dataset is not available. "
            "Place messy_landings_2026.csv in datasets/ or pass --csv.",
            file=sys.stderr,
        )
        return 2
    except Exception as error:  # noqa: BLE001 - CLI should report a clear error
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.limit is not None:
        extracted.rows = extracted.rows[: args.limit]

    print(f"Reading: {extracted.path}")
    print(f"Encoding: {extracted.encoding}; delimiter: {extracted.delimiter!r}")
    print(f"Source rows: {len(extracted.rows)}")
    if extracted.blank_rows_skipped:
        print(f"Blank rows skipped: {extracted.blank_rows_skipped}")

    connection = None
    try:
        if args.dimensions_json:
            if not args.dry_run:
                print(
                    "ERROR: --dimensions-json is only supported with --dry-run.",
                    file=sys.stderr,
                )
                return 1
            dimensions = db.dimensions_from_json(args.dimensions_json)
        else:
            try:
                connection = db.connect(settings, readonly=args.dry_run)
            except Exception as error:  # noqa: BLE001
                print(
                    f"ERROR: could not connect to PostgreSQL: {error}",
                    file=sys.stderr,
                )
                print(
                    "Set FISHERIES_DB_HOST, FISHERIES_DB_PORT, FISHERIES_DB_NAME, "
                    "FISHERIES_DB_USER, and FISHERIES_DB_PASSWORD.",
                    file=sys.stderr,
                )
                return 1
            dimensions = db.fetch_dimensions(connection)

        result = clean_rows(
            extracted.rows,
            settings.column_mapping,
            dimensions,
            CleaningOptions(
                date_dayfirst=args.date_dayfirst,
                port_aliases=settings.value_mappings.get("ports", {}),
                species_aliases=settings.value_mappings.get("species", {}),
                cooperative_aliases=settings.value_mappings.get("cooperatives", {}),
            ),
        )
    except Exception as error:  # noqa: BLE001
        if connection is not None:
            connection.close()
        print(f"ERROR during cleaning: {error}", file=sys.stderr)
        return 1

    _print_summary(result, extracted.path)
    summary = _result_to_dict(result, extracted.path)

    if args.dry_run:
        try:
            _write_json_summary(args.json_summary, summary)
            print("\nDry run complete. No database rows were written.")
            return 0
        finally:
            if connection is not None:
                connection.close()

    if connection is None:
        print("ERROR: database connection is required for staging.", file=sys.stderr)
        return 1

    try:
        if args.init_staging:
            with connection:
                db.execute_sql_file(connection, STAGING_SQL)
            print("Staging tables created or verified.")

        if not db.staging_exists(connection):
            connection.close()
            print(
                "ERROR: staging tables do not exist. "
                "Run database/staging_tables.sql or pass --init-staging.",
                file=sys.stderr,
            )
            return 1

        run_id = uuid4()
        try:
            with connection:
                db.create_run(connection, run_id, str(extracted.path))
                db.insert_raw_rows(
                    connection,
                    run_id,
                    str(extracted.path),
                    extracted.rows,
                )
                db.insert_clean_rows(connection, run_id, result.rows)
                db.insert_reject_logs(connection, run_id, result.rows)
                db.mark_run_cleaned(
                    connection,
                    run_id,
                    extracted_rows=result.extracted_rows,
                    cleaned_rows=result.ready_rows,
                    rejected_rows=result.rejected_rows,
                    duplicate_rows=result.duplicate_rows,
                    notes="Staged by etl/pipeline.py",
                )
        except Exception as error:  # noqa: BLE001
            connection.close()
            print(f"ERROR while staging: {error}", file=sys.stderr)
            return 1

        summary["run_id"] = str(run_id)
        _write_json_summary(args.json_summary, summary)
        print(f"\nStaged run_id: {run_id}")

        if args.skip_load:
            connection.close()
            print("Load skipped. Review stg.clean_landing before loading.")
            return 0

        try:
            with connection:
                load_summary = load_warehouse(connection, run_id)
        except Exception as error:  # noqa: BLE001
            try:
                with connection:
                    db.mark_run_failed(connection, run_id, str(error))
            except Exception:
                pass
            connection.close()
            print(f"ERROR during warehouse load: {error}", file=sys.stderr)
            print("The warehouse transaction was rolled back.", file=sys.stderr)
            return 1

        connection.close()
        print("\nWarehouse load complete:")
        print(json.dumps(load_summary, indent=2, default=str))
        return 0
    finally:
        try:
            connection.close()
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(
        description="Extract, clean, stage, and load fisheries landing data."
    )
    parser.add_argument(
        "--csv",
        default=str(settings.dataset),
        help="Path to the source CSV (default: datasets/messy_landings_2026.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and clean only; do not write to the database",
    )
    parser.add_argument(
        "--dimensions-json",
        default=None,
        help="Use a read-only dimension snapshot JSON for an offline dry run",
    )
    parser.add_argument(
        "--init-staging",
        action="store_true",
        help="Create/verify staging tables before staging",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Stage and validate, but do not load the warehouse",
    )
    parser.add_argument(
        "--date-dayfirst",
        action="store_true",
        default=settings.date_dayfirst,
        help="Interpret ambiguous slash dates as day/month/year",
    )
    parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        help="Only process the first N source rows (testing)",
    )
    parser.add_argument(
        "--json-summary",
        default=None,
        help="Write an execution summary JSON file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
