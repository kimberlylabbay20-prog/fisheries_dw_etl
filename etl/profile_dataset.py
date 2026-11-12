"""Profile a landing CSV without writing to the database."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from .cleaning import (
    _extract_value,
    is_missing,
    normalize_header,
    parse_date,
    parse_decimal,
)
from .config import Settings, load_column_mapping
from .extract import extract_csv


def _quantile(values: list[Decimal], fraction: float) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = Decimal(str(position - lower))
    return ordered[lower] * (Decimal("1") - weight) + ordered[upper] * weight


def _numeric_profile(values: list[Any], field_name: str, max_integer_digits: int) -> dict[str, Any]:
    valid: list[Decimal] = []
    invalid = 0
    missing = 0
    errors: Counter[str] = Counter()

    for value in values:
        if is_missing(value):
            missing += 1
            continue
        number, error = parse_decimal(value, field_name, max_integer_digits)
        if error:
            invalid += 1
            errors[error] += 1
        elif number is not None:
            valid.append(number)

    if valid:
        total = sum(valid)
        minimum = min(valid)
        maximum = max(valid)
        mean = total / Decimal(len(valid))
        q1 = _quantile(valid, 0.25)
        q3 = _quantile(valid, 0.75)
        iqr = (q3 - q1) if q1 is not None and q3 is not None else None
        if iqr is not None:
            low = q1 - Decimal("1.5") * iqr
            high = q3 + Decimal("1.5") * iqr
            outliers = sum(1 for number in valid if number < low or number > high)
        else:
            low = high = None
            outliers = 0
    else:
        total = minimum = maximum = mean = q1 = q3 = iqr = low = high = None
        outliers = 0

    return {
        "field": field_name,
        "total_values": len(values),
        "valid": len(valid),
        "invalid": invalid,
        "missing": missing,
        "min": minimum,
        "max": maximum,
        "sum": total,
        "mean": mean,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "outlier_low": low,
        "outlier_high": high,
        "outlier_count": outliers,
        "error_examples": errors.most_common(5),
    }


def _date_profile(values: list[Any], dayfirst: bool) -> dict[str, Any]:
    valid = []
    invalid = 0
    missing = 0
    errors: Counter[str] = Counter()
    for value in values:
        if is_missing(value):
            missing += 1
            continue
        parsed, error = parse_date(value, dayfirst=dayfirst)
        if error:
            invalid += 1
            errors[error] += 1
        elif parsed is not None:
            valid.append(parsed)

    return {
        "total_values": len(values),
        "valid": len(valid),
        "invalid": invalid,
        "missing": missing,
        "min": min(valid) if valid else None,
        "max": max(valid) if valid else None,
        "error_examples": errors.most_common(5),
    }


def _top_values(values: list[Any], limit: int = 10) -> list[dict[str, Any]]:
    counter = Counter(
        str(value).strip()
        for value in values
        if not is_missing(value)
    )
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(limit)
    ]


def profile_dataset(path: Path | str, dayfirst: bool = False) -> dict[str, Any]:
    extracted = extract_csv(path)
    column_mapping = load_column_mapping()

    headers = extracted.headers
    raw_rows = [record for _, record in extracted.rows]
    normalized_rows = [
        {normalize_header(key): value for key, value in record.items()}
        for record in raw_rows
    ]

    missing_by_column = {}
    for header in headers:
        normalized = normalize_header(header)
        missing_by_column[header] = sum(
            1 for row in normalized_rows if is_missing(row.get(normalized))
        )

    exact_hashes = Counter(
        json.dumps(record, sort_keys=True, default=str)
        for record in raw_rows
    )
    exact_duplicate_groups = sum(1 for count in exact_hashes.values() if count > 1)
    exact_duplicate_extra_rows = sum(count - 1 for count in exact_hashes.values() if count > 1)

    canonical_values: dict[str, list[Any]] = {}
    for canonical in (
        "landing_id",
        "landing_date",
        "port",
        "species",
        "vessel_id",
        "vessel_name",
        "cooperative_name",
        "quantity_kg",
        "value_php",
    ):
        canonical_values[canonical] = [
            _extract_value(row, canonical, column_mapping)
            for row in normalized_rows
        ]

    return {
        "path": str(Path(path)),
        "encoding": extracted.encoding,
        "delimiter": extracted.delimiter,
        "row_count": len(raw_rows),
        "column_count": len(headers),
        "headers": headers,
        "normalized_headers": extracted.normalized_headers,
        "blank_rows_skipped": extracted.blank_rows_skipped,
        "missing_by_column": missing_by_column,
        "exact_duplicate_groups": exact_duplicate_groups,
        "exact_duplicate_extra_rows": exact_duplicate_extra_rows,
        "landing_date": _date_profile(canonical_values["landing_date"], dayfirst),
        "quantity_kg": _numeric_profile(
            canonical_values["quantity_kg"],
            "quantity_kg",
            max_integer_digits=10,
        ),
        "value_php": _numeric_profile(
            canonical_values["value_php"],
            "value_php",
            max_integer_digits=12,
        ),
        "top_ports": _top_values(canonical_values["port"]),
        "top_species": _top_values(canonical_values["species"]),
        "top_vessels": _top_values(canonical_values["vessel_id"]),
        "top_cooperatives": _top_values(canonical_values["cooperative_name"]),
    }


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    return str(value)


def profile_to_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# Dataset Profiling Report",
        "",
        f"- **File:** `{profile['path']}`",
        f"- **Rows:** {profile['row_count']}",
        f"- **Columns:** {profile['column_count']}",
        f"- **Encoding:** {profile['encoding']}",
        f"- **Delimiter:** `{profile['delimiter']}`",
        f"- **Blank rows skipped:** {profile['blank_rows_skipped']}",
        f"- **Exact duplicate groups:** {profile['exact_duplicate_groups']}",
        f"- **Exact duplicate extra rows:** {profile['exact_duplicate_extra_rows']}",
        "",
        "## Columns and Missing Values",
        "",
        "| Column | Missing |",
        "|---|---:|",
    ]
    for column, missing in profile["missing_by_column"].items():
        lines.append(f"| `{column}` | {missing} |")

    lines.extend(
        [
            "",
            "## Date Profile",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Valid | {profile['landing_date']['valid']} |",
            f"| Invalid | {profile['landing_date']['invalid']} |",
            f"| Missing | {profile['landing_date']['missing']} |",
            f"| Min | {_format_value(profile['landing_date']['min'])} |",
            f"| Max | {_format_value(profile['landing_date']['max'])} |",
            "",
            "## Numeric Profiles",
            "",
            "| Field | Valid | Invalid | Missing | Min | Max | Sum | Mean | Outliers |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for key in ("quantity_kg", "value_php"):
        item = profile[key]
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                item["field"],
                item["valid"],
                item["invalid"],
                item["missing"],
                _format_value(item["min"]),
                _format_value(item["max"]),
                _format_value(item["sum"]),
                _format_value(item["mean"]),
                item["outlier_count"],
            )
        )

    for title, key in (
        ("Top Ports", "top_ports"),
        ("Top Species", "top_species"),
        ("Top Vessels", "top_vessels"),
        ("Top Cooperatives", "top_cooperatives"),
    ):
        lines.extend(["", f"## {title}", "", "| Value | Count |", "|---|---:|"])
        for item in profile[key]:
            lines.append(f"| {item['value']} | {item['count']} |")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Profile a fisheries landing CSV.")
    parser.add_argument("--csv", default=str(settings.dataset), help="Path to the CSV file")
    parser.add_argument("--output-json", help="Write JSON profile to this path")
    parser.add_argument("--output-md", help="Write Markdown profile to this path")
    parser.add_argument(
        "--date-dayfirst",
        action="store_true",
        default=settings.date_dayfirst,
        help="Interpret ambiguous slash dates as day/month/year",
    )
    args = parser.parse_args(argv)

    try:
        profile = profile_dataset(args.csv, dayfirst=args.date_dayfirst)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - CLI should report a clear error
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(profile, indent=2, default=str),
            encoding="utf-8",
        )

    if args.output_md:
        output_path = Path(args.output_md)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(profile_to_markdown(profile), encoding="utf-8")

    print(json.dumps(profile, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
