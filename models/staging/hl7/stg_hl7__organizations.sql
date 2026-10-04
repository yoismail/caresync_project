with 

source as (

    select * from {{ source('hl7', 'organizations') }}

),

renamed as (

    select
        id,
        name,
        address,
        city,
        state,
        zip,
        lat,
        lon,
        phone,
        revenue,
        utilization,
        loaded_at

    from source

)

select * from renamed