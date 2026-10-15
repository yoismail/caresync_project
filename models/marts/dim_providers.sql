{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}


SELECT
    provider_id,
    organization_id,
    provider_name,
    gender,
    specialty,
    city,
    region,
    utilization,
    loaded_at,

    -- Business categorization 
    CASE
        WHEN specialty IN ('General Practice', 'Family Practice', 'Primary Care') THEN 'Primary Care'
        WHEN specialty IN ('Internal Medicine', 'Cardiology', 'Neurology', 'Pediatrics') THEN 'Specialist'
        ELSE 'Other Specialty'
    END AS specialty_category,

    CASE
        WHEN utilization >= 0.8 THEN 'High Caseload'
        WHEN utilization >= 0.5 THEN 'Moderate Caseload'
        WHEN utilization IS NOT NULL THEN 'Low Caseload'
        ELSE 'Unknown'
    END AS caseload_level

FROM {{ ref('stg_hl7__providers') }}