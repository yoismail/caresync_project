{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}


SELECT
    encounter_id,
    patient_id,
    organization_id,
    provider_id,
    payer_id,
    encounter_start,
    encounter_end,
    encounter_class,
    encounter_code,
    encounter_description,
    reason_code,
    reason_description,
    base_encounter_cost,
    total_claim_cost,
    payer_coverage,
    loaded_at,

    -- Business calculations 
    DATEDIFF('minute', encounter_start, encounter_end) AS encounter_duration_minutes,

    CASE
        WHEN payer_coverage >= total_claim_cost THEN 'Fully Covered'
        WHEN payer_coverage > 0 THEN 'Partially Covered'
        ELSE 'Uncovered'
    END AS coverage_status,

    ROUND(
        (payer_coverage / NULLIF(total_claim_cost, 0)) * 100,
        2
    ) AS coverage_percentage,

    CASE
        WHEN DATE_PART('hour', encounter_start) BETWEEN 9 AND 17 THEN 'Hours: 9–5'
        ELSE 'Hours: Outside 9–5'
    END AS time_of_day_category

FROM {{ ref('stg_hl7__encounters') }}