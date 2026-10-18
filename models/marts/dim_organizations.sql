{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}

WITH organizations AS (

    SELECT * FROM {{ ref('stg_hl7__organizations') }}

),

-- utilization is a raw encounter count (Synthea's UTILIZATION field), not a
-- 0-1 ratio, so tiers are terciles of the actual organization distribution
-- rather than fixed fractional cutoffs that would put every organization in
-- the top bucket.
thresholds AS (

    SELECT
        PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY utilization) AS p33,
        PERCENTILE_CONT(0.67) WITHIN GROUP (ORDER BY utilization) AS p67
    FROM organizations
    WHERE utilization IS NOT NULL

)

SELECT
    o.organization_id,
    o.organization_name,
    o.city,
    o.region,
    o.revenue,
    o.utilization,
    o.loaded_at,

    -- Business-friendly categorization
    CASE
        WHEN o.revenue > 5000000 THEN 'Large Facility'
        WHEN o.revenue BETWEEN 1000000 AND 5000000 THEN 'Medium Facility'
        WHEN o.revenue IS NOT NULL THEN 'Small Facility'
        ELSE 'Unknown'
    END AS facility_size,

    CASE
        WHEN o.utilization >= t.p67 THEN 'High Usage'
        WHEN o.utilization >= t.p33 THEN 'Moderate Usage'
        WHEN o.utilization IS NOT NULL THEN 'Low Usage'
        ELSE 'Unknown'
    END AS utilization_level

FROM organizations o
CROSS JOIN thresholds t