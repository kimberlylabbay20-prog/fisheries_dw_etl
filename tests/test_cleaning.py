from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from etl.cleaning import (
    CleaningOptions,
    Dimensions,
    PortRecord,
    SpeciesRecord,
    VesselVersion,
    clean_rows,
    clean_text,
    lookup_port,
    lookup_species,
    normalize_header,
    parse_date,
    parse_decimal,
    parse_landing_id,
)


def sample_dimensions() -> Dimensions:
    return Dimensions(
        ports=[
            PortRecord(1, "Bongao Fish Port", "Bongao"),
            PortRecord(6, "Bongao Fish Port", "Bongao"),
            PortRecord(2, "Panglima Sugala Port", "Panglima Sugala"),
        ],
        species=[
            SpeciesRecord(1, "Yellowfin Tuna"),
            SpeciesRecord(2, "Skipjack Tuna"),
        ],
        vessels=[
            VesselVersion(
                vessel_key=1,
                vessel_id="V001",
                vessel_name="M/V Sinar Laut",
                cooperative_name="Bongao Fishers Cooperative",
                effective_start_date=date(2020, 1, 1),
                effective_end_date=date(2024, 12, 31),
                is_current=False,
            ),
            VesselVersion(
                vessel_key=11,
                vessel_id="V001",
                vessel_name="M/V Sinar Laut",
                cooperative_name="Bongao United Cooperative",
                effective_start_date=date(2025, 1, 1),
                effective_end_date=date(9999, 12, 31),
                is_current=True,
            ),
        ],
        date_keys={20190601, 20240601, 20260105, 20260106},
        existing_landing_ids={1},
    )


def raw_row(**overrides):
    row = {
        "landing_id": "100",
        "landing_date": "2026-01-05",
        "port": "Bongao Fish Port",
        "species": "Yellowfin Tuna",
        "vessel_id": "V001",
        "vessel_name": "M/V Sinar Laut",
        "cooperative_name": "Bongao United Cooperative",
        "quantity_kg": "120.5",
        "value_php": "18,000.00",
    }
    row.update(overrides)
    return row


