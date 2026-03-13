# Portfolio Evolution Engine

A synthetic bank simulation engine that models the full lifecycle of commercial loans — from pipeline origination through funding, amortisation, maturity, and runoff — alongside deposit co-evolution, credit rating migration, and balance sheet aggregation.

Built as a high-fidelity test harness for the BDI (Banking Decision Intelligence) team to validate onboarding and automation workflows before engaging with real clients.

## Quick Start

```bash
# Install
pip install -e .

# Validate data
python -m portfolio_evolution.main validate

# Run a 30-day simulation
python -m portfolio_evolution.main run --preset quick --horizon 30

# Infer schema from new data
python -m portfolio_evolution.main infer-schema --source data/new_bank_data.csv
```

## Docker (Recommended for BDI Team)

```bash
# Start the full stack (API + scheduler + DuckDB)
docker compose up --build -d

# Check health
curl http://localhost:8000/health

# Trigger a simulation
curl -X POST "http://localhost:8000/simulate?horizon=30&preset=quick"

# Query results
curl http://localhost:8000/runs
curl http://localhost:8000/runs/{run_id}/positions
curl http://localhost:8000/runs/{run_id}/aggregates

# Check scheduler status
curl http://localhost:8000/scheduler/status
```

### BDI Team Connection Options

| Method | Endpoint | Use Case |
|--------|----------|----------|
| REST API | `http://localhost:8000` | Application integration, dashboards |
| SQL (JDBC/ODBC) | `outputs/simulation.duckdb` | Direct SQL queries via DuckDB drivers |
| File Drop | `./outputs/` volume mount | CSV/Parquet file consumption |

## Architecture

```
portfolio-evolution/
├── config/                    # YAML-driven simulation parameters
│   ├── master_config.yaml     # Central config
│   ├── pipeline_transitions.yaml
│   ├── funded_behaviour.yaml
│   ├── deposit_behaviour.yaml
│   ├── rating_migration.yaml
│   ├── archetypes/            # Lender archetypes
│   ├── scenarios/             # Macro scenarios (baseline, recession, stress)
│   └── presets/               # Run presets (quick, standard, full)
├── schemas/                   # YAML schema definitions and mappings
├── data/sample/               # Synthetic portfolio data
├── src/portfolio_evolution/
│   ├── engines/               # Core simulation engines
│   │   ├── simulation_runner.py   # Daily orchestrator
│   │   ├── pipeline_engine.py     # Pipeline stage transitions
│   │   ├── funded_engine.py       # Amortisation and maturity
│   │   ├── rating_engine.py       # Credit rating migration
│   │   ├── deposit_engine.py      # Deposit balance evolution
│   │   ├── deposit_capture.py     # Deposit capture at funding
│   │   ├── pipeline_generator.py  # Synthetic deal inflow
│   │   └── calendar.py            # Business day calendar
│   ├── models/                # Pydantic data models
│   ├── ingestion/             # Data loading and validation
│   ├── aggregation/           # Roll-forward, balance sheet, liquidity
│   ├── scenarios/             # Scenario overlay engine
│   ├── strategy/              # Strategy interpreter
│   ├── explainability/        # Event logging and audit trail
│   ├── output/                # Formatter, DuckDB store, manifest
│   ├── state/                 # State persistence for autonomous mode
│   ├── api/                   # FastAPI REST API + scheduler
│   └── main.py                # CLI entry point
├── tests/                     # 95+ tests (unit, integration, property, acceptance)
├── Dockerfile
└── docker-compose.yaml
```

## Autonomous Mode

The engine can run autonomously — simulating one business day per real day (or faster in accelerated mode). Enable in `config/master_config.yaml`:

```yaml
scheduler:
  enabled: true
  mode: realtime        # or "accelerated"
  cadence: daily
  run_time: "06:00"
  accelerated_ratio: 5  # for accelerated mode
  catch_up_on_start: true
```

The scheduler:
- Picks up where the last run left off (state persistence)
- Generates new pipeline deals automatically (configurable inflow)
- Catches up missed days on container restart
- Writes all results to DuckDB for API/SQL access

## Key Features

- **Config-first**: All business rules live in YAML. No hardcoded parameters.
- **Full lifecycle**: Pipeline → Underwriting → Funding → Amortisation → Maturity
- **Deposit co-evolution**: Deposits captured at funding, decayed by behavior, repriced by beta model
- **Credit rating migration**: 9x9 transition matrix with watchlist and scenario stress
- **Scenario overlays**: Baseline, mild recession, severe stress
- **Deterministic**: Reproducible with seed. Golden file regression tests.
- **Explainability**: Every state change logged with reason codes and random draws
- **Balance sheet**: Combined assets + liabilities with LDR, LCR proxy, NIM proxy

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=portfolio_evolution

# Property-based tests only
python -m pytest tests/property/ -v

# Acceptance tests only
python -m pytest tests/acceptance/ -v
```
