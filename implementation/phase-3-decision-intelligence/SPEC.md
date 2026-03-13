# Phase 3: Decision Intelligence & Productization

**Duration**: Weeks 10–14 (3 sprints)

**Goal**: Valuation and economic measures, text-to-strategy translation from earnings
calls, sensitivity analysis, variance decomposition, intelligence object generation,
and full explainability reporting.

**Prerequisite**: Phase 2 complete — stochastic engine, rating migration, strategy/scenario
overlays, performance benchmarked.

---

## 1. What This Phase Delivers

By the end of Phase 3, a user can:

1. Track carrying value, market value proxies, yield, and spread income through simulation
2. Paste earnings call text and get auto-generated strategy signals
3. Run sensitivity analysis to understand which parameters move outcomes most
4. Get variance decomposition: how much of portfolio change comes from origination vs
   amortisation vs prepayment vs utilisation vs migration
5. Receive structured intelligence objects (insights) from simulation results
6. Review full explainability reports with per-position change attribution
7. Explore results through 3 complete Jupyter notebooks

---

## 2. Sprint 6 (Weeks 10–11): Valuation & Sensitivity

### 2.1 Valuation Engine (Simple)

`src/portfolio_evolution/engines/valuation_engine.py`

Track economic measures for each funded position daily:

- **Carrying value**: funded_amount adjusted for amortisation and impairment
- **Funded balance**: current outstanding
- **Accrued interest proxy**: `funded_amount × coupon_rate / 360 × days_since_last_payment`
- **Market value proxy**: carrying_value adjusted for spread movement
  `MV = CV × (1 - spread_duration × Δspread_bps / 10000)`
- **Expected yield**: `coupon_rate` or `benchmark_rate + spread_bps`
- **Undrawn fee income proxy**: `undrawn_amount × fee_rate / 360`

Config in `config/funded_behaviour.yaml`:

```yaml
valuation:
  enabled: true
  fair_value_mode: simple  # simple | dcf | full
  spread_duration_default: 3.0
  fee_rate_default_bps: 25
  day_count: 360
```

### 2.2 Yield & Spread Tracking

Aggregate across portfolio:

- Portfolio weighted average yield
- Portfolio weighted average spread
- NIM proxy (yield - funding cost assumption)
- Undrawn fee income pool
- Spread income contribution by segment

Track through simulation horizon and report as time series.

### 2.3 Variance Decomposition

`src/portfolio_evolution/aggregation/variance_decomp.py`

Decompose portfolio balance change into additive drivers:

```
ΔBalance = + new originations (pipeline → funded)
           - scheduled amortisation
           - maturity runoff
           + renewals
           - prepayments
           + utilisation increase
           - utilisation decrease
           + rating upgrades (if valuation-linked)
           - rating downgrades
           - defaults / charge-offs
           + scenario effect (vs baseline)
           + strategy effect (vs no-strategy)
```

Output as waterfall chart data: start balance → each driver → end balance.

Available per-scenario and as scenario-vs-scenario delta attribution.

### 2.4 Sensitivity Analysis

`src/portfolio_evolution/aggregation/sensitivity.py`

Methodology:

1. Define parameter grid: for each key parameter, test +/- range while holding others constant
2. Run simulation for each parameter perturbation
3. Measure impact on key output metrics (funded balance, rating mix, default rate, yield)
4. Rank parameters by impact magnitude

Key parameters to test:

- Pipeline transition probabilities (approval rate, fallout rate)
- Prepayment multiplier
- Renewal probability
- Utilisation target
- Rating migration multipliers (downgrade, upgrade)
- Scenario intensity (spread shift, growth factor)
- Strategy magnitude

Output: tornado chart data showing which parameters move outcomes most:

```
=== Sensitivity: End Funded Balance ===

Parameter                        -10%          +10%         Impact
Pipeline approval rate           -$180M        +$195M       High
Prepayment multiplier            +$120M        -$130M       High
Renewal probability              -$85M         +$90M        Medium
Utilisation target               -$60M         +$55M        Medium
Downgrade multiplier             +$30M         -$35M        Low
Spread shift                     +$10M         -$12M        Low
```

