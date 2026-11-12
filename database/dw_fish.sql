
BEGIN;

WITH old_vessel AS (
    UPDATE dw.dim_vessel
    SET
        effective_end_date = DATE '2024-12-31',
        is_current = FALSE
    WHERE vessel_id = 'V001'
      AND is_current = TRUE
      AND effective_start_date = DATE '2020-01-01'
    RETURNING vessel_id, vessel_name
)
INSERT INTO dw.dim_vessel (
    vessel_id,
    vessel_name,
    cooperative_name,
    effective_start_date,
    effective_end_date,
    is_current
)
SELECT
    vessel_id,
    vessel_name,
    'Bongao United Cooperative',
    DATE '2025-01-01',
    DATE '9999-12-31',
    TRUE
FROM old_vessel;

COMMIT;


SELECT
    vessel_key,
    vessel_id,
    vessel_name,
    cooperative_name,
    effective_start_date,
    effective_end_date,
    is_current
FROM dw.dim_vessel
WHERE vessel_id = 'V001'
ORDER BY effective_start_date;


SELECT
    v.vessel_id,
    v.cooperative_name,
    v.effective_start_date,
    v.effective_end_date,
    v.is_current,
    COUNT(f.landing_id) AS landing_records,
    ROUND(COALESCE(SUM(f.quantity_kg), 0), 2) AS total_kg
FROM dw.dim_vessel v
LEFT JOIN dw.fact_landing f
    ON v.vessel_key = f.vessel_key
WHERE v.vessel_id = 'V001'
GROUP BY
    v.vessel_id,
    v.cooperative_name,
    v.effective_start_date,
    v.effective_end_date,
    v.is_current
ORDER BY v.effective_start_date;

SELECT COUNT (*) AS total_records
FROM dw.fact_landing;

SELECT
    vessel_id,
    vessel_name,
    cooperative_name,
    effective_start_date,
    effective_end_date,
    is_current
FROM dw.dim_vessel
WHERE vessel_id = 'V001'
ORDER BY effective_start_date;

SELECT
    v.cooperative_name,
    v.effective_start_date,
    COUNT(f.landing_id) AS landing_records,
    ROUND(COALESCE(SUM(f.quantity_kg), 0), 2) AS total_kg
FROM dw.dim_vessel v
LEFT JOIN dw.fact_landing f
    ON v.vessel_key = f.vessel_key
WHERE v.vessel_id = 'V001'
GROUP BY
    v.cooperative_name,
    v.effective_start_date
ORDER BY v.effective_start_date;

SELECT
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(f.quantity_kg), 2) AS total_kg
FROM dw.fact_landing f
JOIN dw.dim_date d ON f.date_key = d.date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

WITH species_totals AS (
    SELECT
        p.port_name,
        s.species_name,
        SUM(f.quantity_kg) AS total_kg
    FROM dw.fact_landing f
    JOIN dw.dim_port p ON f.port_id = p.port_id
    JOIN dw.dim_species s ON f.species_id = s.species_id
    GROUP BY
        p.port_id, p.port_name,
        s.species_id, s.species_name
),
ranked_species AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY port_name
            ORDER BY total_kg DESC
        ) AS species_rank
    FROM species_totals
)
SELECT
    port_name,
    species_name,
    ROUND(total_kg, 2) AS total_kg
FROM ranked_species
WHERE species_rank = 1
ORDER BY port_name;

SELECT
    v.cooperative_name,
    ROUND(SUM(f.value_php), 2) AS total_value_php
FROM dw.fact_landing f
JOIN dw.dim_vessel v ON f.vessel_key = v.vessel_key
GROUP BY v.cooperative_name
ORDER BY total_value_php DESC;

SELECT
    v.cooperative_name,
    v.effective_start_date,
    COUNT(f.landing_id) AS landing_records,
    ROUND(
        COALESCE(SUM(f.quantity_kg), 0),
        2
    ) AS total_kg
FROM dw.dim_vessel v
LEFT JOIN dw.fact_landing f
    ON v.vessel_key = f.vessel_key
WHERE v.vessel_id = 'V001'
GROUP BY
    v.cooperative_name,
    v.effective_start_date
ORDER BY v.effective_start_date;  