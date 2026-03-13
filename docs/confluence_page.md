# Synthetic Bank: A Living Test Harness for BDI

**Owner:** Alexander Cannon | **Status:** Live | **Last Updated:** March 13, 2026
**Repo:** [arulana/portfolioevolution](https://github.com/arulana/portfolioevolution) | **Databricks:** `bdi_data_201.synthetic_bank`

---

## What Is This?

The Synthetic Bank is a fully operational, self-advancing simulation of a US superregional commercial bank (~$100B total assets). It models the complete lifecycle of commercial lending — from CRM pipeline origination through credit underwriting, balance sheet funding, amortisation, maturity, renewal, and prepayment — alongside a co-evolving deposit book.

It is **not a static dataset**. It is a living system that advances one business day per real day, generating realistic daily snapshots of four distinct source systems. Every day, the bank:

- Generates new pipeline deals (50/week, configurable)
- Progresses existing deals through a 6-stage pipeline (Lead → Term Sheet → Underwriting → Approved → Documentation → Closing)
- Funds approved deals onto the balance sheet
- Amortises funded loans daily
- Processes maturities and stochastic prepayments
- Renews ~80% of maturing loans back through underwriting
- Migrates credit ratings based on a 9x9 transition matrix
- Evolves deposit balances and reprices based on rate sensitivity
- Writes fresh snapshots to Databricks Delta tables

The data is shaped as if it comes from four separate source systems — exactly how a real bank would provide it.

---

## Why Does This Exist?

### Problem Statement

BDI's onboarding and automation pillars need to test end-to-end workflows before engaging with real clients. But:

1. **Real client data is restricted** — legal, compliance, and contractual barriers limit what we can use internally
2. **Static test data goes stale** — a CSV file doesn't evolve, doesn't have temporal dynamics, and doesn't test edge cases (maturities, renewals, rating migrations)
3. **Multi-system complexity is hard to simulate** — a real bank's data spans CRM, LOS, core banking, and deposits, each with different schemas, update cadences, and data quality characteristics
4. **Demo environments need realistic data** — Summit demos, POC presentations, and client workshops need data that looks and behaves like a real bank

### What This Solves

| Challenge | How the Synthetic Bank Addresses It |
|-----------|--------------------------------------|
| **Onboarding testing** | Four source-system tables mimic real bank data delivery; test CDD mapping, schema resolution, and data quality checks against realistic data |
| **Automation testing** | Daily-advancing data with pipeline transitions, fundings, maturities, and renewals exercises the full automation pipeline |
| **Demo data** | A complete, self-consistent bank with $75B funded, $10B pipeline, $77B deposits — no awkward "this is sample data" disclaimers |
| **Domain agent testing** | Every domain agent (Credit Analytics, RPA, Portfolio Studio) needs loan-level data; the synthetic bank provides it across all required dimensions |
| **Entity resolution** | Cross-system data with intentional overlaps (same borrower in CRM, LOS, core banking, and deposits) to test entity matching |
| **Genie/NL-to-SQL testing** | Real-shaped data in Databricks for testing text-to-SQL queries against meaningful financial structures |
| **AsOfDate consistency** | Built-in simulation calendar ensures consistent dates across all four systems — directly addresses open question A3 |

---

## What's In the Data?

### Bank Profile

| Metric | Value |
|--------|-------|
| **Total Assets** | ~$100B |
| **Funded Loans** | ~$75B across 20,000 positions |
| **Committed Facilities** | ~$100B |
| **Active Pipeline** | ~$10B across 1,500 deals |
| **Deposits** | ~$77B across 15,000 accounts |
| **Loan-to-Deposit Ratio** | ~1.0x (evolves with simulation) |
| **Segment Mix** | C&I (48%), CRE (28%), Multifamily (12%), Construction (7%), Specialty (5%) |
| **Geography** | 15-state superregional footprint: OH, PA, NY, MI, IN, IL, NJ, CT, MA, WI, MN, FL, NC, VA, TX |
| **Risk Rating Distribution** | ~70% Pass (1-4), ~20% Watch (5-6), ~10% Classified (7-9) |
| **Renewal Rate** | ~80% of maturing loans renew |
| **Pipeline Pull-Through** | ~18% lead-to-fund conversion |
| **New Deal Inflow** | 50 deals/week |

### Reference Banks

The synthetic bank is calibrated against publicly available data from peer superregional institutions: KeyBank, M&T Bank, Citizens Financial, Regions Financial, Huntington Bancshares, and Zions Bancorporation.

---

## Four Source System Tables

The data is separated into four tables representing distinct source systems. This separation is intentional — it mirrors how a real bank's data would be provided to BDI and forces our onboarding and automation workflows to handle cross-system data integration.

### 1. CRM Pipeline (`bdi_data_201.synthetic_bank.crm_pipeline`)

**Source System:** Customer Relationship Management
**Update Cadence:** Daily
**Typical Volume:** 500-800 rows per snapshot

Contains early-stage pipeline deals (Lead and Term Sheet stages) tracked by relationship managers. Deals advance to LOS when a term sheet is accepted.

| Key Fields | Description |
|------------|-------------|
| `OPP_ID` | Opportunity ID — unique deal identifier in the CRM |
| `BORROWER_NAME` | Prospective borrower legal entity name |
| `STAGE` | `Lead` or `Term Sheet` |
| `EXPECTED_AMOUNT` | Expected deal size (USD) |
| `CLOSE_PROB` | RM-estimated close probability (0.0 - 1.0) |
| `SEGMENT` | Lending segment: cre, c_and_i, multifamily, construction, specialty |
| `RM_NAME` / `RM_CODE` | Assigned relationship manager |
| `STATE` | US state |

**What to test with this data:**
- CRM-to-CDD schema mapping
- Pipeline reporting and funnel analytics
- RM portfolio analysis
- Geographic concentration monitoring

### 2. LOS Underwriting (`bdi_data_201.synthetic_bank.los_underwriting`)

**Source System:** Loan Origination System
**Update Cadence:** Daily
**Typical Volume:** 2,000-3,500 rows per snapshot

Contains deals in active credit underwriting through closing. Includes both new originations from CRM and **renewal submissions** — maturing funded loans that re-enter the underwriting process. This is a critical test case for automation.

| Key Fields | Description |
|------------|-------------|
| `APP_ID` | Application ID. Renewals prefixed with `RNW-`. |
| `UW_STAGE` | `underwriting`, `approved`, `documentation`, `closing` |
| `REQUESTED_AMOUNT` / `APPROVED_AMOUNT` | Requested vs. approved amounts |
| `RISK_RATING` / `RATING_NUMERIC` | Internal risk rating (letter and numeric 1-9) |
| `IS_RENEWAL` | Boolean flag — true if this is a renewal of a maturing funded loan |
| `RATE_TYPE` / `EXPECTED_RATE` | Rate type and expected coupon |
| `CONDITION_COUNT` | Conditions precedent to closing |

**What to test with this data:**
- LOS-to-CDD schema mapping
- Underwriting workflow automation
- Renewal tracking and matching to original funded loans
- Credit approval pipeline analytics
- Cross-system entity matching (same borrower appears in CRM and LOS with different IDs)

### 3. Core Banking Funded (`bdi_data_201.synthetic_bank.core_funded`)

**Source System:** Core Banking System
**Update Cadence:** Daily
**Typical Volume:** 16,000-20,000 rows per snapshot

The on-balance-sheet loan portfolio. This is the richest table — 24 columns covering balances, rates, ratings, collateral, regulatory flags, and accrual status. Balances change daily due to amortisation. Loans exit via maturity (most renew) or prepayment.

| Key Fields | Description |
|------------|-------------|
| `ACCT_NO` | Loan account number — primary key |
| `CURRENT_BAL` / `COMMITTED_AMT` | Outstanding funded balance and total committed amount |
| `INT_RATE` / `RATE_TYPE` | Current interest rate and type (fixed/floating) |
| `ORIG_DATE` / `MATURITY_DATE` | Origination and contractual maturity dates |
| `AMORT_TYPE` | `linear`, `bullet`, `interest_only`, `revolving`, `sculpted` |
| `RISK_RATING` / `RISK_RATING_NUM` | Internal risk rating |
| `SEGMENT` / `PRODUCT_TYPE` | Lending segment and product sub-type |
| `ACCRUAL_STATUS` | Whether the loan is accruing interest |
| `SNC_FLAG` / `TDR_FLAG` / `OWNER_OCC` | Regulatory flags |
| `COLLATERAL_TYPE` / `PROPERTY_TYPE` | Collateral details |

**What to test with this data:**
- Core banking-to-CDD schema mapping (this is the most complex mapping exercise)
- EDF-X automation pipeline (financial data → PD/LGD → RPA)
- RPA profitability calculations (NIM, ROE, RORAC on real-structured loan data)
- Portfolio Studio inputs (EC, concentration, risk/return)
- Credit Analytics agent queries
- Genie NL-to-SQL against a 20,000-row loan book
- Balance sheet aggregation and LDR/LCR analysis
- Watch list and classified asset monitoring

### 4. Core Deposits (`bdi_data_201.synthetic_bank.core_deposits`)

**Source System:** Core Deposits System
**Update Cadence:** Daily
**Typical Volume:** 15,000-16,000 rows per snapshot

Deposit accounts linked to loan borrowers via `CUSTOMER_ID`. Includes checking, savings, CDs, and money market accounts with rate sensitivity (deposit beta) and liquidity classification.

| Key Fields | Description |
|------------|-------------|
| `ACCOUNT_ID` | Deposit account ID |
| `CUSTOMER_ID` | Links to loan borrowers (maps to `ACCT_NO` in core_funded) |
| `ACCOUNT_TYPE` | Checking, Commercial Checking, Operating, CD, Savings, Money Market |
| `CURRENT_BAL` | Current deposit balance |
| `INT_RATE` / `RATE_TYPE` / `DEPOSIT_BETA` | Rate, type, and rate sensitivity |
| `LIQUIDITY_CLASS` | Stable, Operational, Non-Operational, Rate Sensitive |

**What to test with this data:**
- Deposit data onboarding
- Relationship-level analytics (join loans + deposits per customer)
- ALM/BSM inputs (when BSM agent arrives H2 2026)
- Liquidity analysis (LDR, LCR proxy, NSFR proxy)
- Deposit pricing and beta analysis
- Cross-system entity resolution (CUSTOMER_ID ↔ ACCT_NO)

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Simulation Engine                         │
│                                                               │
│  Pipeline Generator ──► Pipeline Engine ──► Funded Engine     │
│       (50/week)        (6-stage transitions)  (amort/mature)  │
│                              │                      │         │
│                     CRM → LOS handoff      Renewal → LOS     │
│                                                               │
│  Deposit Engine ◄── Deposit Capture (at funding)              │
│  Rating Engine ── 9x9 transition matrix                       │
│                                                               │
│  Config-First: All rules in YAML (no hardcoded parameters)    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              System View Formatters                           │
│                                                               │
│  format_crm_view()  format_los_view()  format_core_view()    │
│                     format_deposits_view()                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│           Databricks Delta Tables                            │
│                                                               │
│  bdi_data_201.synthetic_bank.crm_pipeline                    │
│  bdi_data_201.synthetic_bank.los_underwriting                │
│  bdi_data_201.synthetic_bank.core_funded                     │
│  bdi_data_201.synthetic_bank.core_deposits                   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: Lifecycle of a Loan

```
1. PIPELINE INFLOW
   New deal generated → enters CRM as "Lead"
   Fields: borrower, segment, expected amount, RM, state

2. CRM PROGRESSION (crm_pipeline table)
   Lead ──► Term Sheet (daily probability: 2.5%)
   Term Sheet ──► LOS Handoff (daily probability: 4.0%)
   Deals can also drop at any stage (competitive loss, borrower walks)
   Age decay: stale leads become less likely to advance

3. LOS HANDOFF (los_underwriting table)
   When term sheet is accepted, deal transitions from CRM to LOS
   position_type changes from "pipeline_crm" to "pipeline_los"
   Enters underwriting stage with full credit data

4. LOS PROGRESSION
   Underwriting ──► Approved ──► Documentation ──► Closing ──► Funded
   Each stage has its own transition probability and fallout rate
   Segment and rating modifiers (C&I moves faster, weak credits fall out more)
   Later stages accelerate (pressure to close)

5. FUNDING (core_funded table)
   Deal closes → enters core banking as a funded loan
   Committed amount, funded amount, rate, collateral, risk rating
   Deposit captured (new account in core_deposits linked to borrower)

6. FUNDED EVOLUTION
   Daily amortisation based on amort type (linear, bullet, I/O, revolving)
   Credit rating migration (monthly, 9x9 matrix)
   Stochastic prepayment (segment-specific CPR, 90-day minimum age)

7. MATURITY
   At contractual maturity:
   - 80% probability → RENEWAL: new deal enters LOS as "underwriting"
     (APP_ID = "RNW-{original_ACCT_NO}-{date}", IS_RENEWAL = true)
   - 20% probability → RUNOFF: loan exits the portfolio

8. RENEWAL CYCLE
   Renewal progresses through LOS stages (same as new origination)
   If approved and funded → re-enters core_funded as a new loan
   Creates a full audit trail across all four systems
```

### Configuration (YAML-Driven)

Every business rule is configurable via YAML — no hardcoded parameters:

| Config File | Controls |
|-------------|----------|
| `master_config.yaml` | Simulation horizon, seed, feature flags, segment weights, inflow volume |
| `pipeline_transitions.yaml` | Stage-by-stage transition probabilities, age factors, segment/rating modifiers, expiry limits |
| `funded_behaviour.yaml` | Renewal rates (base + segment + rating overrides), prepayment rates, amortisation rules |
| `rating_migration.yaml` | 9x9 transition matrix, watchlist triggers |
| `deposit_behaviour.yaml` | Deposit evolution, pricing, liquidity classification |

This means the bank can be recalibrated to match any client profile (community bank, regional, superregional, national) by adjusting config values.

### Autonomous Execution

The simulation runs as a **Databricks scheduled job** (`daily_advance` notebook):

1. **06:00 ET daily** — job triggers on the Serverless Warehouse
2. Reads the latest snapshot from the four Delta tables
3. Reconstructs positions and advances one business day
4. Writes new snapshot with incremented `sim_day`
5. Job completes, warehouse scales down

No local machines, no manual intervention. The bank grows organically.

---

## How to Access the Data

### Databricks SQL

```sql
-- Quick check: what's in the bank today?
SELECT
  (SELECT COUNT(*) FROM bdi_data_201.synthetic_bank.core_funded
   WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.core_funded)) as funded_loans,
  (SELECT COUNT(*) FROM bdi_data_201.synthetic_bank.los_underwriting
   WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.los_underwriting)) as los_deals,
  (SELECT COUNT(*) FROM bdi_data_201.synthetic_bank.crm_pipeline
   WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.crm_pipeline)) as crm_deals,
  (SELECT COUNT(*) FROM bdi_data_201.synthetic_bank.core_deposits
   WHERE sim_day = (SELECT MAX(sim_day) FROM bdi_data_201.synthetic_bank.core_deposits)) as deposit_accounts;
```

### Starter Queries

Six pre-built queries are available in the repo under `queries/`:

1. **Funded Book Summary** — Portfolio composition by segment with classified/TDR breakouts
2. **Pipeline Funnel** — Combined CRM + LOS funnel with deal counts and amounts per stage
3. **Renewal Tracker** — All renewal submissions currently in underwriting
4. **Deposit Concentration** — Balances by account type and liquidity class
5. **Geographic Exposure** — State-level concentration heatmap
6. **Loan-to-Deposit Ratio** — Balance sheet summary with LDR

### Connecting Domain Agents

| Agent | Relevant Tables | Use Case |
|-------|----------------|----------|
| **Credit Analytics (EDF-X)** | `core_funded` | Run EDF-X on the 20K-loan portfolio to generate PDs, LGDs, implied ratings |
| **RPA** | `core_funded` + `crm_pipeline` + `los_underwriting` | Profitability analysis: NIM, ROE, RORAC on funded book; pipeline weighted profitability |
| **Portfolio Studio** | `core_funded` | Portfolio analytics: EC, concentration, risk/return optimization |
| **Impairment Studio** | `core_funded` | CECL/IFRS-9 ECL calculations on a realistic portfolio |
| **BSM (H2 2026)** | `core_funded` + `core_deposits` | ALM analysis: duration gap, NII sensitivity, liquidity |
| **Genie** | All four tables | NL-to-SQL testing: "Show me all CRE loans in Ohio over $5M with ratings below 5" |

### Full Data Dictionary

A complete field-by-field reference with types, descriptions, example values, and cross-table relationships is available at `docs/data_dictionary.md` in the repo.

---

## Reusability: Beyond the Synthetic Bank

### POC and Demo Data Generation

The synthetic data generation engine (`scripts/generate_synthetic_data.py`) is designed for reuse. It can generate:

- **Any bank profile** — community bank ($1-10B), regional ($10-50B), superregional ($50-200B), national ($200B+) by adjusting config parameters
- **Any segment mix** — CRE-heavy, C&I-heavy, consumer, specialty lending
- **Any geography** — single-state, multi-state, national
- **Any vintage distribution** — concentrated maturity walls, evenly distributed, seasoned vs. recent
- **Custom risk profiles** — pristine (all pass-rated), stressed (high classified), or realistic distribution

This means when a POC or demo needs bank-specific data (e.g., "generate a $15B community bank with heavy CRE concentration in the Southeast"), we can produce it in minutes.

### Data Model Spanning

The synthetic bank already generates data that spans the key dimensions needed across BDI data models:

| Dimension | Coverage |
|-----------|----------|
| **Instrument/Loan** | 47-column loan record (core_funded) — covers CDD instrument fields |
| **Entity/Obligor** | Borrower names, IDs, cross-system links — covers CDD entity fields |
| **Pipeline/Opportunity** | Full 6-stage pipeline with probabilities and dates |
| **Collateral** | Type, code, property type, owner-occupied flag |
| **Rating** | 9-level internal scale with letter and numeric, migration history |
| **Financial** | Committed, funded, undrawn, rates, amort type, payment frequency |
| **Regulatory** | SNC, TDR, accrual status, risk rating groups |
| **Deposit** | Account type, balance, rate, beta, liquidity class, customer link |
| **Geography** | 15-state footprint, branch codes |
| **Industry** | NAICS codes, report groups |

---

## Technical Details

### Tech Stack

| Component | Technology |
|-----------|------------|
| **Simulation Engine** | Python (Polars, Pydantic, NumPy) |
| **Data Validation** | Pydantic strict models |
| **Configuration** | YAML (all business rules) |
| **Local Storage** | DuckDB (JDBC/ODBC queryable) |
| **Cloud Storage** | Databricks Delta tables (Unity Catalog) |
| **Scheduling** | Databricks Jobs (serverless) |
| **API** | FastAPI (REST, optional) |
| **Testing** | pytest (115+ tests), Hypothesis (property-based) |
| **Repository** | GitHub ([arulana/portfolioevolution](https://github.com/arulana/portfolioevolution)) |

### Key Performance Metrics

| Metric | Value |
|--------|-------|
| Simulation speed | ~1.2 seconds per day (20K+ positions) |
| Peak memory | ~0.4 GB |
| Full-year run (local) | ~7.5 minutes |
| Daily Databricks push | ~3 minutes |
| Databricks rows per day | ~35,000 across 4 tables |
| Test coverage | 115+ tests (unit, integration, property, acceptance) |

### Repository Structure

```
portfolioevolution/
├── config/                        # YAML business rules (pipeline, funded, deposits, ratings)
├── data/sample/                   # Generated CSV files (20K funded, 1.5K pipeline, 15K deposits)
├── docs/data_dictionary.md        # Full field-by-field reference
├── notebooks/daily_advance.py     # Databricks scheduled notebook
├── queries/                       # 6 starter SQL queries
├── schemas/                       # Schema definitions, mappings, lookups
├── scripts/                       # Data generation, setup, smoke tests
├── src/portfolio_evolution/       # Core engine code
│   ├── engines/                   # Simulation engines (pipeline, funded, deposit, rating, calendar)
│   ├── models/                    # Pydantic data models
│   ├── output/                    # System views, DuckDB store, Databricks sync
│   ├── api/                       # FastAPI + autonomous scheduler
│   └── ...
└── tests/                         # 115+ tests
```

---

## What's Next

| Item | Priority | Description |
|------|----------|-------------|
| **Run first scheduled job** | Now | Trigger the `daily_advance` notebook manually to verify it works end-to-end in Databricks |
| **Create Genie space** | High | Set up a Genie space over `bdi_data_201.synthetic_bank.*` to test NL-to-SQL queries |
| **Onboarding dry run** | High | Use the synthetic bank as a non-hosted client: run the CDD mapping workflow against the four tables |
| **EDF-X automation test** | High | Feed `core_funded` data through the EDF-X → RPA pipeline to test end-to-end automation |
| **Entity resolution test** | Medium | Test cross-system entity matching using the deliberate overlaps between CRM, LOS, core banking, and deposits |
| **Community bank variant** | Medium | Generate a second bank profile ($5B community bank) to test BDI against a different client size |
| **Summit demo data** | Medium | Generate a curated dataset for the three Summit demo scenarios (Deal Context, Production Optimizer, Portfolio Scanner) |
| **Scenario stress testing** | Low | Enable macro scenarios (recession, rate shock) to test how the portfolio evolves under stress |

---

## Questions? Comments?

This page is the team's reference point for the Synthetic Bank. Please:

- **Comment below** with questions, requests, or issues
- **Tag @alexander.cannon** for changes to the simulation or data
- **Check `bdi_data_201.synthetic_bank`** in Databricks to explore the live data

The data is there. The bank is breathing. Let's use it.
