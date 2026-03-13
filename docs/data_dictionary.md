# Data Dictionary — Synthetic Bank

**Location:** `bdi_data_201.synthetic_bank`
**Updated:** 2026-03-13
**Profile:** US superregional bank, ~$100B total assets

---

## Common Fields

These fields appear in all four tables:

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | STRING | Unique simulation run identifier. Groups all snapshots from a single run. |
| `sim_day` | INT | Simulation day number (0 = initial as-of date). Increments by 1 per business day. Use to track changes over time. |

---

## crm_pipeline

**Source System:** CRM (Customer Relationship Management)
**Description:** Early-stage pipeline deals being managed by relationship managers. Represents opportunities before formal credit submission. Deals advance to `los_underwriting` when a term sheet is accepted.

| Field | Type | Description | Example Values |
|-------|------|-------------|----------------|
| `OPP_ID` | STRING | Opportunity ID, unique in CRM | `OPP-00042` |
| `BORROWER_NAME` | STRING | Legal entity name of the prospective borrower | `Metro Properties LLC` |
| `STAGE` | STRING | Current CRM stage | `Lead`, `Term Sheet` |
| `EXPECTED_AMOUNT` | DOUBLE | Expected deal size (USD) | `4500000.0` |
| `CLOSE_PROB` | DOUBLE | Estimated close probability (0.0 to 1.0) | `0.25` |
| `SEGMENT` | STRING | Lending segment | `cre`, `c_and_i`, `multifamily`, `construction`, `specialty` |
| `RM_NAME` | STRING | Assigned relationship manager | `Jay Shah` |
| `RM_CODE` | STRING | RM employee code | `245` |
| `EXPECTED_CLOSE_DATE` | STRING | Projected close date (ISO) | `2026-04-15` |
| `LAST_ACTIVITY_DATE` | STRING | Date of last CRM activity | `2026-01-02` |
| `STATE` | STRING | US state of collateral/borrower | `OH`, `PA`, `NY` |
| `SOURCE` | STRING | Source system identifier | Always `crm` |

**Key relationships:**
- Deals that advance past Term Sheet move to `los_underwriting` (same borrower, new APP_ID)
- `CLOSE_PROB` is the RM's subjective estimate, not the engine's transition probability

---

## los_underwriting

**Source System:** LOS (Loan Origination System)
**Description:** Deals in active credit underwriting through closing. Includes both new originations (from CRM) and renewal submissions from maturing funded loans. Deals that close and fund move to `core_funded`.

| Field | Type | Description | Example Values |
|-------|------|-------------|----------------|
| `APP_ID` | STRING | Application ID, unique in LOS. Renewals prefixed `RNW-`. | `OPP-00042`, `RNW-000123-2026-03-15` |
| `BORROWER_NAME` | STRING | Legal entity name | `Metro Properties LLC` |
| `UW_STAGE` | STRING | Underwriting stage | `underwriting`, `approved`, `documentation`, `closing` |
| `REQUESTED_AMOUNT` | DOUBLE | Loan amount requested (USD) | `4500000.0` |
| `APPROVED_AMOUNT` | DOUBLE | Credit-approved amount (USD). NULL if not yet approved. | `4200000.0` |
| `RISK_RATING` | STRING | Internal risk rating letter | `AAA`, `AA`, `A`, `BBB`, `BB`, `B`, `CCC`, `CC`, `D` |
| `RATING_NUMERIC` | INT | Risk rating numeric (1=best, 9=default) | `4` |
| `ANALYST_CODE` | STRING | Credit analyst or RM code | `245` |
| `APPROVAL_DATE` | STRING | Date credit was approved (NULL if pending) | `2026-02-10` |
| `EXPECTED_CLOSE_DATE` | STRING | Projected closing date (ISO) | `2026-04-15` |
| `RATE_TYPE` | STRING | Interest rate type | `fixed`, `floating` |
| `EXPECTED_RATE` | DOUBLE | Expected coupon rate (decimal) | `0.065` (= 6.5%) |
| `SEGMENT` | STRING | Lending segment | `cre`, `c_and_i`, `multifamily`, `construction`, `specialty` |
| `STATE` | STRING | US state | `OH`, `PA`, `NY` |
| `IS_RENEWAL` | BOOLEAN | True if this is a renewal of a maturing funded loan | `true`, `false` |
| `CONDITION_COUNT` | INT | Number of conditions precedent to closing | `3` |

**Key relationships:**
- `APP_ID` links back to `OPP_ID` in `crm_pipeline` for new originations
- Renewal `APP_ID` format: `RNW-{original_ACCT_NO}-{maturity_date}` links to `core_funded.ACCT_NO`
- Funded deals create a new row in `core_funded`

---

## core_funded

**Source System:** Core Banking
**Description:** On-balance-sheet funded loan positions. Daily snapshot with current balances, rates, ratings, and collateral details. Loans enter when deals fund from `los_underwriting`. Loans exit via maturity (renewal back to LOS, ~80%) or prepayment (runoff).

