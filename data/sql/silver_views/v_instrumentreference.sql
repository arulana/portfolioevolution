-- Silver view: instrumentreference
-- Derives from raw core_funded + los_underwriting tables.
-- Replicates translate.py logic: translate_core_funded_to_instrument + translate_los_underwriting_to_instrument
--
-- Usage: CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.instrumentreference AS ...
-- Parameters: ${catalog}, ${raw_schema}, ${silver_schema}

CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.instrumentreference AS

WITH sofr_lookup AS (
    SELECT effective_date, sofr_90_day
    FROM ${catalog}.${raw_schema}.lookup_sofr
),

-- CRD instruments from core_funded
crd AS (
    SELECT
        AS_OF_DATE                          AS asOfDate,
        ACCT_NO                             AS instrumentIdentifier,
        ENTITY_ID                           AS entityIdentifier,
        PRODUCT_TYPE                        AS instrumentType,
        ORIG_DATE                           AS originationDate,
        MATURITY_DATE                       AS maturityDate,
        CAST(COMMITTED_AMT AS DOUBLE)       AS currentCommitmentAmount,
        CAST(CURRENT_BAL AS DOUBLE)         AS unpaidPrincipalBalance,
        GREATEST(
            COALESCE(CAST(CURRENT_BAL AS DOUBLE), 0),
            COALESCE(CAST(COMMITTED_AMT AS DOUBLE), 0)
        )                                   AS originalNotionalAmount,
        CAST(INT_RATE AS DOUBLE)            AS currentRate,
        RATE_TYPE                           AS interestRateType,
        ORIG_DATE                           AS _orig_date_for_sofr,
        COALESCE(PMT_FREQ, 'Monthly')       AS interestPaymentFrequency,
        CASE WHEN PRODUCT_TYPE = 'Line of Credit' THEN 1 ELSE 0 END AS revolving,
        CASE WHEN PRODUCT_TYPE = 'Line of Credit' THEN 'Revolving' ELSE 'Term' END AS creditLensProductCategory,
        RISK_RATING_NUM                     AS internalRating,
        RISK_RATING                         AS internalRatingDescription,
        ACCT_NO                             AS instrumentName,
        'CRD'                               AS importSource
    FROM ${catalog}.${raw_schema}.core_funded
),

crd_with_spread AS (
    SELECT
        crd.*,
        CASE
            WHEN crd.interestRateType = 'Variable' AND crd._orig_date_for_sofr IS NOT NULL THEN
                ROUND(GREATEST(0,
                    COALESCE(crd.currentRate * 100.0, 0) -
                    COALESCE(
                        (SELECT s.sofr_90_day
                         FROM sofr_lookup s
                         WHERE s.effective_date <= crd._orig_date_for_sofr
                         ORDER BY s.effective_date DESC
                         LIMIT 1),
                        0)
                ), 5)
            ELSE NULL
        END AS interestRateSpread,
        CASE WHEN crd.interestRateType = 'Variable' THEN 'SOFR' ELSE NULL END AS repricingIndex,
        CASE WHEN crd.interestRateType = 'Variable' THEN '3 Month' ELSE NULL END AS repricingTenor,
        CASE WHEN crd.interestRateType = 'Variable' THEN 'Monthly' ELSE NULL END AS interestRateResetFrequency
    FROM crd
),

-- CREDITLENS instruments from los_underwriting
cl AS (
    SELECT
        AS_OF_DATE                          AS asOfDate,
        APP_ID                              AS instrumentIdentifier,
        ENTITY_ID                           AS entityIdentifier,
        'Loan'                              AS instrumentType,
        APPROVAL_DATE                       AS originationDate,
        EXPECTED_CLOSE_DATE                 AS maturityDate,
        CAST(APPROVED_AMOUNT AS DOUBLE)     AS currentCommitmentAmount,
        CAST(REQUESTED_AMOUNT AS DOUBLE)    AS unpaidPrincipalBalance,
        CAST(APPROVED_AMOUNT AS DOUBLE)     AS originalNotionalAmount,
        CAST(EXPECTED_RATE AS DOUBLE)       AS currentRate,
        RATE_TYPE                           AS interestRateType,
        CAST(NULL AS STRING)                AS _orig_date_for_sofr,
        'Monthly'                           AS interestPaymentFrequency,
        CAST(NULL AS INT)                   AS revolving,
        'Term'                              AS creditLensProductCategory,
        RATING_NUMERIC                      AS internalRating,
        RISK_RATING                         AS internalRatingDescription,
        APP_ID                              AS instrumentName,
        'CREDITLENS'                        AS importSource,
        CAST(NULL AS DOUBLE)                AS interestRateSpread,
        CAST(NULL AS STRING)                AS repricingIndex,
        CAST(NULL AS STRING)                AS repricingTenor,
        CAST(NULL AS STRING)                AS interestRateResetFrequency
    FROM ${catalog}.${raw_schema}.los_underwriting
)

SELECT
    asOfDate,
    instrumentIdentifier,
    entityIdentifier,
    instrumentType,
    originationDate,
    maturityDate,
    currentCommitmentAmount,
    unpaidPrincipalBalance,
    originalNotionalAmount,
    currentRate,
    interestRateType,
    interestRateSpread,
    interestPaymentFrequency,
    CAST(NULL AS STRING) AS interestRateResetFirstDate,
    repricingIndex,
    repricingTenor,
    interestRateResetFrequency,
    revolving,
    CAST(NULL AS STRING) AS creditLensProductType,
    creditLensProductCategory,
    CAST(NULL AS STRING) AS creditLensFacilityProductStatus,
    CAST(NULL AS STRING) AS creditLensProductApprovalStatus,
    CAST(NULL AS DOUBLE) AS collateralValue,
    internalRating,
    internalRatingDescription,
    instrumentName,
    CAST(NULL AS STRING) AS loanAccountingSystemIdentifier,
    CAST(NULL AS STRING) AS regulatoryRating,
    importSource
FROM crd_with_spread

UNION ALL

SELECT
    asOfDate,
    instrumentIdentifier,
    entityIdentifier,
    instrumentType,
    originationDate,
    maturityDate,
    currentCommitmentAmount,
    unpaidPrincipalBalance,
    originalNotionalAmount,
    currentRate,
    interestRateType,
    interestRateSpread,
    interestPaymentFrequency,
    CAST(NULL AS STRING) AS interestRateResetFirstDate,
    repricingIndex,
    repricingTenor,
    interestRateResetFrequency,
    revolving,
    CAST(NULL AS STRING) AS creditLensProductType,
    creditLensProductCategory,
    CAST(NULL AS STRING) AS creditLensFacilityProductStatus,
    CAST(NULL AS STRING) AS creditLensProductApprovalStatus,
    CAST(NULL AS DOUBLE) AS collateralValue,
    internalRating,
    internalRatingDescription,
    instrumentName,
    CAST(NULL AS STRING) AS loanAccountingSystemIdentifier,
    CAST(NULL AS STRING) AS regulatoryRating,
    importSource
FROM cl
