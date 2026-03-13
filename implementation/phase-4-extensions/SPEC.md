# Phase 4: Decision Intelligence Extensions

**Duration**: Weeks 15–20 (backlog, prioritised delivery)

**Goal**: Transform the simulation engine into a full decision intelligence platform —
strategy optimisation, deal selection, capital/liquidity constraints, historical
calibration, behavioural learning, and scaling.

**Prerequisite**: Phase 3 complete — valuation, sensitivity, explainability, intelligence
objects all working.

---

## 1. What This Phase Delivers

Phase 4 is a prioritised backlog rather than a fixed sprint plan. Features are ordered
by value and can be delivered incrementally. By the end, the system goes from
"simulation engine" to "decision intelligence platform" — answering not just
"what happens?" but "what should we do?"

---

## 2. Feature Backlog (Priority Order)

### 2.1 Strategy Optimizer

**Value**: Very High — transforms the engine from simulation to decision support.

Instead of simulating a given strategy, search for the best strategy under constraints.

Example questions the optimizer answers:

- What pipeline mix maximises RORAC while keeping capital usage below threshold?
- What origination strategy meets growth targets but keeps average rating above BBB-?
- What pricing discipline keeps balances stable if utilisation falls?

Architecture:

```
Optimizer
  ├── Objective function (maximize: NIM, RORAC, growth, diversification)
  ├── Constraints (capital <= X, concentration <= Y, rating >= Z)
  ├── Decision variables (pipeline multipliers, approval thresholds, pricing floors)
  └── Search engine
       ├── Grid search (simple, exhaustive)
       ├── Bayesian optimisation (sample-efficient)
       └── Heuristic search (rule-based pruning)
```

Config:

```yaml
optimize:
  objective:
    maximize: portfolio_nim
  constraints:
    max_sector_concentration: 0.20
    min_avg_rating: "BBB-"
    max_capital_usage: 0.85
  search:
    method: bayesian
    max_evaluations: 200
    convergence_threshold: 0.01
```

Output: recommended strategy parameters with confidence intervals and trade-off analysis.

### 2.2 Deal Selection / Prioritisation Engine

**Value**: Very High — portfolio construction from pipeline.

From a pipeline of N deals, rank by portfolio impact:

```
Deal Score = margin_contribution
           + diversification_benefit
           - capital_cost
           - rating_risk_penalty
           - concentration_penalty
           + relationship_value
```

Features:

- Score each pipeline deal by marginal portfolio impact
- Rank by composite score
- Show top-N recommended deals with rationale
- Simulate portfolio impact of accepting top-K deals
- Support "what if I fund these 50 deals?" analysis

Output:

```
=== Deal Prioritisation (top 10) ===

Rank  Deal ID      Counterparty       Amount    Margin  Capital  Score
1     PIPE-0042    Acme Mfg           $25M      3.2%    $2.1M    0.94
2     PIPE-0187    Beta Logistics     $15M      2.8%    $1.4M    0.91
3     PIPE-0503    Gamma Tech         $40M      2.5%    $4.0M    0.87
...

Portfolio impact of funding top 10:
  +$180M funded balance, +12bps NIM, -2% CRE concentration, +$18M capital usage
```

### 2.3 Capital & RWA Constraints

**Value**: High — enables "growth under constraints" planning.

Compute for each position:

- **Risk-Weighted Assets (RWA)**: using standardised or IRB approach
  `RWA = EAD × risk_weight(PD, LGD, maturity, asset_class)`
- **Economic Capital (EC)**: `EC = EAD × LGD × (stressed_PD - expected_PD) × correlation_factor`
- **Leverage Exposure**: gross funded + undrawn commitment × CCF

Aggregate and track through simulation.

Apply constraints:

```yaml
constraints:
  capital:
    cet1_ratio_min: 0.10
    total_capital_ratio_min: 0.13
    leverage_ratio_min: 0.05
  concentration:
    max_single_name: 0.03
    max_sector: 0.20
    max_geography: 0.25
  liquidity:
    max_commitment_to_deposit_ratio: 0.85
```

When constraint is breached, engine can:
- Flag warning
- Halt new originations in affected segment
- Reduce pipeline conversion probability

### 2.4 Liquidity Consumption Tracking

**Value**: High — critical for revolving credit portfolios.

Track:

- Total committed lines (funded + unfunded)
- Undrawn commitments by segment
- Draw risk under stress (what happens if utilisation spikes to 90%?)
- Liquidity buffer usage

Useful questions:

- How much liquidity headroom do we have under a drawdown spike scenario?
- Which segments consume the most liquidity per unit of income?

### 2.5 Historical Calibration Engine

**Value**: High — critical for realism.

Train transition probabilities from historical data:

**Pipeline calibration**:
- Ingest historical pipeline snapshots (monthly or quarterly)
- Compute observed transition frequencies between stages
- Fit stage duration distributions (Weibull, log-normal)
- Estimate close probabilities by segment, product, rating, deal size

**Funded calibration**:
- Ingest historical portfolio roll-forwards
- Estimate prepayment rates by cohort
- Estimate renewal probabilities
- Calibrate utilisation dynamics

**Rating calibration**:
- Ingest historical rating transition data
- Fit transition matrices by segment and economic cycle
- Validate against Moody's published matrices

Output: calibrated parameter files that replace expert-rule defaults.

```
portfolio-evolution calibrate \
  --historical-pipeline pipeline_history.parquet \
  --historical-funded funded_history.parquet \
  --output config/calibrated/
```

### 2.6 Behavioural Cohort Learning

