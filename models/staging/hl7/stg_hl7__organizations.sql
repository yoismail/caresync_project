with 
source as (
    select * from {{ source('hl7', 'organizations') }}
),
renamed as (
    select
        id                                      as organization_id,
        name                                    as organization_name,
        city,
        state                                   as region,

        -- Numeric columns → proper types
        revenue::number(18,2)                    as revenue,
        utilization::number(10,4)                as utilization,

        loaded_at

        -- Removed: address, zip, lat, lon, phone — precise detail not needed for reporting
    from source
)
select * from renamed