with 
source as (
    select * from {{ source('hl7', 'encounters') }}
),
renamed as (
    select
        id                                      as encounter_id,
        patient                                 as patient_id,
        organization                            as organization_id,
        provider                                as provider_id,
        payer                                   as payer_id,

        -- Timestamps → proper datetime type
        encounter_start::timestamp_ntz           as encounter_start,
        encounter_stop::timestamp_ntz            as encounter_end,

        -- Standardise encounter class values
        case 
            when encounterclass in (
                'ambulatory', 
                'inpatient', 
                'outpatient', 
                'emergency', 
                'urgentcare', 
                'wellness', 
                'other'
            ) 
            then encounterclass 
            else 'other' 
        end                                     as encounter_class,

        code                                    as encounter_code,
        description                             as encounter_description,
        reasoncode                              as reason_code,
        reasondescription                       as reason_description,

        -- Financial values → proper currency type
        base_encounter_cost::number(18,2)        as base_encounter_cost,
        total_claim_cost::number(18,2)           as total_claim_cost,
        payer_coverage::number(18,2)             as payer_coverage,

        loaded_at
    from source
)
select * from renamed