**Value**: Medium — improves realism for heterogeneous portfolios.

Instead of uniform rules, cluster positions into behavioural cohorts:

- **Cohort A**: Sponsor LBO term loans — high prepayment, low renewal, bullet structure
- **Cohort B**: SME revolvers — high utilisation volatility, high renewal, seasonal draws
- **Cohort C**: CRE construction — staged disbursement, low prepay, maturity-driven
- **Cohort D**: Investment-grade corporate — low default, stable utilisation, repricing-sensitive

Each cohort gets its own evolution parameters. Clustering can be:
- Rule-based (product × segment × rating band)
- ML-based (k-means on historical behaviour features)

### 2.7 Management Action Simulation

**Value**: Medium — enables "what if we change policy mid-year?" analysis.

Allow mid-simulation interventions:

```yaml
management_actions:
  - day: 60
    action: "tighten CRE underwriting"
    effect:
      CRE:
        approval_multiplier: 0.70
        pipeline_inflow_multiplier: 0.80

  - day: 90
    action: "raise spread floors 20bps"
    effect:
      pricing_floor_shift_bps: 20

  - day: 120
    action: "reduce tenor for leveraged loans"
    effect:
      leveraged:
        max_tenor_months: 60
        average_tenor_multiplier: 0.80
```

The engine evaluates cumulative impact of sequential policy changes. This is
analogous to central bank policy path modelling.

### 2.8 Reverse Stress Testing

**Value**: Medium — finds breaking points.

Instead of "what happens under scenario X?", ask: "what scenario causes constraint Y to breach?"

Search algorithm:

1. Define constraint: `CET1_ratio >= 10%`
2. Search over scenario parameter space (spread, growth, unemployment, default)
3. Find minimum-severity scenario that causes breach
4. Report the breaking-point scenario and the path to breach

Useful for:
- Regulatory stress testing (CCAR/DFAST-style)
- Board risk appetite calibration
- Capital planning

### 2.9 Parallel Simulation Engine

**Value**: Medium — enables production-scale runs.

Parallelise across:

- Paths (embarrassingly parallel)
- Scenarios (independent)
- Portfolio segments (if no cross-segment dependencies)

Technology options:

- **multiprocessing** (simplest, built-in)
- **Ray** (distributed, good for cloud scaling)
- **Dask** (DataFrame-native parallelism)

Target: 10,000 paths × 365 days in under 30 minutes.

### 2.10 Scenario Authoring UI

**Value**: Low-Medium — improves accessibility for non-technical users.

Web-based UI for:

- Creating scenarios via sliders (spread shift, growth, unemployment)
- Creating scenarios via narrative prompts ("moderate recession with tightening credit")
  — LLM converts text to parameter set
- Comparing scenario definitions side-by-side
- Launching simulation runs
- Viewing results with interactive charts

Tech: Streamlit or Panel for MVP. Full web app (React + FastAPI) for production.

---

## 3. Delivery Priority Matrix

| Feature | Value | Effort | Priority |
|---------|-------|--------|----------|
| Strategy optimizer | Very High | High | P1 |
| Deal selection engine | Very High | Medium | P1 |
| Capital & RWA constraints | High | Medium | P2 |
| Liquidity consumption | High | Low-Medium | P2 |
| Historical calibration | High | High | P2 |
| Behavioural cohort learning | Medium | Medium | P3 |
| Management action simulation | Medium | Medium | P3 |
| Reverse stress testing | Medium | High | P3 |
| Parallel simulation engine | Medium | Medium | P3 |
| Scenario authoring UI | Low-Medium | High | P4 |

Recommended delivery order:

- **Weeks 15–16**: Deal selection engine + capital constraints (quick wins, high value)
- **Weeks 17–18**: Strategy optimizer + liquidity tracking
- **Weeks 19–20**: Historical calibration + management actions
- **Beyond week 20**: Cohort learning, reverse stress, parallelisation, UI

---

## 4. The Decision Intelligence Shift

Phase 4 transforms the system from a simulation engine into a decision intelligence
platform. The key shift:

| Before Phase 4 | After Phase 4 |
|-----------------|---------------|
| "What happens under scenario X?" | "What should we do given scenario X?" |
| Simulate a given strategy | Search for the best strategy |
| Report portfolio evolution | Recommend portfolio actions |
| Show risk metrics | Enforce risk constraints |
| Use expert-rule parameters | Learn parameters from history |

This aligns with the BDI thesis: knowledge operationalised into judgement.

---

## 5. Phase 4 Acceptance Criteria

- [ ] Strategy optimizer finds parameter sets that maximise objective under constraints
- [ ] Deal selection engine ranks pipeline deals by marginal portfolio impact
- [ ] Capital / RWA computed and tracked through simulation
- [ ] Constraints (capital, concentration, liquidity) enforced or flagged
- [ ] Historical calibration produces parameter files from real data
- [ ] Management actions can be injected mid-simulation
- [ ] Parallel engine scales to 10k+ paths
- [ ] At least one of: reverse stress testing, cohort learning, or scenario UI delivered

---

## 6. Integration with Moody's Ecosystem

Phase 4 features connect naturally to existing Moody's products:

- **Rating migration matrices**: calibrate from Moody's published transition data
- **EDFX PD data**: feed entity-level PDs into position-level risk scoring
- **Scenario data**: use Moody's standard macro scenarios (baseline, S1-S4)
- **Portfolio Studio**: export results in PS-compatible format for KPI analysis
- **RPA deal data**: import deal information for pipeline enrichment
- **Climate risk**: layer physical/transition risk scenarios onto rating migration
