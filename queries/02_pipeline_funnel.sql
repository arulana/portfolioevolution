-- Pipeline Funnel — CRM + LOS Combined
-- Shows deal counts and amounts at every stage from Lead through Closing.
-- Use to assess pipeline health and conversion rates.

SELECT stage, deal_count, total_amount, avg_close_prob, source_system
FROM (
    SELECT
        STAGE AS stage,
        COUNT(*) AS deal_count,
        SUM(EXPECTED_AMOUNT) AS total_amount,
        AVG(CLOSE_PROB) AS avg_close_prob,
        'CRM' AS source_system,
        CASE STAGE
            WHEN 'lead' THEN 1
            WHEN 'term_sheet' THEN 2
        END AS sort_order
    FROM bdi_data_201.synthetic_bank.crm_pipeline
    WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.crm_pipeline)
    GROUP BY STAGE

    UNION ALL

    SELECT
        UW_STAGE AS stage,
        COUNT(*) AS deal_count,
        SUM(REQUESTED_AMOUNT) AS total_amount,
        NULL AS avg_close_prob,
        'LOS' AS source_system,
        CASE UW_STAGE
            WHEN 'underwriting' THEN 3
            WHEN 'approved' THEN 4
            WHEN 'documentation' THEN 5
            WHEN 'closing' THEN 6
        END AS sort_order
    FROM bdi_data_201.synthetic_bank.los_underwriting
    WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.los_underwriting)
    GROUP BY UW_STAGE
)
ORDER BY sort_order;
