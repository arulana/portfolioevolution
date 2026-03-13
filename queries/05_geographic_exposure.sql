-- Geographic Exposure Heatmap
-- Shows funded loan concentration by state.
-- Use for CRA analysis, concentration risk monitoring, and regional strategy.

SELECT
    STATE,
    COUNT(*) AS loan_count,
    SUM(CURRENT_BAL) AS total_funded,
    SUM(COMMITTED_AMT) AS total_committed,
    AVG(RISK_RATING_NUM) AS avg_rating,
    SUM(CASE WHEN SEGMENT = 'cre' THEN CURRENT_BAL ELSE 0 END) AS cre_bal,
    SUM(CASE WHEN SEGMENT = 'c_and_i' THEN CURRENT_BAL ELSE 0 END) AS ci_bal,
    SUM(CASE WHEN SEGMENT = 'multifamily' THEN CURRENT_BAL ELSE 0 END) AS mf_bal,
    SUM(CASE WHEN SEGMENT = 'construction' THEN CURRENT_BAL ELSE 0 END) AS const_bal
FROM bdi_data_201.synthetic_bank.core_funded
WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.core_funded)
GROUP BY STATE
ORDER BY total_funded DESC;