| Field | Type | Description | Example Values |
|-------|------|-------------|----------------|
| `ACCT_NO` | STRING | Loan account number, primary key | `000042` |
| `BORROWER` | STRING | Legal entity name | `Metro Properties LLC` |
| `CURRENT_BAL` | DOUBLE | Outstanding funded balance (USD). Decreases daily with amortisation. | `3250000.0` |
| `COMMITTED_AMT` | DOUBLE | Total committed facility amount (USD). Funded + undrawn. | `4500000.0` |
| `INT_RATE` | DOUBLE | Current interest rate (decimal) | `0.072` (= 7.2%) |
| `RATE_TYPE` | STRING | Rate type | `fixed`, `floating` |
| `ORIG_DATE` | STRING | Original loan origination date | `2024-03-15` |
| `MATURITY_DATE` | STRING | Contractual maturity date | `2029-03-15` |
| `AMORT_TYPE` | STRING | Amortisation schedule type | `linear`, `bullet`, `interest_only`, `revolving`, `sculpted` |
| `PMT_FREQ` | STRING | Payment frequency | `Monthly`, `Single Payment at Maturity` |
| `RISK_RATING` | STRING | Internal risk rating letter | `AAA` through `D` |
| `RISK_RATING_NUM` | INT | Risk rating numeric (1-9) | `4` |
| `SEGMENT` | STRING | Lending segment | `cre`, `c_and_i`, `multifamily`, `construction`, `specialty` |
| `PRODUCT_TYPE` | STRING | Product sub-type / property type | `office`, `industrial`, `multifamily` |
| `STATE` | STRING | US state (15-state footprint) | `OH`, `PA`, `NY` |
| `ACCRUAL_STATUS` | STRING | Whether the loan is accruing interest | `TRUE`, `FALSE` |
| `COLLATERAL_TYPE` | STRING | Primary collateral description | `Real Estate 1st Mortgage`, `Equipment` |
| `PROPERTY_TYPE` | STRING | Property type for RE collateral | `Office`, `Retail`, `Industrial`, `Multifamily` |
| `OWNER_OCC` | BOOLEAN | True if borrower occupies the collateral | `true`, `false` |
| `SNC_FLAG` | BOOLEAN | Shared National Credit (participations >= $30M) | `true`, `false` |
| `TDR_FLAG` | BOOLEAN | Troubled Debt Restructuring (ASC 310-40) | `true`, `false` |
| `AS_OF_DATE` | STRING | Snapshot date (ISO format) | `2026-01-02` |

**Key relationships:**
- `ACCT_NO` is the primary key; track across `sim_day` to see balance, rating, and status changes
- At maturity, ~80% of loans generate a renewal in `los_underwriting` (APP_ID = `RNW-{ACCT_NO}-{date}`)
- Deposits linked via `CUSTOMER_ID` in `core_deposits` (mapped to borrower)

---

## core_deposits

**Source System:** Core Deposits
**Description:** Deposit accounts including checking, savings, CDs, and money market. Linked to loan borrowers via `CUSTOMER_ID`. New deposit accounts are captured when pipeline deals fund. Balances and rates evolve daily based on behavior models and benchmark rate sensitivity.

| Field | Type | Description | Example Values |
|-------|------|-------------|----------------|
| `ACCOUNT_ID` | STRING | Deposit account ID, primary key | `DEP-000042` |
| `CUSTOMER_ID` | STRING | Customer ID linking to funded loan borrowers | `003222` |
| `ACCOUNT_TYPE` | STRING | Deposit product type | `Checking`, `Commercial Checking`, `Operating`, `CD`, `Savings`, `Money Market` |
| `CURRENT_BAL` | DOUBLE | Current deposit balance (USD) | `2450000.0` |
| `INT_RATE` | DOUBLE | Interest rate paid (decimal) | `0.045` (= 4.5%) |
| `RATE_TYPE` | STRING | Rate type | `fixed`, `floating` |
| `DEPOSIT_BETA` | DOUBLE | Rate sensitivity (0.0-1.0). Movement per 100bps benchmark change. | `0.35` |
| `OPEN_DATE` | STRING | Account opening date | `2021-06-15` |
| `LIQUIDITY_CLASS` | STRING | Liquidity classification for regulatory purposes | `Stable`, `Operational`, `Non-Operational`, `Rate Sensitive` |
| `SEGMENT` | STRING | Customer segment aligned with lending | `cre`, `c_and_i`, `multifamily` |
| `AS_OF_DATE` | STRING | Snapshot date (ISO format) | `2026-01-02` |

**Key relationships:**
- `CUSTOMER_ID` maps to `ACCT_NO` in `core_funded` (same borrower, different systems)
- Use this join to compute relationship-level metrics (total exposure = loans + deposits)
- `LIQUIDITY_CLASS` is key for LCR/NSFR regulatory calculations

---

## Cross-Table Relationships

```
crm_pipeline.OPP_ID ──(advances to)──► los_underwriting.APP_ID
                                              │
                                              ▼ (funds)
                                       core_funded.ACCT_NO
                                              │
                                              ├──(maturity + renewal)──► los_underwriting.APP_ID (RNW-*)
                                              │
                                              └──(customer link)──► core_deposits.CUSTOMER_ID
```

## Useful Joins

```sql
-- Relationship-level exposure (loans + deposits per customer)
SELECT f.BORROWER, f.ACCT_NO,
       f.CURRENT_BAL as loan_balance,
       d.CURRENT_BAL as deposit_balance,
       f.CURRENT_BAL - COALESCE(d.CURRENT_BAL, 0) as net_exposure
FROM bdi_data_201.synthetic_bank.core_funded f
LEFT JOIN bdi_data_201.synthetic_bank.core_deposits d
  ON f.ACCT_NO = d.CUSTOMER_ID
WHERE f.sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.core_funded);

-- Track a renewal from funded loan to LOS and back
SELECT 'funded' as source, ACCT_NO as id, BORROWER as name, CURRENT_BAL as amount, sim_day
FROM bdi_data_201.synthetic_bank.core_funded
WHERE ACCT_NO = '000042'
UNION ALL
SELECT 'los' as source, APP_ID, BORROWER_NAME, REQUESTED_AMOUNT, sim_day
FROM bdi_data_201.synthetic_bank.los_underwriting
WHERE APP_ID LIKE 'RNW-000042%'
ORDER BY sim_day;
```
