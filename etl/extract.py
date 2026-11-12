"""CSV extraction utilities."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .cleaning import is_missing, normalize_header


@dataclass
class ExtractedCSV:
    path: Path
    headers: list[str]
    normalized_headers: list[str]
    rows: list[tuple[int, dict[str, Any]]]
    encoding: str
    delimiter: str
    blank_rows_skipped: int


def _read_text(path: Path, encoding: str) -> str:
    with path.open("r", encoding=encoding, newline="") as handle:
        return handle.read()


def _detect_encoding(path: Path) -> tuple[str, str]:
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return _read_text(path, encoding), encoding
        except UnicodeDecodeError as error:
            last_error = error
    raise UnicodeDecodeError(
        "utf-8",
        b"",
        0,
        1,
        f"Could not decode {path}: {last_error}",
    )


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def extract_csv(path: Path | str) -> ExtractedCSV:
    """Read a CSV into raw dictionaries, preserving source row numbers."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {csv_path}. "
            "Place the instructor CSV in datasets/ or pass --csv."
        )
    if not csv_path.is_file():
        raise ValueError(f"Dataset path is not a file: {csv_path}")

    text, encoding = _detect_encoding(csv_path)
    delimiter = _detect_delimiter(text[:4096])

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError(f"CSV has no header row: {csv_path}")

    headers = [str(header).replace("\ufeff", "").strip() for header in reader.fieldnames]
    normalized_headers = [normalize_header(header) for header in headers]
    duplicates = {
        header
        for header in normalized_headers
        if normalized_headers.count(header) > 1
    }
    if duplicates:
        raise ValueError(f"Duplicate CSV headers after normalization: {sorted(duplicates)}")

    rows: list[tuple[int, dict[str, Any]]] = []
    blank_rows_skipped = 0
    for source_row, record in enumerate(reader, start=2):
        if record is None:
            blank_rows_skipped += 1
            continue
        values = [record.get(header) for header in reader.fieldnames]
        if all(is_missing(value) for value in values):
            blank_rows_skipped += 1
            continue
        rows.append((source_row, dict(record)))

    return ExtractedCSV(
        path=csv_path,
        headers=headers,
        normalized_headers=normalized_headers,
        rows=rows,
        encoding=encoding,
        delimiter=delimiter,
        blank_rows_skipped=blank_rows_skipped,
    )


def iter_raw_rows(path: Path | str) -> Iterator[tuple[int, dict[str, Any]]]:
    yield from extract_csv(path).rows
