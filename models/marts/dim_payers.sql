{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}


SELECT
    payer_id,
    payer_name,
    city,
    region,
    amount_covered,
    amount_uncovered,
    revenue,
    covered_encounters,
    uncovered_encounters,
    covered_medications,
    uncovered_medications,
    covered_procedures,
    uncovered_procedures,
    covered_immunizations,
    uncovered_immunizations,
    unique_customers,
    member_months,
    qols_avg,
    loaded_at,
    
    -- Business-friendly labels
    CASE
        WHEN amount_covered > 0 THEN 'Active Coverage'
        ELSE 'No Coverage'
    END AS coverage_status,
    
    CASE
        WHEN unique_customers > 1000 THEN 'Large Payer'
        WHEN unique_customers BETWEEN 100 AND 1000 THEN 'Medium Payer'
        ELSE 'Small Payer'
    END AS payer_size_tier

FROM {{ ref('stg_hl7__payers') }}