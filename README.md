# Portfolio Evolution Engine

A synthetic US superregional bank simulation (~$100B assets) that models the full lifecycle of commercial loans — from CRM pipeline through LOS underwriting, core banking funding, amortisation, maturity, renewal, and prepayment — alongside deposit co-evolution and credit rating migration.

Built as a high-fidelity test harness for the BDI (Banking Decision Intelligence) team to validate onboarding and automation workflows before engaging with real clients.

## Databricks (Primary Access)

The synthetic bank data lives in Databricks Unity Catalog. The four tables represent distinct source systems — exactly as a real bank would provide them.

**Location:** `bdi_data_201.synthetic_bank`

| Table | Source System | Description | ~Rows/Day |
|-------|--------------|-------------|-----------|
| `crm_pipeline` | CRM | Early-stage deals (Lead, Term Sheet) | 500-800 |
| `los_underwriting` | Loan Origination | Deals in underwriting through closing, incl. renewals | 2,000-3,500 |
| `core_funded` | Core Banking | On-balance-sheet funded loans with balances and ratings | 16,000-20,000 |
| `core_deposits` | Core Deposits | Deposit accounts linked to borrowers | 15,000-16,000 |

### Sample Queries

```sql
-- Funded book summary by segment
SELECT SEGMENT, COUNT(*) as loans, SUM(CURRENT_BAL) as total_bal,
       AVG(INT_RATE) as avg_rate, AVG(RISK_RATING_NUM) as avg_rating
FROM bdi_data_201.synthetic_bank.core_funded
GROUP BY SEGMENT ORDER BY total_bal DESC;

-- Pipeline funnel
SELECT STAGE, COUNT(*) as deals, SUM(EXPECTED_AMOUNT) as total_amount,
       AVG(CLOSE_PROB) as avg_prob
FROM bdi_data_201.synthetic_bank.crm_pipeline
GROUP BY STAGE;

-- Renewals currently in underwriting
SELECT APP_ID, BORROWER_NAME, REQUESTED_AMOUNT, UW_STAGE, RISK_RATING
FROM bdi_data_201.synthetic_bank.los_underwriting
WHERE IS_RENEWAL = true;

-- Deposit concentration by type
SELECT ACCOUNT_TYPE, COUNT(*) as accounts, SUM(CURRENT_BAL) as total_bal,
       AVG(INT_RATE) as avg_rate
FROM bdi_data_201.synthetic_bank.core_deposits
GROUP BY ACCOUNT_TYPE ORDER BY total_bal DESC;

-- Loan-to-deposit ratio
SELECT
  (SELECT SUM(CURRENT_BAL) FROM bdi_data_201.synthetic_bank.core_funded) as total_loans,
  (SELECT SUM(CURRENT_BAL) FROM bdi_data_201.synthetic_bank.core_deposits) as total_deposits,
  (SELECT SUM(CURRENT_BAL) FROM bdi_data_201.synthetic_bank.core_funded) /
  NULLIF((SELECT SUM(CURRENT_BAL) FROM bdi_data_201.synthetic_bank.core_deposits), 0) as ldr;
```

### Daily Advance

The simulation advances one business day per real day. Each day:
1. New pipeline deals enter the CRM (50/week configurable)
2. Deals progress through stages (CRM → LOS → Core Banking)
3. Funded loans amortise, mature, prepay, or renew
4. Deposits evolve (balances, rates, new captures at funding)
5. A fresh snapshot is pushed to Databricks

Each snapshot is keyed by `(run_id, sim_day)`. Query across `sim_day` values to see how positions change over time.

## Quick Start (Local Development)

```bash
# Install
pip install -e .

# Install with Databricks support
pip install -e ".[databricks]"

# Generate synthetic data (20K funded, 1.5K pipeline, 15K deposits)
python scripts/generate_synthetic_data.py

# Validate data
python -m portfolio_evolution.main validate

# Run a 30-day simulation
python -m portfolio_evolution.main run --preset quick --horizon 30

# Push day-0 snapshot to Databricks (requires env vars)
python scripts/push_day0_databricks.py
```

### Environment Variables (for Databricks)

```bash
export DATABRICKS_HOST=banking-ci-data.cloud.databricks.com
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/0e815dadc27740bc
export DATABRICKS_TOKEN=<your-personal-access-token>
```

## Docker (Recommended for Production)

```bash
# Start the full stack (API + scheduler + DuckDB)
docker compose up --build -d

# Check health
curl http://localhost:8000/health

# Trigger a simulation
curl -X POST "http://localhost:8000/simulate?horizon=30&preset=quick"

# Query by source system
curl http://localhost:8000/runs/{run_id}/system/crm
curl http://localhost:8000/runs/{run_id}/system/los
curl http://localhost:8000/runs/{run_id}/system/core
curl http://localhost:8000/runs/{run_id}/system/deposits

# Check scheduler status
curl http://localhost:8000/scheduler/status
```

