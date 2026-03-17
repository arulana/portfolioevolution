-- Silver view: entityfinancialstatement
-- Derives from raw financial_spreads table.
-- Replicates translate.py logic: translate_financial_spreads (SCREAMING_SNAKE_CASE -> camelCase)
--
-- Usage: CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.v_entityfinancialstatement AS ...
-- Parameters: ${catalog}, ${raw_schema}, ${silver_schema}

CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.v_entityfinancialstatement AS

SELECT
    ENTITY_IDENTIFIER                       AS entityIdentifier,
    FINANCIAL_STATEMENT_DATE                AS financialStatementDate,
    FINANCIAL_STATEMENT_YEAR                AS financialStatementYear,
    FINANCIAL_STATEMENT_REFERENCE           AS financialStatementReference,
    AS_OF_DATE                              AS asOfDate,

    -- Income statement
    NET_SALES                               AS netSales,
    TOTAL_OPERATING_REVENUE                 AS totalOperatingRevenue,
    TOTAL_COST_OF_GOODS_SOLD                AS totalCostOfGoodsSold,
    COST_OF_SALES_DEPRECIATION              AS costOfSalesDepreciation,
    GROSS_PROFIT                            AS grossProfit,
    SGA_EXPENSES                            AS sgaExpenses,
    OPERATING_EXPENSE_OTHER                 AS operatingExpenseOther,
    TOTAL_AMORTIZATION_AND_DEPRECIATION     AS totalAmortizationAndDepreciation,
    TOTAL_OPERATING_EXPENSE                 AS totalOperatingExpense,
    TOTAL_OPERATING_PROFIT                  AS totalOperatingProfit,
    OTHER_INCOME                            AS otherIncome,
    OTHER_EXPENSES                          AS otherExpenses,
    EBITDA                                  AS ebitda,
    EBIT                                    AS ebit,
    GROSS_INTEREST_INCOME                   AS grossInterestIncome,
    TOTAL_INTEREST_EXPENSE                  AS totalInterestExpense,
    CAPITALIZED_INTEREST_EXPENSE            AS capitalizedInterestExpense,
    MINORITY_INTEREST_EXPENSE               AS minorityInterestExpense,
    CURRENT_INCOME_TAX_EXPENSE              AS currentIncomeTaxExpense,
    TOTAL_EXTRAORDINARY_ITEMS               AS totalExtraordinaryItems,
    NET_INCOME                              AS netIncome,

    -- Balance sheet
    CASH_AND_MARKETABLE_SECURITIES          AS cashAndMarketableSecurities,
    RECEIVABLE_FROM_TRADE                   AS receivableFromTrade,
    TOTAL_ACCOUNTS_RECEIVABLE               AS totalAccountsReceivable,
    TOTAL_INVENTORY                         AS totalInventory,
    OTHER_CURRENT_ASSETS                    AS otherCurrentAssets,
    TOTAL_CURRENT_ASSETS                    AS totalCurrentAssets,
    TOTAL_FIXED_ASSETS                      AS totalFixedAssets,
    TOTAL_ACCUMULATED_DEPRECIATION          AS totalAccumulatedDepreciation,
    TOTAL_LONG_TERM_INVESTMENTS             AS totalLongTermInvestments,
    TOTAL_INTANGIBLE_ASSETS                 AS totalIntangibleAssets,
    OTHER_ASSETS                            AS otherAssets,
    TOTAL_NON_CURRENT_ASSETS                AS totalNonCurrentAssets,
    TOTAL_ASSETS                            AS totalAssets,
    SHORT_TERM_DEBT                         AS shortTermDebt,
    PAYABLE_TO_TRADE                        AS payableToTrade,
    TOTAL_ACCOUNTS_PAYABLE                  AS totalAccountsPayable,
    TOTAL_ACCRUED_LIABILITIES               AS totalAccruedLiabilities,
    OTHER_CURRENT_LIABILITIES               AS otherCurrentLiabilities,
    TOTAL_CURRENT_LIABILITIES               AS totalCurrentLiabilities,
    TOTAL_LONG_TERM_DEBT                    AS totalLongTermDebt,
    TOTAL_SUBORDINATED_DEBT                 AS totalSubordinatedDebt,
    OTHER_NON_CURRENT_LIABILITIES           AS otherNonCurrentLiabilities,
    TOTAL_NON_CURRENT_LIABILITIES           AS totalNonCurrentLiabilities,
    TOTAL_LIABILITIES                       AS totalLiabilities,
    RETAINED_EARNINGS                       AS retainedEarnings,
    NET_WORTH                               AS netWorth,
    TOTAL_LIABILITIES_AND_NET_WORTH         AS totalLiabilitiesAndNetWorth

FROM ${catalog}.${raw_schema}.financial_spreads
