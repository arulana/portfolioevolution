-- Funded Book Summary by Segment
-- Shows total balances, average rates, average ratings, and loan counts per segment.
-- Use to understand portfolio composition and concentration.

SELECT
    SEGMENT,
    COUNT(*) AS loan_count,
    SUM(CURRENT_BAL) AS total_funded_bal,
    SUM(COMMITTED_AMT) AS total_committed,
    SUM(COMMITTED_AMT) - SUM(CURRENT_BAL) AS total_undrawn,
    AVG(INT_RATE) AS avg_rate,
    AVG(RISK_RATING_NUM) AS avg_risk_rating,
    SUM(CASE WHEN RISK_RATING_NUM >= 7 THEN CURRENT_BAL ELSE 0 END) AS classified_bal,
    SUM(CASE WHEN TDR_FLAG = true THEN CURRENT_BAL ELSE 0 END) AS tdr_bal
FROM bdi_data_201.synthetic_bank.core_funded
WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.core_funded)
GROUP BY SEGMENT
ORDER BY total_funded_bal DESC;
