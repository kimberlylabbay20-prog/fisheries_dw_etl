# Fisheries Data Warehouse ETL

Lab 2 / Lab 3 project for the `fisheries_dw` PostgreSQL data warehouse.

The project extracts messy fisheries landing CSV data, validates and cleans it,
stages it in `stg`, applies SCD Type 2 changes to `dw.dim_vessel`, and loads
fact rows into `dw.fact_landing`. The original `database/dw_fish.sql` file is
preserved unchanged.

## Current Status

- Database inspection and read-only data quality checks completed.
- Python ETL package, SQL scripts, and unit tests implemented.
- `34` unit tests pass; `compileall` passes.
- Offline dry run completed against a read-only dimension snapshot.
- The required instructor dataset `datasets/messy_landings_2026.csv` is not
  present, so the instructor ETL run and warehouse load were not executed.
- No warehouse rows were inserted, updated, or deleted by this project run.
- `FISHERIES_DB_PASSWORD` is not visible in the non-interactive review shell;
  host Python PostgreSQL authentication therefore could not be re-verified.
  Earlier attempts with the container password failed. The in-container `psql`
  client works through local trust and was used for read-only checks.

See `reports/` for detailed inspection, profiling, cleaning, and execution
results. See `screenshots/README.md` for the screenshot checklist.

## Warehouse Snapshot

| Table | Rows |
|---|---:|
| `dw.dim_date` | 4,018 |
| `dw.dim_port` | 10 |
| `dw.dim_species` | 10 |
| `dw.dim_vessel` | 9 |
| `dw.fact_landing` | 300 |

Existing fact totals: `82,379.80 kg` and `11,714,339.66 PHP`.
Fact date coverage: `2024-01-01` through `2024-10-26`.

Known source-warehouse issues that the ETL handles:

- `dw.dim_port` contains duplicate name/municipality pairs. The cleaner uses the
  lowest `port_id` and emits a warning.
- `dw.dim_vessel` has a V001 SCD Type 2 history. Old key `1` covers
  `2020-01-01` through `2024-12-31`; current key `11` starts `2025-01-01`.
- `dw.dim_vessel.vessel_key` has no column default; the loader supplies
  `nextval(...)` explicitly.
- `dw.fact_landing.landing_id` is `GENERATED ALWAYS AS IDENTITY`. Explicit
  source IDs require `OVERRIDING SYSTEM VALUE`; the loader also advances the
  identity sequence after explicit inserts so later generated IDs cannot
  collide.

## Project Layout

```text
fisheries_dw/
  config/
    column_mapping.json
    value_mappings.json
  database/
    data_quality_checks.sql
    dw_fish.sql
    inspect_database.sql
    lab2_dw_load.sql
    lab2_etl_pipeline.sql
    staging_tables.sql
  datasets/
    README.md
    messy_landings_2026.csv   # required; currently missing
  etl/
    __init__.py
    cleaning.py
    config.py
    db.py
    extract.py
    load.py
    pipeline.py
    profile_dataset.py
  reports/
    data_cleaning_report.md
    data_profiling_report.md
    database_inspection_report.md
    etl_execution_report.md
    final_submission_report.md
    implementation_review.md
  screenshots/
    README.md
  tests/
    test_cleaning.py
    test_extract_and_profile.py
    test_pipeline.py
  .env.example
  .gitignore
  README.md
  requirements.txt
  run_etl.py
```

## Prerequisites

- Python 3.10+ (tested with Python 3.14.2)
- PostgreSQL 18.6 in Docker container `fisheries-postgres18`, host port `5434`
- Database `fisheries_dw`, schema `dw`
- Python packages:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and set local values. The Python process reads
environment variables; it does not load `.env` automatically. Set them in your
shell before running the pipeline.

Required variables:

