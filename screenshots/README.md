# Screenshot Checklist

Do not fabricate screenshots. Capture each image only after running the
corresponding command and confirming the result.

Recommended capture tool on Windows: `Win+Shift+S` (Snipping Tool), then save
into this folder with the suggested filename.

## Available Now

### 01_container_running.png

```powershell
docker ps --filter "name=fisheries-postgres18"
```

Capture the container name, image, status, and port mapping.

### 02_database_tables.png

```powershell
docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -c "\dt dw.*"
```

Capture the five `dw` tables.

### 03_row_counts.png

```powershell
Get-Content -Raw database\inspect_database.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

Capture the exact row-count section.

### 04_data_quality_checks.png

```powershell
Get-Content -Raw database\data_quality_checks.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

Capture the orphan, duplicate, and SCD integrity results.

### 05_unit_tests.png

```powershell
python -m unittest discover -s tests -v
```

Capture the final `Ran 34 tests ... OK` output.

### 06_offline_dry_run.png

```powershell
python run_etl.py `
  --csv "..\fisheries_data.csv" `
  --dry-run `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\sample_dry_run.json"
```

Capture the summary and rejection reasons. Label it clearly as an unrelated
sample smoke test.

### 07_scd_vessel_history.png

```powershell
docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -P pager=off -c `
  "SELECT vessel_key, vessel_id, cooperative_name, effective_start_date, effective_end_date, is_current FROM dw.dim_vessel ORDER BY vessel_id, effective_start_date;"
```

Capture the V001 historical and current rows.

## After the Instructor Dataset Is Available

### 08_profiling_report.png

```powershell
python -m etl.profile_dataset `
  --csv "datasets\messy_landings_2026.csv" `
  --output-json "reports\generated\instructor_profile.json" `
  --output-md "reports\generated\instructor_profile.md"
```

Capture the actual row count, date range, and numeric profile.

### 09_staging_summary.png

```powershell
python run_etl.py --init-staging --skip-load
```

Then:

```powershell
docker exec fisheries-postgres18 psql -U postgres -d fisheries_dw -P pager=off -c `
  "SELECT status, COUNT(*) FROM stg.clean_landing GROUP BY status ORDER BY status;"
```

Capture the staged run summary and status counts.

### 10_warehouse_load.png

Only after approval:

```powershell
python run_etl.py --init-staging
```

Capture the load summary JSON printed by the pipeline.

### 11_after_load_checks.png

```powershell
Get-Content -Raw database\data_quality_checks.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```

Capture the before/after row counts and integrity checks.

### 12_github_repository.png

Only after explicit approval to initialize, commit, and push:

```powershell
git status
git log --oneline -5
```

Capture the repository page or terminal output. Do not commit `.env`, raw
datasets, generated output, or credentials.
