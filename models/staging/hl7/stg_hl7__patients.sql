with
    source as (select * from {{ source("hl7", "patients") }}),
    renamed as (
        select
            id as patient_id,

            -- Masked name from separate first + last columns
            left(first, 1) || '.' || last as patient_masked_name,

            -- PHI REMOVED — drop sensitive columns entirely
            -- ssn, drivers, passport, prefix, first, last, suffix, maiden,
            -- birthplace, full address → NOT included
            -- Standardize gender values
            case when gender in ('M', 'F', 'O', 'U') then gender else 'U' end as gender,

            -- Standardize marital status
            case
                when marital in ('S', 'M', 'D', 'W', 'U') then marital else 'U'
            end as marital_status,

            race,
            ethnicity,

            -- Convert to proper date types
            birthdate::date as birthdate,
            deathdate::date as deathdate,

            -- Reduce address — keep only region/county level
            case when state != '' then state else null end as region,
            nullif(city, '') as county,

            -- Financial values as proper numbers
            healthcare_expenses::number(18, 2) as healthcare_expenses,
            healthcare_coverage::number(18, 2) as healthcare_coverage,

            loaded_at
        from source
    )
select *
from renamed
