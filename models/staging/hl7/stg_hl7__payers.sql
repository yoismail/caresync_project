with 
source as (
    select * from {{ source('hl7', 'payers') }}
),
renamed as (
    select
        id                                      as payer_id,
        name                                    as payer_name,
        
        -- Address generalized
        city,
        state_headquartered                    as region,

        -- Numeric columns: text → proper currency/number types
        amount_covered::number(18,2)             as amount_covered,
        amount_uncovered::number(18,2)           as amount_uncovered,
        revenue::number(18,2)                    as revenue,
        
        -- Integer counts
        covered_encounters::int                  as covered_encounters,
        uncovered_encounters::int                as uncovered_encounters,
        covered_medications::int                 as covered_medications,
        uncovered_medications::int               as uncovered_medications,
        covered_procedures::int                 as covered_procedures,
        uncovered_procedures::int               as uncovered_procedures,
        covered_immunizations::int              as covered_immunizations,
        uncovered_immunizations::int             as uncovered_immunizations,
        unique_customers::int                    as unique_customers,
        member_months::int                       as member_months,
        
        -- Average/decimal values
        qols_avg::number(10,4)                   as qols_avg,

        -- Audit
        loaded_at

        -- Removed: full street address, zip, phone → privacy & cleaner reporting
    from source
)
select * from renamed