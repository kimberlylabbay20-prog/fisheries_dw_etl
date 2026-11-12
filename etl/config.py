"""Configuration loading for the fisheries ETL pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from etl.cleaning import normalize_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "messy_landings_2026.csv"
DEFAULT_COLUMN_MAPPING = PROJECT_ROOT / "config" / "column_mapping.json"
DEFAULT_VALUE_MAPPINGS = PROJECT_ROOT / "config" / "value_mappings.json"
STAGING_SQL = PROJECT_ROOT / "database" / "staging_tables.sql"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def _normalize_lookup_key(value: str) -> str:
    return normalize_key(value) or ""


def load_column_mapping(path: Path = DEFAULT_COLUMN_MAPPING) -> dict[str, list[str]]:
    data = _read_json(path)
    mapping: dict[str, list[str]] = {}
    for canonical, aliases in data.items():
        if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
            raise ValueError(f"Column mapping for {canonical!r} must be a list of strings")
        mapping[str(canonical)] = [str(item) for item in aliases]
    return mapping


def load_value_mappings(path: Path = DEFAULT_VALUE_MAPPINGS) -> dict[str, dict[str, Any]]:
    data = _read_json(path)
    normalized: dict[str, dict[str, Any]] = {}
    for category in ("ports", "species", "cooperatives"):
        raw_category = data.get(category, {})
        if not isinstance(raw_category, dict):
            raise ValueError(f"Value mapping category {category!r} must be an object")
        normalized[category] = {
            _normalize_lookup_key(source): target
            for source, target in raw_category.items()
        }
    return normalized


@dataclass
class Settings:
    db_host: str = "localhost"
    db_port: int = 5434
    db_name: str = "fisheries_dw"
    db_user: str = "postgres"
    db_password: str | None = None
    dataset: Path = DEFAULT_DATASET
    date_dayfirst: bool = False
    column_mapping: dict[str, list[str]] = field(default_factory=load_column_mapping)
    value_mappings: dict[str, dict[str, Any]] = field(default_factory=load_value_mappings)

    @classmethod
    def from_env(cls) -> "Settings":
        dataset_value = os.getenv("FISHERIES_DATASET")
        if dataset_value:
            dataset = Path(dataset_value)
            if not dataset.is_absolute():
                dataset = PROJECT_ROOT / dataset
        else:
            dataset = DEFAULT_DATASET

        return cls(
            db_host=os.getenv("FISHERIES_DB_HOST", "localhost"),
            db_port=int(os.getenv("FISHERIES_DB_PORT", "5434")),
            db_name=os.getenv("FISHERIES_DB_NAME", "fisheries_dw"),
            db_user=os.getenv("FISHERIES_DB_USER", "postgres"),
            db_password=os.getenv("FISHERIES_DB_PASSWORD"),
            dataset=dataset,
            date_dayfirst=_as_bool(os.getenv("FISHERIES_DATE_DAYFIRST"), False),
            column_mapping=load_column_mapping(),
            value_mappings=load_value_mappings(),
        )

    def connection_kwargs(self) -> Mapping[str, Any]:
        kwargs: dict[str, Any] = {
            "host": self.db_host,
            "port": self.db_port,
            "dbname": self.db_name,
            "user": self.db_user,
        }
        if self.db_password:
            kwargs["password"] = self.db_password
        return kwargs