class CleaningUnitTests(unittest.TestCase):
    def test_normalize_header(self):
        self.assertEqual(normalize_header("  Quantity KG "), "quantity_kg")
        self.assertEqual(normalize_header("\ufeffLanding-Date"), "landing_date")

    def test_clean_text_placeholders(self):
        self.assertIsNone(clean_text(" N/A "))
        self.assertIsNone(clean_text(""))
        self.assertEqual(clean_text("  M/V   Sinar   Laut "), "M/V Sinar Laut")

    def test_parse_date_iso_and_invalid(self):
        parsed, error = parse_date("2026-01-05")
        self.assertIsNone(error)
        self.assertEqual(parsed, date(2026, 1, 5))

        parsed, error = parse_date("not-a-date")
        self.assertIsNone(parsed)
        self.assertIn("invalid landing_date", error)

    def test_parse_date_dayfirst(self):
        parsed, error = parse_date("05/01/2026", dayfirst=True)
        self.assertIsNone(error)
        self.assertEqual(parsed, date(2026, 1, 5))

    def test_parse_decimal_currency_and_commas(self):
        number, error = parse_decimal("PHP 18,000.50", "value_php", 12)
        self.assertIsNone(error)
        self.assertEqual(number, Decimal("18000.50"))

    def test_parse_decimal_rejects_negative_and_precision(self):
        number, error = parse_decimal("-1", "quantity_kg", 10)
        self.assertIsNone(number)
        self.assertIn("non-negative", error)

        number, error = parse_decimal("10000000000", "quantity_kg", 10)
        self.assertIsNone(number)
        self.assertIn("precision", error)

    def test_parse_landing_id_rejects_bigint_overflow(self):
        number, error = parse_landing_id(str(2**63))
        self.assertIsNone(number)
        self.assertIn("bigint range", error)

        number, error = parse_landing_id("42")
        self.assertIsNone(error)
        self.assertEqual(number, 42)

    def test_port_lookup_duplicate_identical_chooses_lowest(self):
        warnings: set[str] = set()
        port, error = lookup_port(
            "Bongao Fish Port",
            sample_dimensions(),
            {},
            warnings,
        )
        self.assertIsNone(error)
        self.assertEqual(port.port_id, 1)
        self.assertTrue(warnings)

    def test_port_lookup_municipality_fallback(self):
        warnings: set[str] = set()
        port, error = lookup_port("Bongao", sample_dimensions(), {}, warnings)
        self.assertIsNone(error)
        self.assertEqual(port.port_id, 1)

    def test_port_lookup_ambiguous_different_municipality(self):
        dimensions = Dimensions(
            ports=[
                PortRecord(1, "Same Port", "Town A"),
                PortRecord(2, "Same Port", "Town B"),
            ]
        )
        warnings: set[str] = set()
        port, error = lookup_port("Same Port", dimensions, {}, warnings)
        self.assertIsNone(port)
        self.assertIn("ambiguous port", error)

    def test_species_lookup_alias(self):
        species, error = lookup_species(
            "Tuna",
            sample_dimensions(),
            {"tuna": "Yellowfin Tuna"},
        )
        self.assertIsNone(error)
        self.assertEqual(species.species_id, 1)

    def test_clean_valid_row(self):
        result = clean_rows(
            [(2, raw_row())],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 1)
        self.assertEqual(result.rejected_rows, 0)
        row = result.rows[0]
        self.assertEqual(row.status, "READY")
        self.assertEqual(row.port_id, 1)
        self.assertEqual(row.species_id, 1)
        self.assertEqual(row.date_key, 20260105)
        self.assertEqual(row.quantity_kg, Decimal("120.50"))
        self.assertEqual(row.value_php, Decimal("18000.00"))

    def test_missing_required_field_is_rejected(self):
        result = clean_rows(
            [(2, raw_row(quantity_kg=""))],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn("missing quantity_kg", result.rows[0].rejection_reason)

    def test_unknown_species_is_rejected(self):
        result = clean_rows(
            [(2, raw_row(species="Seaweed"))],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn("unknown species", result.rows[0].rejection_reason)

    def test_date_not_in_dim_date_is_rejected(self):
        result = clean_rows(
            [(2, raw_row(landing_date="2026-02-01"))],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn("not found in dim_date", result.rows[0].rejection_reason)

    def test_duplicate_source_row_is_rejected(self):
        result = clean_rows(
            [(2, raw_row()), (3, raw_row())],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 1)
        self.assertEqual(result.rejected_rows, 1)
        self.assertIn("duplicate source row", result.rows[1].rejection_reason)

    def test_duplicate_landing_id_is_rejected(self):
        result = clean_rows(
            [
                (2, raw_row(quantity_kg="100")),
                (3, raw_row(quantity_kg="200")),
            ],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 1)
        self.assertIn("duplicate landing_id", result.rows[1].rejection_reason)

    def test_existing_landing_id_is_rejected(self):
        result = clean_rows(
            [(2, raw_row(landing_id="1"))],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn("already exists", result.rows[0].rejection_reason)

    def test_new_vessel_requires_name_and_cooperative(self):
        result = clean_rows(
            [
                (
                    2,
                    raw_row(
                        vessel_id="V999",
                        vessel_name="",
                        cooperative_name="",
                    ),
                )
            ],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn("new vessel is missing vessel_name", result.rows[0].rejection_reason)
        self.assertIn(
            "new vessel is missing cooperative_name",
            result.rows[0].rejection_reason,
        )

    def test_overlong_vessel_name_is_rejected(self):
        result = clean_rows(
            [
                (
                    2,
                    raw_row(
                        vessel_id="V999",
                        vessel_name="X" * 101,
                        cooperative_name="Test Cooperative",
                    ),
                )
            ],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn("vessel_name exceeds 100 characters", result.rows[0].rejection_reason)

    def test_overlong_cooperative_name_is_rejected(self):
        result = clean_rows(
            [
                (
                    2,
                    raw_row(
                        vessel_id="V999",
                        vessel_name="M/V Test Vessel",
                        cooperative_name="C" * 101,
                    ),
                )
            ],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn(
            "cooperative_name exceeds 100 characters",
            result.rows[0].rejection_reason,
        )

    def test_historical_vessel_version_is_valid(self):
        result = clean_rows(
            [
                (
                    2,
                    raw_row(
                        landing_date="2024-06-01",
                        cooperative_name="Bongao Fishers Cooperative",
                    ),
                )
            ],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 1)
        self.assertEqual(result.rows[0].vessel_id_raw, "V001")

    def test_no_covering_vessel_version_is_rejected(self):
        result = clean_rows(
            [(2, raw_row(landing_date="2019-06-01"))],
            {},
            sample_dimensions(),
        )
        self.assertEqual(result.ready_rows, 0)
        self.assertIn(
            "no vessel version covers landing_date",
            result.rows[0].rejection_reason,
        )

    def test_alias_mapping_for_port(self):
        result = clean_rows(
            [(2, raw_row(port="Bongao"))],
            {},
            sample_dimensions(),
            CleaningOptions(port_aliases={"bongao": 1}),
        )
        self.assertEqual(result.ready_rows, 1)
        self.assertEqual(result.rows[0].port_id, 1)


if __name__ == "__main__":
    unittest.main()
