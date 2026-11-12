"""Reusable cleaning and validation rules for fisheries landing records."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from dateutil import parser as date_parser

PLACEHOLDERS = {
    "",
    "na",
    "n/a",
    "null",
    "none",
    "nil",
    "-",
    "--",
    "?",
    "unknown",
    "not available",
    "nan",
    "not applicable",
}

MAX_BIGINT = 2**63 - 1

ISO_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]

MONTH_NAME_FORMATS = [
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%B-%Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
]

MONTH_FIRST_FORMATS = [
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%m/%d/%Y %H:%M:%S",
]

DAY_FIRST_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d/%m/%Y %H:%M:%S",
]


def is_missing(value: Any) -> bool:
    """Return True for null-like source values."""
    if value is None:
        return True
    text = str(value).replace("\u00a0", " ").strip()
    return text.casefold() in PLACEHOLDERS


def clean_text(value: Any) -> str | None:
    """Trim, collapse whitespace, and convert null-like values to None."""
    if is_missing(value):
        return None
    text = str(value).replace("\u00a0", " ")
    text = " ".join(text.split())
    return text or None


def normalize_header(value: Any) -> str:
    """Normalize a CSV header to a lowercase underscore key."""
    text = str(value).replace("\ufeff", "").strip().casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalize_key(value: Any) -> str | None:
    """Normalize text for case-insensitive dimension matching."""
    text = clean_text(value)
    if text is None:
        return None
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split()) or None


def parse_date(value: Any, dayfirst: bool = False) -> tuple[date | None, str | None]:
    """Parse common date formats into a date.

    ISO dates are tried first. Slash/dash dates are ambiguous when both day and
    month are 12 or less; the configured dayfirst flag controls that choice.
    """
    text = clean_text(value)
    if text is None:
        return None, "missing landing_date"

    formats = list(ISO_DATE_FORMATS) + list(MONTH_NAME_FORMATS)
    formats += list(DAY_FIRST_FORMATS) if dayfirst else list(MONTH_FIRST_FORMATS)
    if dayfirst:
        formats += list(MONTH_FIRST_FORMATS)
    else:
        formats += list(DAY_FIRST_FORMATS)

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue

    if re.search(r"\b\d{4}\b", text):
        try:
            parsed = date_parser.parse(
                text,
                dayfirst=dayfirst,
                fuzzy=False,
                default=datetime(1900, 1, 1),
            )
            return parsed.date(), None
        except (ValueError, OverflowError):
            pass

    return None, f"invalid landing_date: {value!r}"


def parse_decimal(
    value: Any,
    field_name: str,
    max_integer_digits: int,
    scale: int = 2,
) -> tuple[Decimal | None, str | None]:
    """Parse a non-negative decimal and enforce warehouse precision."""
    text = clean_text(value)
    if text is None:
        return None, f"missing {field_name}"

    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1].strip()

    text = re.sub(r"(?i)\b(php|peso|pesos)\b", "", text)
    text = text.replace("\u20b1", "").replace("$", "")
    text = text.replace(",", "").replace("_", "").replace(" ", "")

    if negative_parentheses:
        text = f"-{text}"

    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None, f"invalid {field_name}: {value!r}"

    try:
        number = Decimal(text)
    except InvalidOperation:
        return None, f"invalid {field_name}: {value!r}"

    if number < 0:
        return None, f"{field_name} must be non-negative: {value!r}"

    if number >= Decimal(10) ** max_integer_digits:
        return None, f"{field_name} exceeds warehouse precision: {value!r}"

    quantized = number.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
    return quantized, None


def parse_landing_id(value: Any) -> tuple[int | None, str | None]:
    text = clean_text(value)
    if text is None:
        return None, None
    if not re.fullmatch(r"\d+", text):
        return None, f"invalid landing_id: {value!r}"
    number = int(text)
    if number <= 0:
        return None, f"landing_id must be positive: {value!r}"
    if number > MAX_BIGINT:
        return None, f"landing_id exceeds bigint range: {value!r}"
    return number, None


def make_source_hash(values: Sequence[Any]) -> str:
    payload = "\x1f".join("" if value is None else str(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PortRecord:
    port_id: int
    port_name: str
    municipality: str | None = None


@dataclass(frozen=True)
class SpeciesRecord:
    species_id: int
    species_name: str


@dataclass(frozen=True)
class VesselVersion:
    vessel_key: int
    vessel_id: str
    vessel_name: str
    cooperative_name: str
    effective_start_date: date
    effective_end_date: date
    is_current: bool


@dataclass
class Dimensions:
    ports: list[PortRecord] = field(default_factory=list)
    species: list[SpeciesRecord] = field(default_factory=list)
    vessels: list[VesselVersion] = field(default_factory=list)
    date_keys: set[int] = field(default_factory=set)
    existing_landing_ids: set[int] = field(default_factory=set)


@dataclass
class CleaningOptions:
    date_dayfirst: bool = False
    port_aliases: Mapping[str, Any] = field(default_factory=dict)
    species_aliases: Mapping[str, Any] = field(default_factory=dict)
    cooperative_aliases: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class CleanRow:
    source_row: int
    raw_record: dict[str, Any]
    landing_id: int | None = None
    landing_date: date | None = None
    date_key: int | None = None
    port_raw: str | None = None
    port_id: int | None = None
    species_raw: str | None = None
    species_id: int | None = None
    vessel_id_raw: str | None = None
    vessel_name_raw: str | None = None
    cooperative_name_raw: str | None = None
    quantity_kg: Decimal | None = None
    value_php: Decimal | None = None
    status: str = "READY"
    rejection_reason: str | None = None
    source_hash: str | None = None


@dataclass
class CleanResult:
    rows: list[CleanRow]
    warnings: list[str]
    extracted_rows: int
    ready_rows: int
    rejected_rows: int
    duplicate_rows: int


def _build_port_maps(
    ports: Sequence[PortRecord],
) -> tuple[dict[str, list[PortRecord]], dict[str, list[PortRecord]], dict[str, list[PortRecord]]]:
    by_name: dict[str, list[PortRecord]] = defaultdict(list)
    by_short_name: dict[str, list[PortRecord]] = defaultdict(list)
    by_municipality: dict[str, list[PortRecord]] = defaultdict(list)

    for port in ports:
        name_key = normalize_key(port.port_name)
        if name_key:
            by_name[name_key].append(port)
            short_key = re.sub(r"\s+fish\s+port$", "", name_key).strip()
            by_short_name[short_key].append(port)
        municipality_key = normalize_key(port.municipality)
        if municipality_key:
            by_municipality[municipality_key].append(port)

    return by_name, by_short_name, by_municipality


def _choose_port(
    candidates: Sequence[PortRecord],
    raw_value: str,
    warnings: set[str],
) -> tuple[PortRecord | None, str | None]:
    distinct = {
        (normalize_key(port.port_name), normalize_key(port.municipality))
        for port in candidates
    }
    if len(distinct) == 1:
        chosen = min(candidates, key=lambda port: port.port_id)
        if len(candidates) > 1:
            warnings.add(
                f"Duplicate dim_port rows for {raw_value!r}; using lowest port_id {chosen.port_id}."
            )
        return chosen, None
    return None, f"ambiguous port: {raw_value!r}"


def lookup_port(
    raw_value: Any,
    dimensions: Dimensions,
    aliases: Mapping[str, Any],
    warnings: set[str],
) -> tuple[PortRecord | None, str | None]:
    key = normalize_key(raw_value)
    if key is None:
        return None, "missing port"

    alias = aliases.get(key)
    if alias is not None:
        if isinstance(alias, int):
            for port in dimensions.ports:
                if port.port_id == alias:
                    return port, None
            return None, f"port alias points to unknown port_id {alias}"
        key = normalize_key(alias)
        if key is None:
            return None, f"invalid port alias for {raw_value!r}"

    by_name, by_short_name, by_municipality = _build_port_maps(dimensions.ports)
    for mapping in (by_name, by_short_name, by_municipality):
        candidates = mapping.get(key, [])
        if candidates:
            return _choose_port(candidates, str(raw_value), warnings)

    return None, f"unknown port: {raw_value!r}"


def lookup_species(
    raw_value: Any,
    dimensions: Dimensions,
    aliases: Mapping[str, Any],
) -> tuple[SpeciesRecord | None, str | None]:
    key = normalize_key(raw_value)
    if key is None:
        return None, "missing species"

    alias = aliases.get(key)
    if alias is not None:
        if isinstance(alias, int):
            for species in dimensions.species:
                if species.species_id == alias:
                    return species, None
            return None, f"species alias points to unknown species_id {alias}"
        key = normalize_key(alias)
        if key is None:
            return None, f"invalid species alias for {raw_value!r}"

    candidates = [
        species
        for species in dimensions.species
        if normalize_key(species.species_name) == key
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, f"ambiguous species: {raw_value!r}"
    return None, f"unknown species: {raw_value!r}"


def _resolve_cooperative(
    raw_value: Any,
    aliases: Mapping[str, Any],
) -> str | None:
    text = clean_text(raw_value)
    if text is None:
        return None
    key = normalize_key(text)
    if key is None:
        return text
    alias = aliases.get(key)
    if alias is None:
        return text
    return clean_text(alias)


def _extract_value(
    normalized_row: Mapping[str, Any],
    canonical_name: str,
    column_mapping: Mapping[str, Sequence[str]],
) -> Any:
    aliases = list(column_mapping.get(canonical_name, []))
    if canonical_name not in aliases:
        aliases.append(canonical_name)
    for alias in aliases:
        key = normalize_header(alias)
        if key in normalized_row:
            return normalized_row[key]
    return None


def _validate_vessel(
    row: CleanRow,
    versions_by_vessel: Mapping[str, list[VesselVersion]],
    errors: list[str],
) -> None:
    if row.vessel_id_raw is None:
        errors.append("missing vessel_id")
        return
    if len(row.vessel_id_raw) > 30:
        errors.append("vessel_id exceeds 30 characters")
        return
    if row.vessel_name_raw is not None and len(row.vessel_name_raw) > 100:
        errors.append("vessel_name exceeds 100 characters")
    if row.cooperative_name_raw is not None and len(row.cooperative_name_raw) > 100:
        errors.append("cooperative_name exceeds 100 characters")

    versions = versions_by_vessel.get(row.vessel_id_raw, [])
    if not versions:
        if row.vessel_name_raw is None:
            errors.append("new vessel is missing vessel_name")
        if row.cooperative_name_raw is None:
            errors.append("new vessel is missing cooperative_name")
        return

    if row.landing_date is None:
        return

    covering = [
        version
        for version in versions
        if version.effective_start_date <= row.landing_date <= version.effective_end_date
    ]
    if len(covering) > 1:
        errors.append("ambiguous vessel version for landing_date")
    elif not covering:
        errors.append("no vessel version covers landing_date")


def clean_rows(
    raw_rows: Sequence[tuple[int, Mapping[str, Any]]],
    column_mapping: Mapping[str, Sequence[str]],
    dimensions: Dimensions,
    options: CleaningOptions | None = None,
) -> CleanResult:
    """Clean and validate raw rows, returning accepted and rejected records."""
    options = options or CleaningOptions()
    warnings: set[str] = set()
    versions_by_vessel: dict[str, list[VesselVersion]] = defaultdict(list)
    for version in dimensions.vessels:
        versions_by_vessel[version.vessel_id].append(version)

    cleaned_rows: list[CleanRow] = []

    for source_row, raw_record in raw_rows:
        normalized_row = {
            normalize_header(key): value for key, value in raw_record.items()
        }
        row = CleanRow(source_row=source_row, raw_record=dict(raw_record))
        errors: list[str] = []

        landing_id_value = _extract_value(normalized_row, "landing_id", column_mapping)
        landing_id, landing_id_error = parse_landing_id(landing_id_value)
        if landing_id_error:
            errors.append(landing_id_error)
        row.landing_id = landing_id

        date_value = _extract_value(normalized_row, "landing_date", column_mapping)
        landing_date, date_error = parse_date(date_value, dayfirst=options.date_dayfirst)
        if date_error:
            errors.append(date_error)
        row.landing_date = landing_date

        if landing_date is not None:
            date_key = int(landing_date.strftime("%Y%m%d"))
            row.date_key = date_key
            if dimensions.date_keys and date_key not in dimensions.date_keys:
                errors.append(f"landing_date not found in dim_date: {landing_date}")

        port_value = _extract_value(normalized_row, "port", column_mapping)
        row.port_raw = clean_text(port_value)
        port, port_error = lookup_port(
            port_value,
            dimensions,
            options.port_aliases,
            warnings,
        )
        if port_error:
            errors.append(port_error)
        elif port is not None:
            row.port_id = port.port_id

        species_value = _extract_value(normalized_row, "species", column_mapping)
        row.species_raw = clean_text(species_value)
        species, species_error = lookup_species(
            species_value,
            dimensions,
            options.species_aliases,
        )
        if species_error:
            errors.append(species_error)
        elif species is not None:
            row.species_id = species.species_id

        vessel_id_value = _extract_value(normalized_row, "vessel_id", column_mapping)
        row.vessel_id_raw = clean_text(vessel_id_value)
        row.vessel_name_raw = clean_text(
            _extract_value(normalized_row, "vessel_name", column_mapping)
        )
        row.cooperative_name_raw = _resolve_cooperative(
            _extract_value(normalized_row, "cooperative_name", column_mapping),
            options.cooperative_aliases,
        )

        quantity_value = _extract_value(normalized_row, "quantity_kg", column_mapping)
        quantity, quantity_error = parse_decimal(
            quantity_value,
            "quantity_kg",
            max_integer_digits=10,
        )
        if quantity_error:
            errors.append(quantity_error)
        row.quantity_kg = quantity

        value_value = _extract_value(normalized_row, "value_php", column_mapping)
        value, value_error = parse_decimal(
            value_value,
            "value_php",
            max_integer_digits=12,
        )
        if value_error:
            errors.append(value_error)
        row.value_php = value

        _validate_vessel(row, versions_by_vessel, errors)

        if row.landing_id is not None and row.landing_id in dimensions.existing_landing_ids:
            errors.append(f"landing_id already exists in dw.fact_landing: {row.landing_id}")

        row.source_hash = make_source_hash(
            [
                row.landing_id,
                row.landing_date,
                row.port_id,
                row.species_id,
                row.vessel_id_raw,
                row.quantity_kg,
                row.value_php,
            ]
        )

        if errors:
            row.status = "REJECTED"
            row.rejection_reason = "; ".join(errors)
        cleaned_rows.append(row)

    duplicate_rows = 0

    ready_rows = [row for row in cleaned_rows if row.status == "READY"]
    seen_hashes: set[str] = set()
    for row in ready_rows:
        if row.source_hash in seen_hashes:
            row.status = "REJECTED"
            row.rejection_reason = "duplicate source row"
            duplicate_rows += 1
        else:
            seen_hashes.add(row.source_hash)

    ready_rows = [row for row in cleaned_rows if row.status == "READY"]
    seen_landing_ids: set[int] = set()
    for row in ready_rows:
        if row.landing_id is None:
            continue
        if row.landing_id in seen_landing_ids:
            row.status = "REJECTED"
            row.rejection_reason = "duplicate landing_id within batch"
            duplicate_rows += 1
        else:
            seen_landing_ids.add(row.landing_id)

    ready_count = sum(1 for row in cleaned_rows if row.status == "READY")
    rejected_count = len(cleaned_rows) - ready_count

    return CleanResult(
        rows=cleaned_rows,
        warnings=sorted(warnings),
        extracted_rows=len(cleaned_rows),
        ready_rows=ready_count,
        rejected_rows=rejected_count,
        duplicate_rows=duplicate_rows,
    )
