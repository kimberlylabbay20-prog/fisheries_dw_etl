# ETL Execution Report

Date: 2026-11-12

## Summary

| Item | Status |
|---|---|
| Database inspection | Completed, read-only |
| Data quality checks | Completed, read-only |
| Python ETL implementation | Completed |
| Unit tests | 34 passed |
| Compile check | Passed |
| Profiling tool | Passed on unrelated sample |
| Offline dry run | Completed on unrelated sample |
| Instructor dataset ETL | Not run; dataset missing |
| Staging creation | Not run |
| Warehouse load | Not run; requires dataset and approval |
| Warehouse rows modified | None |

## Environment

- Project root: `<project-root>`
- Python: `3.14.2`
- PostgreSQL: `18.6` in container `fisheries-postgres18`
- Database: `fisheries_dw`
- Host port: `5434`
- Installed Python packages include `psycopg2`, `psycopg`, `pandas`, and
  `python-dateutil`

## Verification Commands and Results

### Compile check

```powershell
python -m compileall -q etl tests run_etl.py
```

Result: passed.

### Unit tests

```powershell
python -m unittest discover -s tests -v
```

Result:

```text
Ran 34 tests
OK
```

Coverage includes:

- header normalization and placeholder handling
- date parsing, including day-first and invalid dates
- numeric/currency parsing and precision rejection
- port and species lookups, aliases, and duplicate port handling
- missing required fields and unknown species
- SCD vessel version selection, including historical V001 rows
- duplicate source rows and duplicate `landing_id` handling
- existing `landing_id` rejection and bigint overflow rejection
- overlong vessel and cooperative names
- no covering vessel SCD version
- CSV extraction with BOM, blank rows, and alternate delimiters
- profiler output
- CLI `--limit` validation and `--limit 0`
- offline dry-run ready path and missing-CSV exit code

### Database inspection

```powershell
Get-Content -Raw database\inspect_database.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

Result: completed. See `reports/database_inspection_report.md`.

### Data quality checks

```powershell
Get-Content -Raw database\data_quality_checks.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

Result: completed.

Key results:

- 300 fact rows
- 0 orphan foreign keys
- 0 duplicate fact `landing_id` groups
- 0 exact duplicate fact rows
- 5 duplicate `dim_port` name/municipality groups
- 0 SCD integrity violations
- 0 overlapping vessel date ranges

### Offline dry run

```powershell
python run_etl.py `
  --csv "..\fisheries_data.csv" `
  --dry-run `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\sample_dry_run.json"
```

Result: 10 extracted, 0 ready, 10 rejected, 0 duplicate source rows. See
`reports/data_cleaning_report.md`.

Additional offline fixtures were used to verify the ready path:

- One row for existing vessel `V001` on `2024-06-01` (old SCD version):
  1 extracted, 1 ready, 0 rejected.
- One row for new vessel `V999` on `2026-01-05`:
  1 extracted, 1 ready, 0 rejected.

These fixtures were temporary files outside the project and were not loaded into
the warehouse.

### Dimension snapshot generation

The snapshot was generated with read-only SQL through the container:

```powershell
$sql = @"
SELECT json_build_object(
  'ports', COALESCE((SELECT json_agg(json_build_object('port_id', port_id, 'port_name', port_name, 'municipality', municipality) ORDER BY port_id) FROM dw.dim_port), '[]'::json),
  'species', COALESCE((SELECT json_agg(json_build_object('species_id', species_id, 'species_name', species_name) ORDER BY species_id) FROM dw.dim_species), '[]'::json),
  'vessels', COALESCE((SELECT json_agg(json_build_object('vessel_key', vessel_key, 'vessel_id', vessel_id, 'vessel_name', vessel_name, 'cooperative_name', cooperative_name, 'effective_start_date', effective_start_date, 'effective_end_date', effective_end_date, 'is_current', is_current) ORDER BY vessel_id, effective_start_date) FROM dw.dim_vessel), '[]'::json),
  'date_keys', COALESCE((SELECT json_agg(date_key ORDER BY date_key) FROM dw.dim_date), '[]'::json),
  'existing_landing_ids', COALESCE((SELECT json_agg(landing_id ORDER BY landing_id) FROM dw.fact_landing), '[]'::json)
)::text;
"@
$json = docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -Atc $sql
Set-Content -LiteralPath "reports\generated\dimensions_snapshot.json" -Value $json -Encoding utf8
```

## Blockers

### Required dataset missing

`datasets/messy_landings_2026.csv` is not present. The instructor ETL run,
staging load, and warehouse load cannot be completed without it.

### Host Python database authentication

`FISHERIES_DB_PASSWORD` is not set in the non-interactive review shell, so the
host Python connection could not be re-verified. Earlier attempts using the
container `POSTGRES_PASSWORD` failed with:

```text
psycopg2.OperationalError: connection to server at "localhost" (::1), port 5434 failed:
FATAL: password authentication failed for user "postgres"
```

The user reports that the password is configured in their local interactive
PowerShell terminal. Environment variables set only in that terminal are not
inherited by this tool session. The in-container `psql` client works through
local trust authentication, so read-only checks were run there.

No password was changed, and no credentials were written to the repository.

### Fact identity handling

`dw.fact_landing.landing_id` is `GENERATED ALWAYS AS IDENTITY`. The loader and
manual SQL now use `OVERRIDING SYSTEM VALUE` when preserving source-supplied
`landing_id` values. After explicit inserts, both paths call `setval(...)` so
the identity sequence is at least the maximum existing `landing_id`. This
prevents later generated IDs from colliding with explicitly loaded IDs.

The behavior was validated safely in a rolled-back transaction with a temporary
identity table: explicit `9999` loaded first, then `nextval(...)` produced
`10000`. No warehouse rows were changed.

## Not Executed

The following were intentionally not run:

- `database/staging_tables.sql`
- `database/lab2_dw_load.sql`
- `database/lab2_etl_pipeline.sql`
- `python run_etl.py --init-staging --skip-load`
- `python run_etl.py --init-staging`

Reason: the required dataset is missing and warehouse writes require review and
approval.

## Next Steps

1. Place the instructor dataset at `datasets/messy_landings_2026.csv`.
2. Set a working `FISHERIES_DB_PASSWORD` in the environment.
3. Run the profiler and review the actual source profile.
4. Run `python run_etl.py --dry-run` against the live dimensions.
5. Run `python run_etl.py --init-staging --skip-load`.
6. Review `stg.etl_run_log`, `stg.clean_landing`, and `stg.etl_reject_log`.
7. Obtain approval, then run `python run_etl.py --init-staging` or
   `database/lab2_dw_load.sql`.
8. Run `database/data_quality_checks.sql` again and record before/after counts.
