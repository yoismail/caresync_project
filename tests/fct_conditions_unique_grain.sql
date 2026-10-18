-- fct_conditions has no natural single-column primary key (Synthea's
-- conditions.csv doesn't assign one), so its grain — one row per diagnosis
-- — is enforced here as a composite-key uniqueness check instead of the
-- usual unique/not_null pair on a single PK column.
-- dbt fails this test if it returns any rows.

select
    patient_id,
    encounter_id,
    condition_code,
    condition_start_date,
    count(*) as row_count
from {{ ref('fct_conditions') }}
group by patient_id, encounter_id, condition_code, condition_start_date
having count(*) > 1
