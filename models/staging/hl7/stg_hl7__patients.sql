{{ config(
    materialized='table',
    database='NEXORA_STAGING',
    schema='HL7'
) }}

with 
source as (
    select * from {{ source('hl7', 'patients') }}
),
renamed as (
    select
        id                                          as patient_id,


        -- Masked name from separate first + last columns — both initialed. This can't identify a patient
        left(first, 1) || '.' || left(last, 1) || '.' as patient_masked_name,
        
        -- PHI REMOVED — drop sensitive columns entirely
        -- ssn, drivers, passport, prefix, first, last, suffix, maiden, birthplace, full address → NOT included

        -- Standardize gender values
        case 
            when gender in ('M', 'male', 'Male') then 'M'
            when gender in ('F', 'female', 'Female') then 'F'
            when gender in ('O', 'U', 'Unknown', '') or gender is null then 'U'
            else 'U'
        end as gender,
        
        -- Standardize marital status
        case 
            when marital in ('S', 'M', 'D', 'W', 'U') then marital
            when marital = '' or marital is null or marital = 'None' then 'U'
            else 'U'
        end as marital_status,  
        
        race,
        ethnicity,
        
        -- Convert to proper date types
        birthdate::date                             as birthdate,
        deathdate::date                             as deathdate,
        
        -- Region/county
        case when state != '' then state else null end
                                                    as region,
        nullif(county, '')                          as county,
        
        -- Financial values
        healthcare_expenses::number(18,2)           as healthcare_expenses,
        healthcare_coverage::number(18,2)           as healthcare_coverage,
        
        loaded_at
    from source
)
select * from renamed