{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}


SELECT
    organization_id,
    organization_name,
    city,
    region,
    revenue,
    utilization,
    loaded_at,

    -- Business-friendly categorization
    CASE
        WHEN revenue > 5000000 THEN 'Large Facility'
        WHEN revenue BETWEEN 1000000 AND 5000000 THEN 'Medium Facility'
        WHEN revenue IS NOT NULL THEN 'Small Facility'
        ELSE 'Unknown'
    END AS facility_size,

    CASE
        WHEN utilization >= 0.8 THEN 'High Usage'
        WHEN utilization >= 0.5 THEN 'Moderate Usage'
        WHEN utilization IS NOT NULL THEN 'Low Usage'
        ELSE 'Unknown'
    END AS utilization_level

FROM {{ ref('stg_hl7__organizations') }}