# Data Profiling Report

Date: 2026-11-12

## Instructor Dataset Status

Required file: `datasets/messy_landings_2026.csv`

Status: **not present** in the workspace.

The instructor dataset was not profiled because it is unavailable. No results
were invented or substituted.

## Profiling Tool

`etl/profile_dataset.py` performs read-only profiling:

- detects UTF-8 BOM and common delimiters
- normalizes headers
- counts blank rows and missing values
- detects exact duplicate rows
- parses dates with the same rules as the cleaner
- parses numeric values and computes min, max, sum, mean, quartiles, IQR, and
  IQR outlier counts
- reports top ports, species, vessels, and cooperatives

Usage:

```powershell
python -m etl.profile_dataset `
  --csv "<path-to-csv>" `
  --output-json "reports\generated\profile.json" `
  --output-md "reports\generated\profile.md"
```

## Smoke-Test Profile

The unrelated local sample
`..\fisheries_data.csv` was profiled only to
verify the tool. It is **not** the instructor dataset and must not be treated as
such.

### File characteristics

| Metric | Value |
|---|---:|
| Rows | 10 |
| Columns | 6 |
| Encoding | `utf-8-sig` |
| Delimiter | `,` |
| Blank rows skipped | 0 |
| Exact duplicate row groups | 0 |
| Exact duplicate extra rows | 0 |

Columns:

```text
landing_id, port, species, quantity_kg, value_php, landing_date
```

Missing values by column: all zero.

### Date profile

| Metric | Value |
|---|---:|
| Total values | 10 |
| Valid | 10 |
| Invalid | 0 |
| Missing | 0 |
| Minimum | 2026-01-05 |
| Maximum | 2026-01-28 |

### Numeric profile

| Field | Valid | Min | Max | Sum | Mean | Q1 | Q3 | IQR | IQR outliers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `quantity_kg` | 10 | 85.00 | 200.00 | 1,260.00 | 126.00 | 97.50 | 145.00 | 47.50 | 0 |
| `value_php` | 10 | 7,000.00 | 22,500.00 | 123,000.00 | 12,300.00 | 8,550.00 | 13,425.00 | 4,875.00 | 1 |

### Categorical profile

Top ports:

| Port | Rows |
|---|---:|
| Bongao | 3 |
| Simunul | 2 |
| Sitangkai | 2 |
| Languyan | 2 |
| Panglima Sugala | 1 |

Top species:

| Species | Rows |
|---|---:|
| Tuna | 3 |
| Skipjack | 3 |
| Seaweed | 2 |
| Round Scad | 2 |

The sample has no vessel or cooperative columns, so `top_vessels` and
`top_cooperatives` are empty. All 10 rows are rejected by cleaning because
`vessel_id` is required by `dw.fact_landing`.

## Profiling Checks to Run on the Instructor Dataset

Once `datasets/messy_landings_2026.csv` is available, run the profiler and
record:

- actual row and column counts
- encoding and delimiter
- missing-value counts per column
- duplicate row counts
- valid/invalid date counts and date range
- quantity and value ranges, totals, means, quartiles, and outliers
- distinct port, species, vessel, and cooperative values
- unknown dimension values that need `config/value_mappings.json` aliases

## Generated Outputs

The smoke-test outputs are written under `reports/generated/`, which is excluded
from Git:

- `reports/generated/sample_profile.json`
- `reports/generated/sample_profile.md`
