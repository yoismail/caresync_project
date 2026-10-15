{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}


SELECT
    patient_id,
    encounter_id,
    condition_code,
    condition_description,
    condition_start_date,
    condition_end_date,
    is_active_condition,
    loaded_at,

    -- Business categorization — remove when not needed
    CASE
        WHEN is_active_condition THEN 'Active'
        ELSE 'Resolved'
    END AS condition_status,

    -- How long the condition lasted (in days)
    DATEDIFF(
        'day',
        condition_start_date,
        COALESCE(condition_end_date, CURRENT_DATE)
    ) AS condition_duration_days

FROM {{ ref('stg_hl7__conditions') }}