```text
FISHERIES_DB_HOST=localhost
FISHERIES_DB_PORT=5434
FISHERIES_DB_NAME=fisheries_dw
FISHERIES_DB_USER=postgres
FISHERIES_DB_PASSWORD=<local password>
FISHERIES_DATASET=datasets/messy_landings_2026.csv
FISHERIES_DATE_DAYFIRST=false
```

Never commit `.env` or a real password. `.gitignore` excludes `.env`.

## Dataset

The expected file is `datasets/messy_landings_2026.csv`. It is currently
missing. See `datasets/README.md` for expected columns and aliases.

Do not substitute the unrelated local sample
`..\fisheries_data.csv` for the instructor
dataset. It was used only as a profiling/dry-run smoke test.

## Usage

### Run tests

```powershell
python -m unittest discover -s tests -v
python -m compileall -q etl tests run_etl.py
```

### Profile a CSV without writing to the database

```powershell
python -m etl.profile_dataset `
  --csv "..\fisheries_data.csv" `
  --output-json "reports\generated\sample_profile.json" `
  --output-md "reports\generated\sample_profile.md"
```

### Dry run against PostgreSQL

```powershell
python run_etl.py --dry-run --json-summary "reports\generated\dry_run.json"
```

This reads dimensions from `dw`, cleans the source rows, and writes no database
rows. It requires a working database password.

### Offline dry run using a read-only dimension snapshot

```powershell
python run_etl.py `
  --csv "..\fisheries_data.csv" `
  --dry-run `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\sample_dry_run.json"
```

The snapshot is generated with read-only SQL; see
`reports/etl_execution_report.md`.

### Create staging tables and stage rows without loading

```powershell
python run_etl.py --init-staging --skip-load --json-summary "reports\generated\staged_run.json"
```

Review `stg.etl_run_log`, `stg.clean_landing`, and `stg.etl_reject_log` before
loading.

### Load the warehouse

Only run this after reviewing staging and obtaining approval to modify
warehouse data.

```powershell
python run_etl.py --init-staging --json-summary "reports\generated\load_run.json"
```

The load runs in a transaction and rolls back on failure. It never drops or
truncates tables.

### SQL scripts

```powershell
# Read-only inspection
Get-Content -Raw database\inspect_database.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -

# Read-only data quality checks
Get-Content -Raw database\data_quality_checks.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -

# Additive staging objects
Get-Content -Raw database\staging_tables.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -

# Manual load alternative (requires approval)
Get-Content -Raw database\lab2_dw_load.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

The optional wrapper `database/lab2_etl_pipeline.sql` uses psql `\ir` includes,
so it needs a host `psql` client or a copy of the `database/` directory inside
the container:

```powershell
psql -h localhost -p 5434 -U postgres -d fisheries_dw -f database/lab2_etl_pipeline.sql
```

## Safety Rules

- `database/dw_fish.sql` is preserved unchanged.
- No `DROP`, `TRUNCATE`, or `DELETE` is used by the new SQL scripts.
- Staging DDL is additive (`CREATE SCHEMA IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`).
- Warehouse loads are transaction-wrapped and require explicit review/approval.
- No credentials or generated secrets are committed.
- No dataset rows, results, or screenshots are fabricated.

## Troubleshooting

### `password authentication failed for user "postgres"`

The host Python connection needs the actual PostgreSQL password. Set
`FISHERIES_DB_PASSWORD` in the same shell or environment that runs Python. A
password set only in one interactive terminal is not inherited by other
processes. The in-container `psql` client uses local trust authentication and
can run the read-only SQL scripts without a password.

### Required dataset is missing

Place the instructor file at `datasets/messy_landings_2026.csv`, or pass
`--csv <path>`. Do not use unrelated sample data as the instructor dataset.

### Staging tables do not exist

Run `database/staging_tables.sql` or pass `--init-staging` to the pipeline.

## GitHub

This folder is prepared as a local Git repository for submission. Do not commit
or push without explicit approval. Commit only source, SQL, tests,
configuration examples, and reports; keep raw datasets, generated output, and
`.env` out of Git. No remote URL is assumed or fabricated.
