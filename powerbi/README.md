# Power BI CSV Exports

This folder contains a read-only exporter for the existing `fisheries_dw`
warehouse. It generates CSV files that can be imported into Power BI Desktop.

> This export is **not** the missing instructor-provided
> `datasets/messy_landings_2026.csv`. The exporter reads the existing `dw`
> tables only. It does not process, replace, or claim to have processed the
> missing instructor dataset.

## Current status

- `powerbi/export_powerbi_csv.py` is ready.
- `powerbi/README.md` is ready.
- The CSV files have **not** been generated in this environment because the
  Docker/PostgreSQL server was unavailable and `FISHERIES_DB_PASSWORD` was not
  set.
- No CSV data was fabricated.
- Nothing was staged, committed, or pushed.

## Expected output files

When the database is available, run the exporter to create:

```text
powerbi/dim_date.csv
powerbi/dim_port.csv
powerbi/dim_species.csv
powerbi/dim_vessel.csv
powerbi/fact_landing.csv
```

The exporter writes UTF-8 CSV files with a header row and only the existing
columns from the five warehouse tables. It does not export `stg` tables or any
other database objects.

## Verified schema snapshot

The project's existing read-only inspection report
(`reports/database_inspection_report.md`) records this warehouse schema:

| Table | Current rows | Columns |
|---|---:|---|
| `dw.dim_date` | 4,018 | `date_key`, `full_date`, `year`, `quarter`, `month`, `month_name`, `day_of_month` |
| `dw.dim_port` | 10 | `port_id`, `port_name`, `municipality` |
| `dw.dim_species` | 10 | `species_id`, `species_name` |
| `dw.dim_vessel` | 9 | `vessel_key`, `vessel_id`, `vessel_name`, `cooperative_name`, `effective_start_date`, `effective_end_date`, `is_current` |
| `dw.fact_landing` | 300 | `landing_id`, `date_key`, `port_id`, `species_id`, `vessel_key`, `quantity_kg`, `value_php` |

The live database could not be re-inspected during this task because Docker and
PostgreSQL were unavailable. The export script therefore checks
`information_schema` at runtime, reads the actual column list for each table,
and exports those columns. It does not rely on a hard-coded column list.

## Read-only design

The exporter:

- Uses the existing project configuration through
  `etl.config.Settings.from_env()`.
- Connects through the existing `etl.db.connect(settings, readonly=True)` helper.
- Runs only `SELECT` queries against the fixed table list:
  `dw.dim_date`, `dw.dim_port`, `dw.dim_species`, `dw.dim_vessel`, and
  `dw.fact_landing`.
