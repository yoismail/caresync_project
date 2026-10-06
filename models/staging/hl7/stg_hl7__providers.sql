with 
source as (
    select * from {{ source('hl7', 'providers') }}
),
renamed as (
    select
        id                                      as provider_id,
        organization                            as organization_id,
        name                                    as provider_name,

        -- Standardise gender codes
        case 
            when gender in ('M', 'F', 'O', 'U') then gender 
            else 'U' 
        end                                     as gender,

        speciality                              as specialty,
        city,
        state                                   as region,

        -- Numeric value
        utilization::number(10,4)                as utilization,

        loaded_at

        -- Removed: address, zip, lat, lon — precise location not needed for reporting
    from source
)
select * from renamed