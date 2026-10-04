with 

source as (

    select * from {{ source('hl7', 'encounters') }}

),

renamed as (

    select
        id,
        encounter_start,
        encounter_stop,
        patient,
        organization,
        provider,
        payer,
        encounterclass,
        code,
        description,
        base_encounter_cost,
        total_claim_cost,
        payer_coverage,
        reasoncode,
        reasondescription,
        loaded_at

    from source

)

select * from renamed