{{ config(
    materialized='table',
    database='NEXORA_PROD',
    schema='HL7'
) }}

with patients as (

    select * from {{ ref('stg_hl7__patients') }}

),

aged as (

    select
        *,
        -- Age as of death for deceased patients, as of today for active
        -- ones — otherwise a deceased patient's age keeps climbing forever.
        -- DATEDIFF('year', ...) alone only counts calendar-year boundaries
        -- crossed, not whether the birthday has actually happened yet, so
        -- subtract 1 when the as-of date falls before this year's birthday.
        datediff('year', birthdate, coalesce(deathdate, current_date))
            - case
                when to_char(coalesce(deathdate, current_date), 'MMDD') < to_char(birthdate, 'MMDD')
                then 1 else 0
            end as age
    from patients

)

select
    patient_id,
    patient_masked_name,  -- Already made in staging!
    gender,
    marital_status,
    race,
    ethnicity,
    age,
    case
        when birthdate is null then null
        when age < 18 then 'Minor'
        when age between 18 and 64 then 'Adult'
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
from aged