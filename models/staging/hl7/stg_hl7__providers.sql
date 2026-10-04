with 

source as (

    select * from {{ source('hl7', 'providers') }}

),

renamed as (

    select
        id,
        organization,
        name,
        gender,
        speciality,
        address,
        city,
        state,
        zip,
        lat,
        lon,
        utilization,
        loaded_at

    from source

)

select * from renamed