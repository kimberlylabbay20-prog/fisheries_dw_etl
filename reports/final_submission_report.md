# Final Submission Report

Date: 2026-11-12

Project root: `<project-root>`

## 1. Completed Tasks

- Inspected the `fisheries_dw` warehouse schema, constraints, indexes, sequences,
  SCD history, duplicate ports, and data quality with read-only SQL.
- Implemented the Python ETL package for extraction, profiling, cleaning,
  validation, staging, SCD Type 2 vessel handling, and fact loading.
- Created additive staging SQL, read-only inspection/quality SQL, a manual load
  script, and a psql wrapper.
- Added unit tests for cleaning, extraction, profiling, CLI parsing, and offline
  dry-run behavior.
- Generated documentation and reports for database inspection, profiling,
  cleaning, ETL execution, implementation review, and submission.
- Fixed review findings: `--limit` validation, bigint and varchar bounds,
  staging checks, dry-run connection cleanup, manual SQL check ordering, and a
  misnamed test.
- Fixed fact identity handling: explicit source `landing_id` values now use
  `OVERRIDING SYSTEM VALUE`, and the identity sequence is advanced after
  explicit inserts.
- Preserved `database/dw_fish.sql` unchanged.

## 2. Created or Modified Files

Python and CLI:

- `run_etl.py`
- `etl/__init__.py`
- `etl/cleaning.py`
- `etl/config.py`
- `etl/db.py`
- `etl/extract.py`
- `etl/load.py`
- `etl/pipeline.py`
- `etl/profile_dataset.py`

Configuration and support:

- `config/column_mapping.json`
- `config/value_mappings.json`
- `.env.example`
- `.gitignore`
- `requirements.txt`

SQL:

- `database/inspect_database.sql`
- `database/staging_tables.sql`
- `database/data_quality_checks.sql`
- `database/lab2_dw_load.sql`
- `database/lab2_etl_pipeline.sql`

Tests:

- `tests/test_cleaning.py`
- `tests/test_extract_and_profile.py`
- `tests/test_pipeline.py`

Documentation:

- `README.md`
- `datasets/README.md`
- `screenshots/README.md`
- `reports/database_inspection_report.md`
- `reports/data_profiling_report.md`
- `reports/data_cleaning_report.md`
- `reports/etl_execution_report.md`
- `reports/implementation_review.md`
- `reports/final_submission_report.md`

Protected file:

- `database/dw_fish.sql` was not modified. SHA256:
  `E1DEC8BA9B827412495CF74C1073E7C99160AF1FEE2B8AA163FFBDFBB0CD4E10`.

Local generated artifacts, intentionally ignored by Git:

- `reports/generated/dimensions_snapshot.json`
- `reports/generated/sample_dry_run.json`
- `reports/generated/sample_profile.json`
- `reports/generated/sample_profile.md`

## 3. PostgreSQL Connection Status

- Container `fisheries-postgres18` is running on host port `5434`.
- Database `fisheries_dw` is reachable through the in-container `psql` client
  using local trust authentication.
- Host Python authentication could not be re-verified in the non-interactive
  review shell because `FISHERIES_DB_PASSWORD` is not visible there.
- Earlier host attempts using the container `POSTGRES_PASSWORD` failed with
  `FATAL: password authentication failed for user "postgres"`.
- The user reports that the password is configured in their interactive
  PowerShell terminal. No password was written to the repository or reports.

## 4. CSV Availability

- Required file: `datasets/messy_landings_2026.csv`.
- Status: **missing** in the project, `Documents`, `Downloads`, and `Desktop`.
- The unrelated file
  `..\fisheries_data.csv` was used only as a
  smoke test and must not be submitted as the instructor dataset.
- Because the instructor CSV is missing, the instructor profiling, cleaning,
  staging, and warehouse load were not completed.

## 5. Cleaning Results

- Implemented normalization for headers, text, dates, numeric/currency values,
  port aliases, species aliases, cooperatives, and duplicate handling.
- Added rejection for invalid dates, missing dimensions, unknown species,
  missing vessel IDs, duplicate source rows, duplicate `landing_id` values,
  existing fact IDs, bigint overflow, and overlong vessel/cooperative names.
- SCD Type 2 vessel matching uses `vessel_id` plus the landing date.
- Duplicate port name/municipality pairs use the lowest `port_id` and emit a
  warning.
- Smoke-test dry run on the unrelated sample: 10 extracted, 0 ready, 10
  rejected, 0 duplicate source rows.
- Rejections were caused by missing `vessel_id`, unknown sample species, and
  sample `landing_id` values already present in the warehouse.
- Temporary fixtures verified the ready path for an old V001 version and a new
  V999 vessel; both produced 1 ready row and were not loaded.

## 6. Test Results

Command:

```powershell
python -m unittest discover -s tests -v
```

Result:

```text
Ran 34 tests
OK
```

Coverage includes extraction, profiling, header normalization, date/numeric
parsing, port/species matching, SCD vessel selection, duplicate handling,
bigint/varchar bounds, CLI `--limit` validation, missing CSV handling, and the
offline dry-run ready path.

## 7. Compile Results

Command:

```powershell
python -m compileall -q etl tests run_etl.py
```

Result: passed with no errors.

## 8. Dry-Run Results

Offline smoke-test command:

```powershell
python run_etl.py `
  --csv "..\fisheries_data.csv" `
  --dry-run `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\sample_dry_run.json"
