with 

source as (

    select * from {{ source('hl7', 'payers') }}

),

renamed as (

    select
        id,
        name,
        address,
        city,
        state_headquartered,
        zip,
        phone,
        amount_covered,
        amount_uncovered,
        revenue,
        covered_encounters,
        uncovered_encounters,
        covered_medications,
        uncovered_medications,
        covered_procedures,
        uncovered_procedures,
        covered_immunizations,
        uncovered_immunizations,
        unique_customers,
        qols_avg,
        member_months,
        loaded_at

    from source

)

select * from renamed