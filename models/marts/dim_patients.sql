{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}

select
    patient_id,
    patient_masked_name,  -- Already made in staging!
    gender,
    marital_status,
    race,
    ethnicity,
    datediff('year', birthdate, current_date) as age,
    case
        when birthdate is null then null
        when datediff('year', birthdate, current_date) < 18 then 'Minor'
        when datediff('year', birthdate, current_date) between 18 and 64 then 'Adult'
        else 'Senior'
    end as age_group,
    birthdate,
    deathdate,
    case
        when deathdate is null then 'Active'
        else 'Deceased'
    end as patient_status,
    region,
    county,
    healthcare_expenses,
    healthcare_coverage
from {{ ref('stg_hl7__patients') }}