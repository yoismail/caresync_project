{{ config(
    materialized='table',
    database='NEXORA_STAGING',
    schema='HL7'
) }}

with 
source as (
    select * from {{ source('hl7', 'conditions') }}
),

renamed as (
    select
        PATIENT                     as patient_id,
        ENCOUNTER                   as encounter_id,
        CODE                        as condition_code,
        DESCRIPTION                 as condition_description,

        -- Dates → proper DATE type
        TRY_CAST("START" AS DATE)  as condition_start_date,
        TRY_CAST("STOP" AS DATE)   as condition_end_date,

        -- Flag active conditions
        case
            when "STOP" IS NULL 
              or TRY_CAST("STOP" AS DATE) > CURRENT_DATE
            then true
            else false
        end                         as is_active_condition,

        loaded_at

    from source
)

select * from renamed