### 2.5 Contribution Analysis

Break down total portfolio change by:

- Segment contribution (C&I contributed +$200M, CRE contributed -$150M)
- Rating band contribution
- Product type contribution
- Geography contribution
- Any custom passthrough dimension

Report as: absolute contribution + percentage of total change.

---

## 3. Sprint 7 (Weeks 12–13): Text-to-Strategy & Explainability

### 3.1 Text-to-Strategy Parser

`src/portfolio_evolution/strategy/text_parser.py`

LLM-based translation of qualitative strategy text into structured StrategySignal objects.

Input: free-text from earnings calls, investor presentations, policy notes.

Process:

1. Feed text to LLM with structured prompt
2. LLM extracts strategy signals: dimension, direction, magnitude, target
3. Map signals to StrategySignal objects
4. Apply confidence scoring based on specificity of language
5. Present signals to user for review before applying to simulation

Example:

```
Input text:
"We are focused on growing our commercial and industrial lending in the
middle market segment while remaining more selective in office CRE exposure.
We expect to tighten credit standards for speculative-grade borrowers."

Extracted signals:
  1. segment=C&I_middle_market, direction=increase, magnitude=0.7, confidence=0.85
     → pipeline_inflow_multiplier: 1.20, approval_multiplier: 1.10
  2. segment=CRE_office, direction=tighten, magnitude=0.6, confidence=0.80
     → new_pipeline_multiplier: 0.70, approval_multiplier: 0.75
  3. dimension=rating_band, target=sub_IG, direction=tighten, magnitude=0.5, confidence=0.75
     → subinvestment_grade_approval_multiplier: 0.85
```

Design for LLM-agnostic backend (OpenAI, Azure OpenAI, local model).

### 3.2 Intelligence Object Generator

`src/portfolio_evolution/explainability/intelligence.py`

Produce structured insights from simulation results. Each simulation run generates
a set of IntelligenceObjects:

```python
class IntelligenceObject(BaseModel):
    insight_id: str
    type: Literal["risk_alert", "opportunity", "portfolio_shift",
                   "concentration_warning", "target_deviation", "driver_insight"]
    title: str
    description: str
    driver: str
    confidence: float  # 0 to 1
    severity: Literal["info", "warning", "critical"]
    recommended_action: str | None = None
    supporting_data: dict
```

Example intelligence objects:

```yaml
- type: portfolio_shift
  title: "CRE exposure declining faster than target"
  description: "CRE funded balance dropped 12% (target: -5%) driven by
    accelerated runoff and tightened pipeline conversion"
  driver: "runoff + strategy tightening"
  confidence: 0.82
  severity: warning
  recommended_action: "Review CRE pipeline to confirm intentional reduction
    vs unintended fallout increase"
  supporting_data:
    cre_start_balance: 1200000000
    cre_end_balance: 1056000000
    target_end_balance: 1140000000

- type: risk_alert
  title: "Concentration risk increasing in leveraged lending"
  description: "Leveraged loan share rose from 18% to 24% of funded portfolio
    under baseline scenario"
  driver: "higher pipeline conversion + lower runoff in segment"
  confidence: 0.78
  severity: warning

- type: target_deviation
  title: "Growth target unlikely to be met under stress"
  description: "Funded balance growth of 2.1% falls short of 5% target under
    mild recession (p75 = 3.8%)"
  driver: "pipeline conversion slowdown + increased prepayments"
  confidence: 0.74
  recommended_action: "Increase pipeline in sponsor finance or loosen
    approval thresholds for investment-grade borrowers"
```

Detection rules (configurable):

- Concentration thresholds
- Target deviation thresholds
- Rating mix drift thresholds
- Utilisation spike detection
- Scenario divergence flags

### 3.3 Explainability Reports

`src/portfolio_evolution/explainability/reports.py`

Generate formatted reports from explainability logs:

**Position-level change attribution**:

For each position (or top-N movers), show:

