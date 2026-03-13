-- Loan-to-Deposit Ratio and Balance Sheet Summary
-- Shows the bank's high-level balance sheet position.
-- Target LDR for a superregional is typically 0.75-0.90.

WITH latest AS (
    SELECT MAX(sim_day) AS max_day
    FROM bdi_data_201.synthetic_bank.core_funded
),
loans AS (
    SELECT
        SUM(CURRENT_BAL) AS total_funded,
        SUM(COMMITTED_AMT) AS total_committed,
        COUNT(*) AS loan_count
    FROM bdi_data_201.synthetic_bank.core_funded, latest
    WHERE sim_day = latest.max_day
),
deposits AS (
    SELECT
        SUM(CURRENT_BAL) AS total_deposits,
        COUNT(*) AS deposit_count
    FROM bdi_data_201.synthetic_bank.core_deposits, latest
    WHERE sim_day = latest.max_day
),
pipeline AS (
    SELECT
        SUM(EXPECTED_AMOUNT) AS pipeline_value,
        COUNT(*) AS pipeline_count
    FROM (
        SELECT EXPECTED_AMOUNT FROM bdi_data_201.synthetic_bank.crm_pipeline, latest WHERE sim_day = latest.max_day
        UNION ALL
        SELECT REQUESTED_AMOUNT FROM bdi_data_201.synthetic_bank.los_underwriting, latest WHERE sim_day = latest.max_day
    )
)
SELECT
    loans.total_funded,
    loans.total_committed,
    loans.loan_count,
    deposits.total_deposits,
    deposits.deposit_count,
    pipeline.pipeline_value,
    pipeline.pipeline_count,
    loans.total_funded / NULLIF(deposits.total_deposits, 0) AS loan_to_deposit_ratio,
    (loans.total_committed - loans.total_funded) AS undrawn_commitments
FROM loans, deposits, pipeline;
