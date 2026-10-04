with 

source as (

    select * from {{ source('hl7', 'patients') }}

),

renamed as (

    select
        id,
        birthdate,
        deathdate,
        ssn,
        drivers,
        passport,
        prefix,
        first,
        last,
        suffix,
        maiden,
        marital,
        race,
        ethnicity,
        gender,
        birthplace,
        address,
        city,
        state,
        county,
        zip,
        lat,
        lon,
        healthcare_expenses,
        healthcare_coverage,
        loaded_at

    from source

)

select * from renamed