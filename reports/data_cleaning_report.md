# Data Cleaning Report

Date: 2026-11-12

## Scope

The cleaning layer is implemented in `etl/cleaning.py` and used by both the
profiler and the ETL pipeline. It performs no database writes.

The required instructor dataset `datasets/messy_landings_2026.csv` is missing.
The dry run below used the unrelated local sample only as a smoke test.

## Cleaning Rules

### Text and headers

- Headers are lowercased, punctuation is replaced with underscores, and
  whitespace is collapsed.
- UTF-8 BOM characters are removed.
- Text values are trimmed and internal whitespace is collapsed.
- Null-like placeholders are treated as missing: empty string, `NA`, `N/A`,
  `null`, `none`, `nil`, `-`, `--`, `?`, `unknown`, `not available`, `nan`,
  `not applicable`.

### Dates

- ISO formats are tried first: `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYYMMDD`, and
  timestamp variants.
- Month-name formats such as `05-Jan-2026` are supported.
- Ambiguous slash/dash dates use `FISHERIES_DATE_DAYFIRST` or
  `--date-dayfirst`.
- A landing date is accepted only if its `YYYYMMDD` key exists in
  `dw.dim_date`.

### Numeric values

- Currency markers (`PHP`, `peso`, `pesos`, `₱`, `$`), commas, underscores, and
  spaces are removed.
- Parenthesized negatives are recognized and rejected because the warehouse
  requires non-negative values.
- Values must fit `numeric(12,2)` for `quantity_kg` and `numeric(14,2)` for
  `value_php`.
- `landing_id` must be a positive PostgreSQL `bigint` value.
- Values are rounded half-up to two decimal places.

### Dimension matching

- Port matching normalizes case, punctuation, accents, and ampersands.
- If duplicate port name/municipality pairs exist, the lowest `port_id` is used
  and a warning is emitted.
- Port matching can fall back to municipality if the port name alone is not
  unique.
- Species matching is case-insensitive and supports aliases from
  `config/value_mappings.json`.
- Vessel matching uses `vessel_id` and the landing date to select the SCD Type 2
  version whose effective date range contains the landing date.
- A new vessel requires both a vessel name and cooperative name.
- Vessel and cooperative names are limited to 100 characters.
- Rows without `vessel_id` are rejected.

### Duplicates and existing facts

- Exact duplicate source rows are rejected.
- Duplicate `landing_id` values within a batch are rejected, keeping the first.
- `landing_id` values already present in `dw.fact_landing` are rejected.
- Rows without a source `landing_id` are allowed and receive a generated
  `nextval('dw.fact_landing_landing_id_seq')` value at load time.
- Source-supplied `landing_id` values are preserved with
  `OVERRIDING SYSTEM VALUE`; the identity sequence is advanced after explicit
  inserts.

## Smoke-Test Dry Run

Source: `..\fisheries_data.csv`

Dimensions: read-only snapshot from the live `dw` schema, written to
`reports/generated/dimensions_snapshot.json`.

Command:

```powershell
python run_etl.py `
  --csv "..\fisheries_data.csv" `
  --dry-run `
  --dimensions-json "reports\generated\dimensions_snapshot.json" `
  --json-summary "reports\generated\sample_dry_run.json"
```

Result:

| Metric | Value |
|---|---:|
| Extracted rows | 10 |
| Ready rows | 0 |
| Rejected rows | 10 |
| Duplicate source rows | 0 |

Individual rejection reasons:

| Reason | Rows |
|---|---:|
| Missing `vessel_id` | 10 |
| Unknown species `Tuna` | 3 |
| Unknown species `Skipjack` | 3 |
| Unknown species `Seaweed` | 2 |
| `landing_id` already exists in `dw.fact_landing` | 10 |

Warnings:

- Duplicate `dim_port` rows for `Bongao`; lowest `port_id` 1 used.
- Duplicate `dim_port` rows for `Languyan`; lowest `port_id` 5 used.
- Duplicate `dim_port` rows for `Panglima Sugala`; lowest `port_id` 2 used.
- Duplicate `dim_port` rows for `Simunul`; lowest `port_id` 3 used.
- Duplicate `dim_port` rows for `Sitangkai`; lowest `port_id` 4 used.

Why every row was rejected:

- The sample has no vessel columns.
- Its species values `Tuna`, `Skipjack`, and `Seaweed` do not match the
  warehouse species names.
- Its `landing_id` values `1` through `10` already exist in
  `dw.fact_landing`.

This confirms that the cleaner rejects incomplete source data rather than
silently loading invalid rows.

## Warehouse Writes

The offline dry run used a read-only dimension snapshot and did not connect to
PostgreSQL. No warehouse rows were written. Staging and warehouse load were not
executed because the instructor dataset is missing and no load approval was
requested.

## Generated Outputs

Excluded from Git under `reports/generated/`:

- `sample_dry_run.json`
- `dimensions_snapshot.json`