```

Result: 10 extracted, 0 ready, 10 rejected, 0 duplicate source rows, exit code
`0`. No database connection was opened for this offline run.

The ready path was verified with temporary fixtures:

- Existing vessel V001 on `2024-06-01`: 1 extracted, 1 ready, 0 rejected.
- New vessel V999 on `2026-01-05`: 1 extracted, 1 ready, 0 rejected.

Identity behavior was validated safely in a rolled-back transaction using a
temporary identity table: explicit ID `9999` was inserted, then
`nextval(...)` produced `10000`. No warehouse rows or sequences were changed.

## 9. Database Modifications

- No warehouse rows were inserted, updated, or deleted.
- No staging schema was created.
- No staging or loading command was executed.
- Warehouse counts remained unchanged:

| Check | Value |
|---|---:|
| `dw.dim_date` | 4,018 |
| `dw.dim_port` | 10 |
| `dw.dim_species` | 10 |
| `dw.dim_vessel` | 9 |
| `dw.fact_landing` | 300 |
| Total `quantity_kg` | 82,379.80 |
| Total `value_php` | 11,714,339.66 |
| `stg` schema | absent |
| `dw.fact_landing_landing_id_seq` | 300 |
| `dw.dim_vessel_vessel_key_seq` | 11 |

## 10. Blockers

- Required instructor CSV is missing.
- `FISHERIES_DB_PASSWORD` is not visible in this non-interactive shell, so the
  live-database dry run cannot be executed here.
- Staging creation and warehouse loading require dataset availability and
  explicit approval.
- No Git remote exists; nothing was committed or pushed. The local repository
  was initialized only for submission preparation.

## 11. Exact Next Commands

Set the password in the shell that runs Python, without writing it to a file:

```powershell
$env:FISHERIES_DB_PASSWORD = Read-Host "PostgreSQL password"
```

Profile the instructor dataset:

```powershell
python -m etl.profile_dataset `
  --csv "datasets\messy_landings_2026.csv" `
  --output-json "reports\generated\instructor_profile.json" `
  --output-md "reports\generated\instructor_profile.md"
```

Run the instructor dry run against the read-only dimension snapshot:

```powershell
python run_etl.py --dry-run `
  --csv "datasets\messy_landings_2026.csv" `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\instructor_dry_run.json"
```

Run the live-database dry run:

```powershell
python run_etl.py --dry-run `
  --csv "datasets\messy_landings_2026.csv" `
  --json-summary "reports\generated\instructor_live_dry_run.json"
```

Create staging and stage rows without loading:

```powershell
python run_etl.py --init-staging --skip-load `
  --csv "datasets\messy_landings_2026.csv" `
  --json-summary "reports\generated\staged_run.json"
```

Review staging:

```powershell
docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -c "SELECT run_id, status, extracted_rows, cleaned_rows, rejected_rows, loaded_fact_rows FROM stg.etl_run_log ORDER BY started_at DESC LIMIT 5;"
docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -c "SELECT status, COUNT(*) FROM stg.clean_landing GROUP BY status;"
docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -c "SELECT source_row, reason FROM stg.etl_reject_log ORDER BY reject_id DESC LIMIT 20;"
```

After explicit approval, load the warehouse:

```powershell
python run_etl.py --init-staging `
  --csv "datasets\messy_landings_2026.csv" `
  --json-summary "reports\generated\load_run.json"
```

Re-run quality checks after loading:

```powershell
Get-Content -Raw database\data_quality_checks.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

Re-run tests and compile checks:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q etl tests run_etl.py
```

## 12. Submission Readiness

- Code, SQL, tests, and documentation are implemented and reviewed.
- All 34 tests pass and compile checks pass.
- No warehouse data was modified and the protected SQL file is unchanged.
- The instructor ETL run is not complete because the required CSV is missing.
- The live-database dry run is not complete because the password is not visible
  in this shell.
- Staging and loading remain intentionally unexecuted pending dataset
  availability and approval.
- No screenshots were captured; `screenshots/README.md` contains the checklist
  for real evidence to capture after the instructor run.
- The project is ready to continue as soon as
  `datasets/messy_landings_2026.csv` is available and the password is set in the
  Python environment.

## 13. Finalization Verification (2026-11-12)

- Fresh test run: `python -m unittest discover -s tests -v` -> `Ran 34 tests`,
  `OK`.
- Fresh compile run: `python -m compileall -q etl tests run_etl.py` -> passed.
- Project inventory reviewed: all source, SQL, test, configuration, and
  documentation files are present.
- `database/dw_fish.sql` SHA256 remains
  `E1DEC8BA9B827412495CF74C1073E7C99160AF1FEE2B8AA163FFBDFBB0CD4E10`.
- No staging creation, ETL load, or warehouse write was executed during
  finalization. No `DROP`, `TRUNCATE`, or `DELETE` was run against the
  warehouse.
- Docker Desktop was not running in the finalization shell, so live row counts
  could not be re-queried. The Section 9 counts remain the last verified
  snapshot; no write command was executed after that snapshot.
- Secret scan found no hardcoded passwords, connection strings, tokens, private
  keys, or committed `.env` files. `FISHERIES_DB_PASSWORD` is read only from the
  process environment.
- `datasets/messy_landings_2026.csv` remains missing. No dataset, result, or
  screenshot was fabricated.
- Local Git repository preparation, `.gitignore`, and the commit file set were
  reviewed. No commit or push was made; both remain pending explicit approval.
- Instructor ETL validation remains **not complete** because the real CSV has
  not been processed.