```
Instrument: LOAN-00123 (Acme Corp, C&I Term Loan)
Day 0:  BBB, $10M funded, 100% utilised
Day 90: BB+, $8.2M funded, 100% utilised

Changes:
  Day 12: Amortisation -$200K (scheduled linear)
  Day 34: Rating BBB → BBB- (score drift, scenario: mild recession)
  Day 45: Partial repayment -$400K (stochastic event, draw=0.031)
  Day 67: Rating BBB- → BB+ (downgrade, scenario multiplier=1.30)
  Day 78: Amortisation -$200K (scheduled)
  Day 90: Amortisation -$200K (scheduled), remaining balance $8.2M
```

**Aggregate audit trail**:

Summary of all transitions by type, with counts and average modifiers applied.

### 3.4 Scenario Comparison Notebook

`notebooks/02_scenario_comparison.ipynb`

- Load results from multi-scenario run
- Fan charts: funded balance evolution with percentile bands per scenario
- Waterfall: variance decomposition (baseline → stressed)
- Tornado: sensitivity analysis
- Rating migration heatmap
- Intelligence objects summary

### 3.5 Explainability Notebook

`notebooks/03_explainability.ipynb`

- Load explainability logs
- Position-level drill-down
- Rule frequency analysis (which rules fired most)
- Modifier distribution (how much did scenarios vs strategy shift outcomes)
- Audit trail for selected positions

---

## 4. Sprint 8 (Week 14): Polish & Documentation

### 4.1 Reporting API

`src/portfolio_evolution/output/reporting.py`

Expose structured output for downstream consumers:

- `get_portfolio_summary(run_id, scenario)` → dict
- `get_time_series(run_id, scenario, metric)` → DataFrame
- `get_position_history(run_id, instrument_id)` → DataFrame
- `get_intelligence_objects(run_id)` → list[IntelligenceObject]
- `get_variance_decomposition(run_id, scenario)` → dict
- `compare_scenarios(run_id, scenarios)` → DataFrame

### 4.2 Schema Mapping Documentation

Write onboarding guide:

- Step-by-step: new client data → schema inference → mapping review → validation → first run
- Common mapping patterns (rating crosswalks, date formats, amount scaling)
- Troubleshooting guide for common errors
- Example: onboarding 3 different bank formats

### 4.3 Advanced Valuation (Optional)

If time permits:

- DCF under scenario yield curves
- Spread widening/narrowing effect on fair value with configurable duration
- Expected credit loss (ECL) proxy: EAD × PD × LGD
- Liquidity premium / funding cost overlay

### 4.4 End-to-End Notebooks

Three complete notebooks:

1. **Quickstart** — load data, run quick simulation, basic charts
2. **Scenario Comparison** — 3-scenario run, fan charts, waterfall, tornado
3. **Explainability** — drill into position-level changes, intelligence objects

### 4.5 Final Integration Tests

- Full regression suite across all modules
- Multi-scenario stochastic run with valuation
- Intelligence object generation test
- Text-to-strategy parsing test

---

## 5. Phase 3 Acceptance Criteria

- [ ] Valuation engine tracks carrying value, market value proxy, yield, fee income
- [ ] Variance decomposition attributes balance changes to specific drivers
- [ ] Sensitivity analysis identifies which parameters move outcomes most
- [ ] Contribution analysis breaks down changes by segment, rating, product, geography
- [ ] Text-to-strategy parser extracts signals from earnings call text
- [ ] Extracted strategy signals are presented to user for review before applying
- [ ] Intelligence objects generated from simulation results (risk alerts, opportunities, deviations)
- [ ] Per-position explainability reports show full change attribution
- [ ] Reporting API exposes structured outputs for dashboards
- [ ] 3 complete notebooks demonstrate full workflow
- [ ] Schema mapping documentation enables self-service onboarding

---

## 6. What Phase 3 Does NOT Include

Deferred to Phase 4:

- Strategy optimiser (finding best strategy, not just simulating a given one)
- Deal selection / prioritisation engine
- Capital / RWA constraints
- Liquidity consumption tracking
- Historical calibration from real data
- Behavioural cohort learning
- Management action simulation (mid-run interventions)
- Reverse stress testing
- Parallel execution engine (Ray/Dask)
- Scenario authoring UI
