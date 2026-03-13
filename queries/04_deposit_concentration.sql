-- Deposit Concentration and Liquidity Profile
-- Shows deposit balances by type and liquidity classification.
-- Use for ALM analysis, LCR inputs, and funding stability assessment.

SELECT
    ACCOUNT_TYPE,
    LIQUIDITY_CLASS,
    COUNT(*) AS accounts,
    SUM(CURRENT_BAL) AS total_balance,
    AVG(INT_RATE) AS avg_rate,
    AVG(DEPOSIT_BETA) AS avg_beta
FROM bdi_data_201.synthetic_bank.core_deposits
WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.core_deposits)
GROUP BY ACCOUNT_TYPE, LIQUIDITY_CLASS
ORDER BY total_balance DESC;
