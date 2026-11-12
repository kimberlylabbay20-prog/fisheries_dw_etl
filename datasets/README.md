# Datasets

## Required Instructor Dataset

Expected file:

```text
datasets/messy_landings_2026.csv
```

Status: **not present** in this workspace as of 2026-11-12.

The ETL pipeline defaults to this path. Place the instructor-provided file here,
or pass a different path with `--csv`.

## Expected Source Columns

The pipeline maps common header variants to these canonical fields:

| Canonical field | Examples of accepted headers |
|---|---|
| `landing_id` | `landing_id`, `id`, `record_id`, `landing_no` |
| `landing_date` | `landing_date`, `date`, `catch_date`, `landing_dt`, `date_landed` |
| `port` | `port`, `port_name`, `landing_port`, `unloading_port` |
| `species` | `species`, `species_name`, `fish_species`, `catch_species` |
| `vessel_id` | `vessel_id`, `vessel`, `boat_id`, `boat` |
| `vessel_name` | `vessel_name`, `boat_name`, `ship_name` |
| `cooperative_name` | `cooperative_name`, `cooperative`, `coop`, `cooperative_org` |
| `quantity_kg` | `quantity_kg`, `quantity`, `qty_kg`, `weight_kg`, `kg`, `catch_kg` |
| `value_php` | `value_php`, `value`, `amount_php`, `total_value`, `price_php`, `landing_value` |

Header matching is case-insensitive and ignores punctuation/whitespace
differences. Additional header aliases can be added in
`config/column_mapping.json`.

## Required Fields for Loading

A row is loadable only when it has:

- a valid landing date covered by `dw.dim_date`
- a known port
- a known species
- a known vessel version covering the landing date, or enough vessel name and
  cooperative name data to create a new SCD Type 2 version
- non-negative `quantity_kg` and `value_php` values within warehouse precision
- a landing ID that is not already present in `dw.fact_landing`

Rows without `vessel_id` are rejected because the warehouse fact table requires
a `vessel_key`.

## Local Sample

The unrelated file `..\fisheries_data.csv` has
10 rows and columns:

```text
landing_id, port, species, quantity_kg, value_php, landing_date
```

It is **not** the instructor dataset. It has no vessel or cooperative fields, so
all of its rows are rejected by the ETL. It was used only to smoke-test the
profiler and offline dry-run workflow.

## Git

`.gitignore` excludes `datasets/*.csv`, `datasets/*.xlsx`, and
`datasets/*.xls` by default. Commit the instructor dataset only if the course
instructions explicitly allow it.
