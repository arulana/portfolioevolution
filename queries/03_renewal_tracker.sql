-- Renewal Tracker
-- Shows all renewal submissions currently in the LOS pipeline.
-- Renewals are maturing funded loans re-entering underwriting (~80% renewal rate).
-- Use to monitor renewal volume, approval pipeline, and potential runoff.

SELECT
    APP_ID,
    BORROWER_NAME,
    UW_STAGE,
    REQUESTED_AMOUNT,
    APPROVED_AMOUNT,
    RISK_RATING,
    RATING_NUMERIC,
    SEGMENT,
    STATE,
    EXPECTED_CLOSE_DATE
FROM bdi_data_201.synthetic_bank.los_underwriting
WHERE IS_RENEWAL = true
  AND sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.los_underwriting)
ORDER BY REQUESTED_AMOUNT DESC;
