# Implementation Review

Date: 2026-11-12

Scope: completed Fisheries DW ETL implementation.

No warehouse records were modified during this review. No staging or loading
commands were run.

## Verification Results

### 1. Tests

Command:

```powershell
python -m unittest discover -s tests -v
```

Result: **34 tests passed**, `OK`.

Compile check:

```powershell
python -m compileall -q etl tests run_etl.py
```

Result: passed.

### 2. Dry-run safety

Offline dry run command used:

```powershell
python run_etl.py `
  --csv "..\fisheries_data.csv" `
  --dry-run `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\review_dry_run.json"
```

Result: 10 extracted, 0 ready, 10 rejected, exit code `0`.

Warehouse counts before and after the dry run were identical:

| Check | Before | After |
|---|---:|---:|
| `dw.dim_date` | 4,018 | 4,018 |
| `dw.dim_port` | 10 | 10 |
| `dw.dim_species` | 10 | 10 |
| `dw.dim_vessel` | 9 | 9 |
| `dw.fact_landing` | 300 | 300 |
| Total `quantity_kg` | 82,379.80 | 82,379.80 |
| Total `value_php` | 11,714,339.66 | 11,714,339.66 |
| `stg` schema exists | no | no |

Code inspection confirms the dry-run path:

- `etl/pipeline.py` returns before `--init-staging`, staging inserts, or
  `load_warehouse`.
- With `--dimensions-json`, the dry run does not connect to PostgreSQL.
- Without `--dimensions-json`, `etl/db.py:24-28` opens the session with
  `set_session(readonly=True)` and only runs dimension `SELECT`s.
- The live-database dry run was not executed because `FISHERIES_DB_PASSWORD` is
  not visible in this non-interactive review shell; the offline dry run above
  verifies the no-write behavior without a database connection.

### 3. Credentials

- `etl/config.py:91` reads `FISHERIES_DB_PASSWORD` from the environment.
- `etl/config.py:96-106` passes the value only to `psycopg2.connect`.
- No password is hardcoded in Python or SQL files.
- No `.env` file exists in the project.
- `.env.example` contains only the placeholder `change-me`.
- `.gitignore` excludes `.env` and `.env.*`.

### 4. Missing CSV handling

Command:

```powershell
python run_etl.py --dry-run
```

Result: clear error message, exit code `2`.

```text
ERROR: Dataset not found: ...\datasets\messy_landings_2026.csv.
Place the instructor CSV in datasets/ or pass --csv.
```

The profiler also handles the missing file gracefully with exit code `2`.

### 5. Unsafe database operations

- No `TRUNCATE` statements exist in the project.
- No `DELETE` statements exist in the project.
- No `DROP` statements exist except `ON COMMIT DROP` for temporary tables.
- `database/staging_tables.sql` is additive only.
- `database/data_quality_checks.sql` and `database/inspect_database.sql` are
  read-only.
- Warehouse `UPDATE`/`INSERT` statements are confined to `etl/load.py` and
  `database/lab2_dw_load.sql`, neither of which is called during a dry run.
- The load path uses a transaction and rolls back on failure.
- `database/dw_fish.sql` remains unchanged.

### 6. Fact identity handling

- `dw.fact_landing.landing_id` is `GENERATED ALWAYS AS IDENTITY`, not an
  ordinary column without a default.
- `etl/load.py` and `database/lab2_dw_load.sql` now use
  `OVERRIDING SYSTEM VALUE` when inserting source-supplied `landing_id` values.
- Both paths call `setval(...)` after explicit inserts so the identity sequence
  is at least the maximum existing `landing_id`.
- A rolled-back probe on a temporary identity table confirmed the pattern:
  explicit `9999` inserted, then `nextval(...)` produced `10000`.
- No warehouse rows or sequences were changed by the probe.

## Resolved Issues

| Severity | Issue | Resolution |
|---|---|---|
| Minor | `--limit 0` was treated as “no limit”; negative limits were accepted. | Added a non-negative integer parser and changed the check to `if args.limit is not None`. |
| Minor | New-vessel `vessel_name` and `cooperative_name` were not length-checked. | Added `varchar(100)` length checks and tests. |
| Minor | `landing_id` was not range-checked against PostgreSQL `bigint`. | Added `MAX_BIGINT` validation and a test. |
| Minor | The dry-run branch could leak a DB connection if JSON summary writing failed. | Added a `finally` block that closes the connection. |
| Minor | `staging_exists` did not verify `stg.vessel_change_log`. | Added the missing `to_regclass` check. |
| Minor | The manual SQL ambiguous-vessel check ran after the vessel-key update. | Moved the ambiguity check before the update. |
| Minor | A misnamed test did not actually test a missing SCD version. | Fixed the fixture date and assertion. |
| Important | Explicit `landing_id` inserts would fail against the identity column. | Added `OVERRIDING SYSTEM VALUE` and identity-sequence synchronization. |
| Minor | The manual SQL load did not assert that every ready row was inserted. | Added pre-load ready/fact counts and a post-insert assertion that raises on mismatch. |

## Remaining Issues

| Severity | Issue |
|---|---|
| Blocker | `datasets/messy_landings_2026.csv` is still missing, so the instructor ETL run cannot be completed. |
| Blocker | `FISHERIES_DB_PASSWORD` is not visible in this non-interactive review shell, so the live DB dry-run, staging, and loading cannot be run here. The user reports it is set in their interactive terminal. |
| Minor | Port and species lookups rebuild lookup structures or scan dimensions per row. This is fine for 300 rows but inefficient for large datasets. |
| Note | `source_hash` excludes vessel name and cooperative name, so those fields do not affect duplicate-source detection. |
| Note | `reports/generated/dimensions_snapshot.json` is intentionally ignored by Git. The offline dry-run command requires this snapshot to exist locally. |
| Note | `database/lab2_etl_pipeline.sql` uses psql `\ir` includes and therefore requires a host `psql` client or a copy of the `database/` directory inside the container. This is documented. |

## Exact Offline Dry-Run Command

Once `datasets/messy_landings_2026.csv` is available and the dimension snapshot
exists, run:

```powershell
python run_etl.py --dry-run --csv "datasets\messy_landings_2026.csv" --dimensions-json "reports\generated\dimensions_snapshot.json" --json-summary "reports\generated\instructor_dry_run.json"
```

This command reads the instructor CSV, cleans and validates it against the
read-only dimension snapshot, writes a local JSON summary, and does not connect
to or modify the warehouse.

If `reports\generated\dimensions_snapshot.json` is missing, regenerate it with
the read-only SQL block in `reports/etl_execution_report.md`.
