with 

source as (

    select * from {{ source('hl7', 'conditions') }}

),

renamed as (

    select
        condition_start,
        condition_stop,
        patient,
        encounter,
        code,
        description,
        loaded_at

    from source

)

select * from renamed