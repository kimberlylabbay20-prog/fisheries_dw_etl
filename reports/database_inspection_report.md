# Database Inspection Report

Date: 2026-11-12

Database: `fisheries_dw`

Schema: `dw`

Container: `fisheries-postgres18`

PostgreSQL version: `18.6 (Debian 18.6-1.pgdg13+2)`

Server timezone: `Etc/UTC`

All inspection queries were read-only. No warehouse rows were modified.

## Tables and Row Counts

| Table | Exact rows | Estimated rows |
|---|---:|---:|
| `dw.dim_date` | 4,018 | 4,018 |
| `dw.dim_port` | 10 | 10 |
| `dw.dim_species` | 10 | 10 |
| `dw.dim_vessel` | 9 | 9 |
| `dw.fact_landing` | 300 | 300 |

No `stg` schema exists yet. `to_regclass('stg.clean_landing')` returned null.

## Columns

### `dw.dim_date`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `date_key` | `integer` | no | primary key |
| `full_date` | `date` | no | unique |
| `year` | `integer` | no | |
| `quarter` | `integer` | no | |
| `month` | `integer` | no | |
| `month_name` | `varchar(15)` | no | |
| `day_of_month` | `integer` | no | |

Date range: `2020-01-01` through `2030-12-31`.

### `dw.dim_port`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `port_id` | `integer` | no | primary key |
| `port_name` | `varchar(100)` | no | |
| `municipality` | `varchar(100)` | no | |

### `dw.dim_species`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `species_id` | `integer` | no | primary key |
| `species_name` | `varchar(100)` | no | unique |

Species values:

1. Yellowfin Tuna
2. Skipjack Tuna
3. Round Scad
4. Indian Mackerel
5. Sardines
6. Squid
7. Grouper
8. Spanish Mackerel
9. Anchovy
10. Blue Swimming Crab

### `dw.dim_vessel`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `vessel_key` | `bigint` | no | primary key; no column default |
| `vessel_id` | `varchar(30)` | no | |
| `vessel_name` | `varchar(100)` | no | |
| `cooperative_name` | `varchar(100)` | no | |
| `effective_start_date` | `date` | no | |
| `effective_end_date` | `date` | no | check: end >= start |
| `is_current` | `boolean` | no | default `true` |

Current SCD Type 2 rows:

| vessel_key | vessel_id | vessel_name | cooperative_name | start | end | current |
|---:|---|---|---|---|---|---|
| 1 | V001 | M/V Sinar Laut | Bongao Fishers Cooperative | 2020-01-01 | 2024-12-31 | false |
| 11 | V001 | M/V Sinar Laut | Bongao United Cooperative | 2025-01-01 | 9999-12-31 | true |
| 4 | V002 | M/V Nur Asia | Bongao Fishers Cooperative | 2020-01-01 | 9999-12-31 | true |
| 5 | V003 | M/V Samudra | Sitangkai Fishers Cooperative | 2020-01-01 | 9999-12-31 | true |
| 6 | V004 | M/V Abdul Aziz | Sibutu Fishers Cooperative | 2020-01-01 | 9999-12-31 | true |
| 7 | V005 | M/V Barakah | Panglima Sugala Cooperative | 2020-01-01 | 9999-12-31 | true |
| 8 | V006 | M/V Al-Jawari | Sitangkai Fishers Cooperative | 2020-01-01 | 9999-12-31 | true |
| 9 | V007 | M/V Salsabila | Languyan Fishers Cooperative | 2020-01-01 | 9999-12-31 | true |
| 10 | V008 | M/V Al-Fajr | Bongao Fishers Cooperative | 2020-01-01 | 9999-12-31 | true |

`V001` old key `1` is used by 48 fact rows. Current key `11` is not used by
existing facts. The loader must select the version whose date range contains the
landing date.

### `dw.fact_landing`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `landing_id` | `bigint` | no | primary key; `GENERATED ALWAYS AS IDENTITY`; explicit inserts need `OVERRIDING SYSTEM VALUE` |
| `date_key` | `integer` | no | FK to `dw.dim_date` |
| `port_id` | `integer` | no | FK to `dw.dim_port` |
| `species_id` | `integer` | no | FK to `dw.dim_species` |
| `vessel_key` | `bigint` | no | FK to `dw.dim_vessel` |
| `quantity_kg` | `numeric(12,2)` | no | check: >= 0 |
| `value_php` | `numeric(14,2)` | no | check: >= 0 |

## Constraints and Indexes

Primary keys:

