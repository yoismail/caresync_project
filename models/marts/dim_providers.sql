{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}

WITH providers AS (

    SELECT * FROM {{ ref('stg_hl7__providers') }}

),

-- utilization is a raw encounter count (Synthea's UTILIZATION field), not a
-- 0-1 ratio, so tiers are terciles of the actual provider distribution
-- rather than fixed fractional cutoffs that would put every provider in the
-- top bucket.
thresholds AS (

    SELECT
        PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY utilization) AS p33,
        PERCENTILE_CONT(0.67) WITHIN GROUP (ORDER BY utilization) AS p67
    FROM providers
    WHERE utilization IS NOT NULL

)

SELECT
    p.provider_id,
    p.organization_id,
    p.provider_name,
    p.gender,
    p.specialty,
    p.city,
    p.region,
    p.utilization,
    p.loaded_at,

    -- Business categorization
    CASE
        WHEN p.specialty IN ('General Practice', 'Family Practice', 'Primary Care') THEN 'Primary Care'
        WHEN p.specialty IN ('Internal Medicine', 'Cardiology', 'Neurology', 'Pediatrics') THEN 'Specialist'
        ELSE 'Other Specialty'
    END AS specialty_category,

    CASE
        WHEN p.utilization >= t.p67 THEN 'High Caseload'
        WHEN p.utilization >= t.p33 THEN 'Moderate Caseload'
        WHEN p.utilization IS NOT NULL THEN 'Low Caseload'
        ELSE 'Unknown'
    END AS caseload_level

FROM providers p
CROSS JOIN thresholds t