### Connection Options

| Method | Endpoint | Use Case |
|--------|----------|----------|
| Databricks SQL | `bdi_data_201.synthetic_bank.*` | Shared team access, dashboards, notebooks |
| REST API | `http://localhost:8000` | Application integration, automation |
| SQL (JDBC/ODBC) | `outputs/simulation.duckdb` | Local SQL queries via DuckDB |
| File Drop | `./outputs/` | CSV/Parquet file consumption |

## Architecture

```
portfolio-evolution/
├── config/                    # YAML-driven simulation parameters
│   ├── master_config.yaml     # Central config (calibrated for superregional bank)
│   ├── pipeline_transitions.yaml  # 6-stage pipeline with segment/rating modifiers
│   ├── funded_behaviour.yaml      # Renewal (80%), prepayment, amortisation rules
│   ├── deposit_behaviour.yaml
│   ├── rating_migration.yaml
│   ├── scenarios/             # Macro scenarios (baseline, recession, stress)
│   └── presets/               # Run presets (quick, standard, full)
├── schemas/                   # YAML schema definitions and mappings
├── data/sample/               # Synthetic data (20K funded, 1.5K pipeline, 15K deposits)
├── src/portfolio_evolution/
│   ├── engines/               # Core simulation engines
│   │   ├── simulation_runner.py   # Daily orchestrator
│   │   ├── pipeline_engine.py     # Pipeline stage transitions + CRM→LOS handoff
│   │   ├── funded_engine.py       # Amortisation, maturity, renewal, prepayment
│   │   ├── rating_engine.py       # Credit rating migration
│   │   ├── deposit_engine.py      # Deposit balance evolution
│   │   ├── pipeline_generator.py  # Synthetic deal inflow
│   │   └── calendar.py            # Business day calendar
│   ├── models/                # Pydantic data models
│   ├── output/
│   │   ├── system_views.py        # CRM, LOS, Core, Deposits view formatters
│   │   ├── duckdb_store.py        # Local DuckDB persistence
│   │   └── databricks_sync.py     # Databricks Delta table sync
│   ├── api/                   # FastAPI REST API + autonomous scheduler
│   └── main.py                # CLI entry point
├── scripts/
│   ├── generate_synthetic_data.py  # Data generation (superregional profile)
│   ├── setup_databricks.py         # One-time Databricks table creation
│   └── push_day0_databricks.py     # Initial snapshot push
├── docs/
│   └── data_dictionary.md          # Full field-by-field reference
├── queries/                         # Starter SQL queries
├── tests/                           # 115+ tests (unit, integration, property, acceptance)
├── Dockerfile
└── docker-compose.yaml
```

## System Separation

The simulation models four distinct source systems, mirroring how a real bank organizes its data:

```
Pipeline Deals ──► CRM (Lead, Term Sheet)
                      │
                      ▼ Term sheet accepted
                   LOS (Underwriting → Approved → Documentation → Closing)
                      │
                      ▼ Deal funds
                   Core Banking (funded loans, amortisation, ratings)
                      │
                      ├──► Maturity → 80% renew back to LOS
                      └──► Prepayment → runoff

Deposits ──────► Core Deposits (balances, rates, liquidity)
                      ▲
                      │ Captured at funding
```

## Bank Profile (Superregional)

| Metric | Value |
|--------|-------|
| Total Assets | ~$100B |
| Funded Loans | ~$75B (20,000 positions) |
| Committed | ~$100B |
| Pipeline | ~$10B (1,500 deals) |
| Deposits | ~$77B (15,000 accounts) |
| Segments | C&I (48%), CRE (28%), Multifamily (12%), Construction (7%), Specialty (5%) |
| Geography | 15-state footprint (OH, PA, NY, MI, IN, IL, NJ, CT, MA, WI, MN, FL, NC, VA, TX) |
| Pipeline Pull-Through | ~18% lead-to-fund |
| Renewal Rate | ~80% at maturity |
| New Inflow | 50 deals/week |

## Autonomous Mode

The engine runs autonomously — one business day per real day. Enable in `config/master_config.yaml`:

```yaml
scheduler:
  enabled: true
  mode: realtime
  cadence: daily
  run_time: "06:00"
  catch_up_on_start: true

databricks:
  enabled: true
```

The scheduler:
- Picks up where the last run left off (state persistence)
- Generates new pipeline deals automatically
- Pushes daily snapshots to Databricks
- Catches up missed days on restart

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Unit + property tests (fast)
python -m pytest tests/unit/ tests/property/ -v

# Smoke test at superregional scale
python scripts/smoke_test_superregional.py
```
