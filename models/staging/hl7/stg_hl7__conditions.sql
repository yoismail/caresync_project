with 
source as (
    select * from {{ source('hl7', 'conditions') }}
),
renamed as (
    select
        patient                                 as patient_id,
        encounter                               as encounter_id,
        code                                    as condition_code,
        description                             as condition_description,

        -- Dates → proper DATE type
        condition_start::date                   as condition_start_date,
        condition_stop::date                    as condition_end_date,

        -- Flag active conditions
        case
            when condition_stop is null 
                 or condition_stop::date > current_date
            then true
            else false
        end                                     as is_active_condition,

        loaded_at
    from source
)
select * from renamed