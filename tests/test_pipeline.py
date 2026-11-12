from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from etl.pipeline import build_parser, run


SNAPSHOT = {
    "ports": [
        {"port_id": 1, "port_name": "Bongao", "municipality": "Bongao"},
    ],
    "species": [
        {"species_id": 1, "species_name": "Yellowfin Tuna"},
    ],
    "vessels": [
        {
            "vessel_key": 11,
            "vessel_id": "V001",
            "vessel_name": "M/V Bongao Star",
            "cooperative_name": "Bongao United Cooperative",
            "effective_start_date": "2025-01-01",
            "effective_end_date": "9999-12-31",
            "is_current": True,
        }
    ],
    "date_keys": [20260105],
    "existing_landing_ids": [1],
}


def _write_snapshot(path: Path) -> None:
    path.write_text(json.dumps(SNAPSHOT), encoding="utf-8")


def _write_csv(path: Path) -> None:
    path.write_text(
        "landing_id,landing_date,port,species,vessel_id,vessel_name,"
        "cooperative_name,quantity_kg,value_php\n"
        "9999,2026-01-05,Bongao,Yellowfin Tuna,V001,M/V Bongao Star,"
        "Bongao United Cooperative,120.5,18000\n",
        encoding="utf-8",
    )


class PipelineParserTests(unittest.TestCase):
    def test_limit_zero_is_allowed(self):
        args = build_parser().parse_args(["--limit", "0"])
        self.assertEqual(args.limit, 0)

    def test_negative_limit_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["--limit", "-1"])


class PipelineRunTests(unittest.TestCase):
    def test_missing_csv_returns_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.csv"
            args = build_parser().parse_args(["--csv", str(missing)])
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(run(args), 2)

    def test_offline_dry_run_with_ready_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            csv_path = temp / "clean.csv"
            snapshot_path = temp / "snapshot.json"
            summary_path = temp / "summary.json"
            _write_csv(csv_path)
            _write_snapshot(snapshot_path)

            args = build_parser().parse_args(
                [
                    "--csv",
                    str(csv_path),
                    "--dry-run",
                    "--dimensions-json",
                    str(snapshot_path),
                    "--json-summary",
                    str(summary_path),
                ]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run(args), 0)

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["extracted_rows"], 1)
            self.assertEqual(summary["ready_rows"], 1)
            self.assertEqual(summary["rejected_rows"], 0)

    def test_limit_zero_processes_no_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            csv_path = temp / "clean.csv"
            snapshot_path = temp / "snapshot.json"
            summary_path = temp / "summary.json"
            _write_csv(csv_path)
            _write_snapshot(snapshot_path)

            args = build_parser().parse_args(
                [
                    "--csv",
                    str(csv_path),
                    "--dry-run",
                    "--limit",
                    "0",
                    "--dimensions-json",
                    str(snapshot_path),
                    "--json-summary",
                    str(summary_path),
                ]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run(args), 0)

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["extracted_rows"], 0)
            self.assertEqual(summary["ready_rows"], 0)


if __name__ == "__main__":
    unittest.main()