- `dw.dim_date(date_key)`
- `dw.dim_port(port_id)`
- `dw.dim_species(species_id)`
- `dw.dim_vessel(vessel_key)`
- `dw.fact_landing(landing_id)`

Unique constraints/indexes:

- `dw.dim_date(full_date)`
- `dw.dim_species(species_name)`
- `uq_dim_vessel_current(vessel_id) WHERE is_current = true`

Foreign keys:

- `dw.fact_landing.date_key -> dw.dim_date.date_key`
- `dw.fact_landing.port_id -> dw.dim_port.port_id`
- `dw.fact_landing.species_id -> dw.dim_species.species_id`
- `dw.fact_landing.vessel_key -> dw.dim_vessel.vessel_key`

Check constraints:

- `dw.dim_vessel.effective_end_date >= effective_start_date`
- `dw.fact_landing.quantity_kg >= 0`
- `dw.fact_landing.value_php >= 0`

## Sequences

| Sequence | Last value |
|---|---:|
| `dw.dim_port_port_id_seq` | 10 |
| `dw.dim_species_species_id_seq` | 10 |
| `dw.dim_vessel_vessel_key_seq` | 11 |
| `dw.fact_landing_landing_id_seq` | 300 |

`dw.dim_vessel.vessel_key` has no column default; new rows must call
`nextval(...)` explicitly. `dw.fact_landing.landing_id` is
`GENERATED ALWAYS AS IDENTITY`; source-supplied IDs require
`OVERRIDING SYSTEM VALUE`, and the identity sequence must be advanced after
explicit inserts.

## Fact Data Profile

| Metric | Value |
|---|---:|
| Rows | 300 |
| Min `quantity_kg` | 53.09 |
| Max `quantity_kg` | 499.27 |
| Total `quantity_kg` | 82,379.80 |
| Min `value_php` | 4,698.36 |
| Max `value_php` | 93,548.53 |
| Total `value_php` | 11,714,339.66 |
| Min fact date | 2024-01-01 |
| Max fact date | 2024-10-26 |

Fact rows by month:

| Year | Month | Rows | Quantity kg | Value PHP |
|---:|---|---:|---:|---:|
| 2024 | January | 54 | 14,130.02 | 1,871,267.06 |
| 2024 | February | 50 | 14,318.78 | 2,007,361.46 |
| 2024 | March | 39 | 10,234.40 | 1,378,013.12 |
| 2024 | April | 24 | 7,912.21 | 882,305.64 |
| 2024 | May | 23 | 6,157.62 | 1,008,200.62 |
| 2024 | June | 22 | 6,581.74 | 863,255.78 |
| 2024 | July | 23 | 6,893.91 | 1,019,809.55 |
| 2024 | August | 23 | 6,570.08 | 979,990.17 |
| 2024 | September | 23 | 5,205.53 | 968,875.46 |
| 2024 | October | 19 | 4,375.51 | 735,260.80 |

## Integrity Findings

| Check | Result |
|---|---:|
| Orphan `fact_landing -> dim_date` | 0 |
| Orphan `fact_landing -> dim_port` | 0 |
| Orphan `fact_landing -> dim_species` | 0 |
| Orphan `fact_landing -> dim_vessel` | 0 |
| Duplicate fact `landing_id` groups | 0 |
| Exact duplicate fact row groups | 0 |
| Duplicate `dim_species` name groups | 0 |
| Duplicate `dim_port` name + municipality groups | 5 |
| Vessels with more than one current row | 0 |
| Vessels with no current row | 0 |
| Invalid vessel date ranges | 0 |
| Current vessel rows with non-sentinel end date | 0 |
| Overlapping vessel SCD ranges | 0 |

Duplicate port detail:

| port_id | port_name | municipality |
|---:|---|---|
| 1 | Bongao Fish Port | Bongao |
| 6 | Bongao Fish Port | Bongao |
| 2 | Panglima Sugala Port | Panglima Sugala |
| 7 | Panglima Sugala Port | Panglima Sugala |
| 3 | Simunul Fish Port | Simunul |
| 8 | Simunul Fish Port | Simunul |
| 4 | Sitangkai Fish Port | Sitangkai |
| 9 | Sitangkai Fish Port | Sitangkai |
| 5 | Languyan Fish Port | Languyan |
| 10 | Languyan Fish Port | Languyan |

The cleaner resolves these duplicates by selecting the lowest `port_id` and
emitting a warning.

## Inspection Commands

```powershell
Get-Content -Raw database\inspect_database.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -

Get-Content -Raw database\data_quality_checks.sql |
  docker exec -i fisheries-postgres18 psql -U postgres -d fisheries_dw -f -
```