- Does not run `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `DROP`, `ALTER`,
  `CREATE`, or any other write operation.
- Does not export credentials, connection strings, or private account details.
- Writes only the five expected CSV files. Temporary files use a unique prefix
  and are replaced atomically with the final CSV files.
- Does not delete or modify unrelated files.

The current warehouse tables contain operational dimension and fact data such as
ports, species, vessels, cooperatives, quantities, and values. They do not
contain database passwords or connection credentials.

## Prerequisites

- Python 3.10 or newer.
- The project dependencies installed, including `psycopg2`.
- PostgreSQL running and the `fisheries_dw` database available.
- The `dw` schema and warehouse tables loaded.
- The database password available in the environment.
- A database user with `SELECT` permission on the five `dw` tables.

From the project root, install dependencies if needed:

```powershell
python -m pip install -r requirements.txt
```

## Run the exporter

Run these commands from the project root:

```powershell
$env:FISHERIES_DB_PASSWORD = Read-Host "PostgreSQL password"
python powerbi/export_powerbi_csv.py
```

Do not put the password into a script, README, CSV, or committed file. The
`Read-Host` command keeps it out of the command history.

Optional environment variables use the project's existing defaults:

| Variable | Default |
|---|---|
| `FISHERIES_DB_HOST` | `localhost` |
| `FISHERIES_DB_PORT` | `5434` |
| `FISHERIES_DB_NAME` | `fisheries_dw` |
| `FISHERIES_DB_USER` | `postgres` |
| `FISHERIES_DB_PASSWORD` | none; must be supplied at runtime |

To write the exports somewhere else:

```powershell
python powerbi/export_powerbi_csv.py --output-dir powerbi
```

The default output directory is this `powerbi/` folder.

## Expected console result

A complete run prints one line per exported table and a final summary:

```text
Connecting to the configured PostgreSQL database in read-only mode.
EXPORTED: dw.dim_date -> ...\powerbi\dim_date.csv (4018 rows)
EXPORTED: dw.dim_port -> ...\powerbi\dim_port.csv (10 rows)
EXPORTED: dw.dim_species -> ...\powerbi\dim_species.csv (10 rows)
EXPORTED: dw.dim_vessel -> ...\powerbi\dim_vessel.csv (9 rows)
EXPORTED: dw.fact_landing -> ...\powerbi\fact_landing.csv (300 rows)
Done. Wrote 5 CSV files to ...\powerbi.
```

Row counts are read from the live tables and may differ if the warehouse has
changed since the inspection report was written.

If an expected table is missing, the script skips it, reports the missing table,
and exits with a nonzero status. It does not create substitute tables or
fabricate rows.

## Import into Power BI Desktop

1. Open Power BI Desktop.
2. Select **Home > Get Data > Text/CSV**.
3. Import each generated file:
   - `dim_date.csv`
   - `dim_port.csv`
   - `dim_species.csv`
   - `dim_vessel.csv`
   - `fact_landing.csv`
4. In **Transform Data**, verify these data types:
   - `full_date`, `effective_start_date`, and `effective_end_date`: Date
   - `date_key`, `port_id`, `species_id`, `landing_id`: Whole Number
   - `vessel_key`: Whole Number
   - `quantity_kg` and `value_php`: Decimal Number
   - `is_current`: True/False
5. In **Model view**, create these one-to-many relationships:
   - `dim_date[date_key]` to `fact_landing[date_key]`
   - `dim_port[port_id]` to `fact_landing[port_id]`
   - `dim_species[species_id]` to `fact_landing[species_id]`
   - `dim_vessel[vessel_key]` to `fact_landing[vessel_key]`
6. Use `dim_vessel[vessel_key]`, not `vessel_id`, for the fact relationship.
   `dim_vessel` is a slowly changing dimension (SCD Type 2), so one vessel can
   have multiple historical keys.
7. Optionally mark `dim_date` as the date table and use `full_date` as the date
   column.

Example measures:

```dax
Total Quantity Kg = SUM ( fact_landing[quantity_kg] )
Total Value PHP = SUM ( fact_landing[value_php] )
Landing Count = COUNTROWS ( fact_landing )
```

To refresh after the warehouse changes, rerun the exporter and then select
**Refresh** in Power BI Desktop.

## Troubleshooting

### Password not set

If the script reports a connection failure, set the password in the current
PowerShell session:

```powershell
$env:FISHERIES_DB_PASSWORD = Read-Host "PostgreSQL password"
```

### Docker or PostgreSQL is unavailable

Start Docker Desktop and the `fisheries-postgres18` container, then verify the
database is reachable before rerunning the exporter. The CSV files cannot be
generated while the database is offline.

### Missing table

If `dw.dim_date`, `dw.dim_port`, `dw.dim_species`, `dw.dim_vessel`, or
`dw.fact_landing` does not exist, load the existing warehouse schema first. The
exporter will not create it.

### Permission denied

The database user needs `SELECT` permission on the five `dw` tables. The
exporter opens a read-only session, so write permissions are not required.

### Empty CSV file

An empty table produces a header-only CSV. This is not fabricated data; it means
the source table currently has no rows.

## Git handling

No `.gitignore` change was made for this folder. The CSV exports are intentional
project outputs, so they are not ignored by default. If the course or project
policy says warehouse data must not be published, add this rule before
committing:

```gitignore
powerbi/*.csv
```

Never commit `.env` files, database passwords, or connection strings.
