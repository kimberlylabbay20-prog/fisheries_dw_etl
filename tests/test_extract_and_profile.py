from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from etl.extract import extract_csv
from etl.profile_dataset import profile_dataset, profile_to_markdown


class ExtractionTests(unittest.TestCase):
    def test_extract_csv_with_bom_and_blank_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.csv"
            path.write_text(
                "\ufefflanding_id,landing_date,port,species,vessel_id,quantity_kg,value_php\n"
                "1,2026-01-05,Bongao,Yellowfin Tuna,V001,120,18000\n"
                ",,,,,,\n"
                "2,2026-01-06,Simunul,Skipjack Tuna,V002,85,10200\n",
                encoding="utf-8",
            )
            extracted = extract_csv(path)
            self.assertEqual(len(extracted.rows), 2)
            self.assertEqual(extracted.blank_rows_skipped, 1)
            self.assertEqual(extracted.rows[0][0], 2)
            self.assertEqual(extracted.rows[1][0], 4)
            self.assertEqual(extracted.headers[0], "landing_id")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            extract_csv("does-not-exist.csv")

    def test_duplicate_headers_raise(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "duplicate.csv"
            path.write_text("landing_id,Landing ID\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                extract_csv(path)

    def test_semicolon_delimiter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "semi.csv"
            path.write_text(
                "landing_id;landing_date;port;species;vessel_id;quantity_kg;value_php\n"
                "1;2026-01-05;Bongao;Yellowfin Tuna;V001;120;18000\n",
                encoding="utf-8",
            )
            extracted = extract_csv(path)
            self.assertEqual(extracted.delimiter, ";")
            self.assertEqual(len(extracted.rows), 1)


class ProfileTests(unittest.TestCase):
    def test_profile_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.csv"
            path.write_text(
                "landing_id,landing_date,port,species,vessel_id,quantity_kg,value_php\n"
                "1,2026-01-05,Bongao,Yellowfin Tuna,V001,120,18000\n"
                "2,2026-01-06,Simunul,Skipjack Tuna,V002,85,10200\n"
                "3,not-a-date,Simunul,Skipjack Tuna,V002,-5,abc\n",
                encoding="utf-8",
            )
            profile = profile_dataset(path)
            self.assertEqual(profile["row_count"], 3)
            self.assertEqual(profile["landing_date"]["valid"], 2)
            self.assertEqual(profile["landing_date"]["invalid"], 1)
            self.assertEqual(profile["quantity_kg"]["valid"], 2)
            self.assertEqual(profile["quantity_kg"]["invalid"], 1)
            markdown = profile_to_markdown(profile)
            self.assertIn("# Dataset Profiling Report", markdown)
            self.assertIn("quantity_kg", markdown)


if __name__ == "__main__":
    unittest.main()
