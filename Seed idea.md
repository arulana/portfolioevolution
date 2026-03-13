Below is a working spec you can hand to a coding agent.

⸻

Spec: Daily Portfolio Evolution & Pipeline Simulation Engine

1. Purpose

Build a simulation engine that takes:

	•	a funded portfolio snapshot

	•	a pipeline snapshot, marked as the base case

	•	optional strategy statements from a bank or bank-like lender

	•	optional scenario overlays

and simulates:

	•	daily pipeline movement

	•	daily funded portfolio evolution

	•	drawdowns / utilisation changes

	•	booking / closing / fallout / renewals / repayments / amortisation

	•	rating migration

	•	instrument value evolution

	•	scenario-based forecasting

The tool should support both:

	1.	stochastic simulation for portfolio evolution

	2.	scenario forecasting for management planning, balance sheet/risk planning, and strategy testing

⸻

2. Core Outcome

The engine should answer questions like:

	•	How does today’s pipeline turn into funded assets over the next 30 / 90 / 365 days?

	•	What mix shift occurs by segment, industry, rating, tenor, structure, or utilisation?

	•	How does the funded portfolio evolve under management strategy, risk appetite, and macro scenarios?

	•	What happens to balances, commitments, yields, risk metrics, and ratings over time?

	•	What is the expected distribution, not just point estimate?

	•	How sensitive is evolution to pricing strategy, origination focus, credit tightening, rating migration, or customer drawdown behaviour?

⸻

3. High-Level Design

The system should model the portfolio as two coupled populations:

A. Pipeline population

Unfunded or partially committed opportunities progressing through states.

Examples of states:

	•	Lead

	•	Underwriting

	•	Approved

	•	Committed

	•	Documentation

	•	Closing

	•	Funded

	•	Dropped / Lost

	•	Expired

B. Funded portfolio population

Booked instruments whose balances and risk characteristics evolve over time.

Examples of events:

	•	Amortisation

	•	Scheduled maturity

	•	Renewal / refinance

	•	Prepayment

	•	Draw / repayment

	•	Covenant deterioration / improvement

	•	Rating migration

	•	Restructuring

	•	Default / impairment

The engine runs in daily time steps and allows Monte Carlo sampling or deterministic expected-value mode.

⸻

4. Functional Requirements

4.1 Inputs

Mandatory

	•	funded_portfolio_base: current funded positions

	•	pipeline_base: current pipeline opportunities

	•	simulation_config

	•	calendar_config

Optional

	•	strategy_text: earnings call excerpts, management statements, investor presentation language, policy notes

	•	strategy_structured_overrides

	•	scenario_definitions

	•	transition_rule_overrides

	•	rating_migration_matrices

	•	utilisation_behaviour_rules

	•	market_environment_inputs

⸻

4.2 Outputs

Required outputs

	•	Daily simulated states for all pipeline and funded positions

	•	Aggregated portfolio roll-forward

	•	Expected and percentile distributions for:

	•	funded balances

	•	commitments

	•	utilisation

	•	originations

	•	runoff

	•	segment mix

	•	rating mix

	•	yield / spread

	•	expected loss proxy

	•	capital proxy if configured

Scenario outputs

	•	Base vs downside vs upside comparison

	•	Contribution analysis by driver

	•	Variance decomposition:

	•	booking volume

	•	drawdown

	•	amortisation

	•	rating migration

	•	strategy tilt

	•	macro/scenario effect

Explainability outputs

	•	For each simulated transition, record:

	•	triggering rule

	•	stochastic draw used

	•	scenario modifiers applied

	•	strategy modifiers applied

	•	previous and next state

⸻

5. Data Model

5.1 Common entity design

Use a normalized object model so both funded and pipeline records share a common schema.

InstrumentPosition

instrument_id: string

counterparty_id: string

facility_id: string|null

position_type: enum[pipeline, funded]

product_type: string

segment: string

subsegment: string|null

industry: string|null

geography: string|null

currency: string

origination_channel: string|null

# economics

committed_amount: float

funded_amount: float

utilisation_rate: float|null

undrawn_amount: float|null

coupon_type: enum[fixed, floating, fee_based, other]

coupon_rate: float|null

spread_bps: float|null

benchmark_rate: float|null

fee_rate: float|null

purchase_price: float|null

market_value: float|null

carrying_value: float|null

# structure / t&c

origination_date: date|null

expected_close_date: date|null

maturity_date: date|null

amortisation_type: enum[bullet, linear, sculpted, revolving, other]|null

repayment_schedule: object|null

seniority: string|null

secured_flag: bool|null

collateral_type: string|null

covenant_package: string|null

tenor_months: int|null

extension_options: object|null

call_protection: object|null

# risk

internal_rating: string|null

external_rating: string|null

pd: float|null

lgd: float|null

watchlist_flag: bool|null

stage: string|null

risk_grade_bucket: string|null

default_flag: bool

# lifecycle

pipeline_stage: string|null

approval_status: string|null

close_probability: float|null

days_in_stage: int|null

renewal_probability: float|null

prepayment_probability: float|null

# metadata

data_quality_score: float|null

source_system: string|null

as_of_date: date


⸻

5.2 Strategy objects

StrategySignal

Represents management direction extracted from earnings calls or structured manually.

signal_id: string

source_type: enum[earnings_call, investor_presentation, manual, policy]

statement_text: string

effective_date: date

expiry_date: date|null

dimension: enum[segment, industry, geography, product_type, rating_band, tenor, pricing, utilisation, risk_appetite]

target_value: string|float|object

direction: enum[increase, decrease, tighten, loosen, maintain, rotate]

magnitude: float   # normalized 0 to 1

confidence: float  # 0 to 1

translation_rule: string

Examples:

	•	Increase C&I originations to sponsor-backed upper middle market

	•	Tighten CRE exposure

	•	Improve deposit spread discipline

	•	Shorten duration

	•	Focus on higher-quality borrowers

	•	Increase cross-sell in existing client base

⸻

5.3 Scenario object

ScenarioDefinition

scenario_id: string

name: string

description: string

start_date: date

end_date: date

macro_factors:

  benchmark_rate_shift_bps: float

  credit_spread_shift_bps: float

  growth_factor: float

  inflation_factor: float

  unemployment_factor: float

  sector_stress: object

  geography_stress: object

transition_modifiers:

  booking_rate_multiplier: float

  fallout_rate_multiplier: float

  prepayment_multiplier: float

  renewal_multiplier: float

  utilisation_multiplier: float

  downgrade_multiplier: float

  default_multiplier: float

pricing_modifiers:

  new_business_spread_shift_bps: float

  refinance_spread_shift_bps: float


⸻

6. Simulation Logic

6.1 Daily engine loop

For each simulation day:

	1.	Load current pipeline state

	2.	Load current funded state

	3.	Apply calendar logic

	•	business day handling

	•	month-end effects if configured

	4.	Update pipeline transitions

	5.	Convert qualified pipeline deals into funded deals

	6.	Update funded balances and cashflow behaviour

	7.	Apply utilisation changes

	8.	Apply repayments / amortisation / maturity / renewal

	9.	Apply rating migration

	10.	Revalue positions if valuation logic enabled

	11.	Aggregate outputs

	12.	Write explainability log

⸻

6.2 Pipeline simulation rules

Each pipeline record evolves through a stage-transition model.

Example transition probabilities

For each record on each day:

	•	P(Underwriting -> Approved)

	•	P(Approved -> Documentation)

	•	P(Documentation -> Closing)

	•	P(Closing -> Funded)

	•	P(any active stage -> Dropped)

	•	P(stage remains unchanged)

Transition probabilities should depend on:

	•	current stage

	•	days in stage

	•	product type

	•	segment

	•	client quality / rating

	•	deal size

	•	geography

	•	strategy tilt

	•	scenario overlay

	•	seasonality

	•	relationship status / existing client flag if available

Example form

base_prob

x strategy_multiplier

x scenario_multiplier

x stage_age_factor

x segment_factor

x rating_factor

Support both:

	•	hazard-rate formulation

	•	transition matrix formulation

⸻

6.3 Funding conversion

When pipeline reaches Funded:

	•	create new funded instrument from pipeline record

	•	initialize:

	•	origination date

	•	funded amount

	•	commitment

	•	utilisation

	•	pricing

	•	rating

	•	schedule

	•	remove or archive pipeline record

	•	create lineage link:

	•	source_pipeline_id -> new_funded_instrument_id

Support partial funding:

	•	revolving line commitment booked but only partial funded balance

	•	staged disbursement facilities

	•	delayed draw terms

⸻

6.4 Funded portfolio evolution

Each funded position evolves daily via stateful rules.

Events to simulate

	•	amortisation

	•	maturity runoff

	•	rollover / renewal

	•	utilisation movement

	•	partial repayment

	•	prepayment

	•	repricing where relevant

	•	rating migration

	•	default / charge-off if in scope

Behaviour drivers

	•	product type

	•	revolving vs term

	•	borrower quality

	•	interest-rate environment

	•	management strategy

	•	market scenario

	•	contractual schedule

	•	seasonality

	•	borrower cohort archetype

⸻

7. Driving Characteristics / Behavioural Drivers

The user asked for driving characteristics based on earnings call strategy statements or bank-like behaviour. Build a translation layer that maps qualitative strategy into quantitative modifiers.

7.1 Strategy translation layer

Create a module:

StrategyInterpreter

Purpose:

	•	ingest text or structured strategic statements

	•	classify statements into business levers

	•	translate into simulation parameter shifts

Example mapping

Statement

“Grow commercial and industrial lending in the middle market while remaining selective in office CRE.”

Quant translation

segment_overrides:

  C&I_middle_market:

    pipeline_inflow_multiplier: 1.20

    approval_multiplier: 1.10

    pricing_shift_bps: -10

  CRE_office:

    new_pipeline_multiplier: 0.70

    approval_multiplier: 0.75

    downgrade_multiplier: 1.15

Statement

“We are focused on better returns, tighter spreads discipline, and higher-quality origination.”

Quant translation

pricing_floor_shift_bps: +15

subinvestment_grade_approval_multiplier: 0.85

investment_grade_approval_multiplier: 1.05

average_tenor_multiplier: 0.90


⸻

7.2 Behavioural archetypes

Support prebuilt lender archetypes:

	•	conservative regional bank

	•	growth-oriented commercial bank

	•	sponsor-focused direct lender

	•	asset-based lender

	•	credit fund

	•	CRE-heavy bank

	•	relationship-bank archetype

Each archetype should provide default priors for:

	•	pipeline conversion speed

	•	fallout rate

	•	pricing aggressiveness

	•	rating tolerance

	•	utilisation behaviour

	•	renewal tendency

	•	tenor preference

	•	sector appetite

	•	risk tightening under stress

⸻

8. Rating Migration Rules

The engine must support rating migration for both pipeline and funded positions.

8.1 Requirements

	•	daily or monthly migration cadence, applied through daily engine

	•	configurable transition matrix by:

	•	segment

	•	product type

	•	scenario

	•	starting rating

	•	optional point-in-time adjustment based on macro conditions

8.2 Migration model options

Option A: Matrix-based

Use rating transition matrix and convert monthly/annual transitions into daily probabilities.

Option B: Score-based

Maintain latent credit score and map score bands to ratings. Score drifts based on scenario and borrower factors.

Option C: Hybrid

Score evolves daily, rating only changes when score crosses thresholds; fallback matrices used where data sparse.

8.3 Minimum rule set

	•	upgrades and downgrades allowed

	•	watchlist increases downgrade probability

	•	stressed sectors have elevated downgrade/default transition

	•	new originations inherit rating from pipeline or underwriting estimate

	•	refinancing can change rating if policy allows re-underwriting adjustment

⸻

9. Valuation / Economic Evolution

Given the data richness includes value of loan/instruments and t&c, support optional valuation logic.

9.1 Minimum supported measures

	•	carrying value

	•	funded balance

	•	accrued interest proxy

	•	market value proxy

	•	expected yield / spread

	•	undrawn fee income proxy

9.2 Optional valuation enhancements

	•	discount cashflows under scenario curves

	•	spread widening/narrowing effect on fair value

	•	expected credit loss proxy

	•	liquidity premium or funding cost overlay

⸻

10. Scenario Forecasting Mode

The spec should indeed double as a scenario forecasting tool.

10.1 Two operating modes

Mode 1: Simulation mode

Focus on bottom-up stochastic evolution of individual deals and positions.

Mode 2: Forecast mode

Focus on scenario planning with management overlays and expected-value paths.

In forecast mode:

	•	fewer Monte Carlo paths may be needed

	•	deterministic levers are emphasized

	•	reporting compares scenarios directly

⸻

10.2 Example forecast questions

	•	What happens to funded balances if origination focus shifts to C&I and CRE tightens?

	•	What is the 90-day booking outlook under a mild recession?

	•	How does a +100 bps benchmark move change utilisation, runoff, and spread income?

	•	What rating mix is expected by year-end?

	•	How much of change is driven by pipeline conversion vs migration vs runoff?

⸻

11. Architecture

11.1 Modules

A. data_ingestion

	•	load portfolio and pipeline snapshots

	•	validate schema

	•	fill defaults

	•	flag bad records

B. feature_engineering

	•	derive tenor buckets, rating bands, balance buckets, stage age

	•	compute undrawn amounts

	•	map industries/segments to canonical taxonomy

C. strategy_interpreter

	•	parse qualitative strategy statements

	•	emit structured strategy modifiers

D. scenario_engine

	•	manage scenario objects

	•	apply global and segment-specific modifiers

E. pipeline_transition_engine

	•	simulate stage changes

	•	simulate funding / fallout / expiry

F. funded_evolution_engine

	•	simulate balances, utilisation, repricing, maturity, renewal

G. rating_engine

	•	migrate ratings and default states

H. valuation_engine

	•	update economic measures

I. aggregation_engine

	•	roll up outputs by day/path/scenario

J. explainability_logger

	•	write rule audit trail

K. reporting_api

	•	expose outputs for notebooks / dashboard / scenario comparison UI

⸻

12. Suggested Tech Design

12.1 Language

Prefer Python first.

12.2 Core libraries

	•	pandas or polars for data frames

	•	numpy for vectorized simulation

	•	pydantic for schema validation

	•	scipy for distributions where needed

	•	pyyaml for rules config

	•	networkx optional if lifecycle graph is explicit

	•	duckdb optional for scalable local analytics

	•	plotly or simple reporting layer optional

12.3 Design style

	•	rules-driven, config-first

	•	separate engine code from business rules

	•	allow YAML/JSON configuration of transition parameters

	•	deterministic reproducibility with seeded RNG

	•	support batch scenario execution

⸻

13. Config Design

13.1 Master config

simulation_horizon_days: 365

num_paths: 500

random_seed: 42

time_step: daily

mode: stochastic   # stochastic | deterministic_forecast

calendar:

  business_days_only: true

  country: US

pipeline:

  enabled: true

  allow_partial_funding: true

funded:

  amortisation_enabled: true

  renewal_enabled: true

  prepayment_enabled: true

  utilisation_sim_enabled: true

ratings:

  enabled: true

  approach: matrix_hybrid

valuation:

  enabled: true

  fair_value_mode: simple

output:

  store_position_level_history: true

  store_event_log: true

  aggregate_frequency: daily


⸻

14. Agent Deliverables

The coding agent should produce:

Phase 1

	•	project skeleton

	•	schema definitions

	•	synthetic sample data generator

	•	deterministic daily engine

	•	simple transition rules

	•	daily roll-forward outputs

Phase 2

	•	stochastic simulation

	•	rating migration module

	•	utilisation module

	•	strategy interpreter with manual structured input

	•	scenario comparison reporting

Phase 3

	•	text-to-strategy translation from earnings call text

	•	valuation enhancements

	•	sensitivity analysis

	•	explainability reports

	•	notebook examples / dashboard API

⸻

15. Acceptance Criteria

Functional

	•	Can ingest funded and pipeline snapshots

	•	Can simulate daily evolution over configurable horizon

	•	Can convert pipeline into funded positions

	•	Can simulate amortisation / runoff / renewals

	•	Can apply rating migration

	•	Can run at least 3 named scenarios

	•	Can produce aggregate roll-forward tables and position-level logs

Explainability

	•	Every non-trivial state change has a recorded reason code

	•	Outputs show effect of strategy and scenario overlays separately

Quality

	•	Reproducible results with seed

	•	Unit tests for each module

	•	Integration test for 30-day toy portfolio run

	•	No hard-coded business rules inside core engine where config should be used

Performance

	•	Handle at least:

	•	100k funded positions

	•	20k pipeline positions

	•	100 paths

	•	90-day horizon

within practical runtime on a developer machine, using vectorization where possible

⸻

16. Example Daily Event Logic

Pipeline record example

For each active pipeline deal on day t:

	1.	increment days_in_stage

	2.	compute adjusted transition probabilities

	3.	draw random event

	4.	if funded:

	•	instantiate funded position

	•	assign utilisation / funded amount

	5.	if dropped:

	•	archive with reason code

	6.	else remain in stage

Funded record example

For each funded position on day t:

	1.	apply scheduled amortisation

	2.	simulate unscheduled repayment / draw

	3.	update utilisation

	4.	check maturity

	5.	if matured:

	•	runoff or renew based on renewal probability

	6.	update rating

	7.	revalue if enabled

⸻

17. Pseudocode

for scenario in scenarios:

    for path in range(num_paths):

        pipeline = load_pipeline_base()

        funded = load_funded_base()

        for day in simulation_days:

            strategy_mods = strategy_engine.get_modifiers(day, scenario)

            scenario_mods = scenario_engine.get_modifiers(day, scenario)

            pipeline_events = pipeline_engine.step(

                pipeline_df=pipeline,

                funded_df=funded,

                day=day,

                strategy_mods=strategy_mods,

                scenario_mods=scenario_mods,

            )

            funded = book_new_originations(

                funded_df=funded,

                funded_from_pipeline=pipeline_events.new_funded_positions

            )

            funded_events = funded_engine.step(

                funded_df=funded,

                day=day,

                strategy_mods=strategy_mods,

                scenario_mods=scenario_mods,

            )

            funded = rating_engine.step(

                funded_df=funded,

                day=day,

                scenario_mods=scenario_mods

            )

            funded = valuation_engine.step(

                funded_df=funded,

                day=day,

                scenario_mods=scenario_mods

            )

            aggregates = aggregation_engine.compute(day, pipeline, funded)

            logger.write(day, path, scenario, pipeline_events, funded_events, aggregates)


⸻

18. Key Modeling Assumptions to Encode Explicitly

The agent should not bury these in code. Keep them configurable:

	•	Whether weekends/business days count

	•	Whether close probabilities are point-in-time or stage-based

	•	Whether utilisation is mean-reverting or event-driven

	•	Whether maturity always triggers runoff vs possible renewal

	•	Whether rating migration is monthly-applied or daily-converted

	•	Whether scenario affects only new business or also back book

	•	Whether strategy statements influence:

	•	pipeline inflow

	•	approval

	•	pricing

	•	rating tolerance

	•	tenor

	•	sector selection

	•	Whether valuations are accounting balances or economic fair values

⸻

19. Nice-to-Have Extensions

	•	cohort-level calibration from historical bank data

	•	reverse stress mode

	•	manager actions:

	•	tighten underwriting

	•	shift pricing floors

	•	cap sector exposure

	•	limit tenor

	•	concentration constraints

	•	capital / RWA / liquidity usage overlay

	•	link scenario paths to macro generators

	•	UI for scenario authoring

	•	LLM-assisted explanation of forecast changes

⸻

20. Instruction to Coding Agent

Build this as a rules-driven simulation framework, not a single notebook. Prioritize:

	1.	clean object model

	2.	daily state-transition engine

	3.	explainability log

	4.	strategy/scenario overlays as first-class objects

	5.	config-based rule control

	6.	ability to run both stochastic simulation and deterministic scenario forecast

Do not assume perfect historical calibration exists. The first version should support:

	•	expert-rule initialization

	•	manual parameter overrides

	•	synthetic data test harness

	•	later calibration from real historical transitions

⸻

21. Test-Driven Development Approach

The coding agent must follow strict TDD: write failing tests first, then implement the minimum code to pass, then refactor. Every module, every phase, tests lead.

21.1 TDD Principles for This Project

	•	Red-Green-Refactor: write a failing test, make it pass with minimal code, clean up
	•	Tests are the spec: each test encodes a business rule or invariant from this document
	•	No production code without a failing test: if there is no test demanding it, do not write it
	•	Tests must be fast: unit tests complete in < 1 second per module; full suite < 60 seconds
	•	Deterministic by default: seed all randomness so every test is reproducible
	•	Test names describe business behaviour, not implementation: test_pipeline_deal_advances_from_underwriting_to_approved not test_transition_method

21.2 Test Categories

Category A: Unit tests (per module)

Isolated tests for each engine module. Mock all dependencies. These are written first.

Category B: Contract tests (data model)

Verify that pydantic schemas accept valid data and reject invalid data. Written before any engine logic.

Category C: Integration tests (module pairs)

Test handoff between modules: pipeline -> funding conversion -> funded portfolio. Written as modules connect.

Category D: Property-based tests (invariants)

Use hypothesis or similar to verify portfolio-wide invariants hold across random inputs:
	•	total balance never goes negative
	•	sum of funded + pipeline + runoff + dropped = original population
	•	transition probabilities sum to <= 1.0
	•	utilisation rate stays in [0, 1]

Category E: Scenario acceptance tests (end-to-end)

Full simulation runs on toy portfolio with known expected outcomes. Written per phase completion.

Category F: Regression tests (golden file)

Capture output of a canonical run with seed=42 on a fixed toy portfolio. Any code change that alters output must be intentional and documented.

⸻

21.3 Test Infrastructure (Build First)

Before any module, the agent must build:

	1.	tests/ directory structure mirroring src/

tests/
  conftest.py                    # shared fixtures
  fixtures/
    sample_funded_portfolio.json
    sample_pipeline.json
    sample_scenarios.yaml
    sample_strategy_signals.yaml
    expected_outputs/
      golden_30day_run.json
  unit/
    test_data_ingestion.py
    test_feature_engineering.py
    test_strategy_interpreter.py
    test_scenario_engine.py
    test_pipeline_transition_engine.py
    test_funded_evolution_engine.py
    test_rating_engine.py
    test_valuation_engine.py
    test_aggregation_engine.py
    test_explainability_logger.py
  integration/
    test_pipeline_to_funding.py
    test_daily_engine_loop.py
    test_scenario_comparison.py
    test_strategy_overlay_effect.py
  property/
    test_portfolio_invariants.py
    test_probability_constraints.py
    test_balance_conservation.py
  acceptance/
    test_phase1_deterministic_run.py
    test_phase2_stochastic_run.py
    test_phase3_full_feature_run.py

	2.	conftest.py shared fixtures

Provide reusable fixtures:
	•	small_funded_portfolio: 10 funded positions with diverse product types
	•	small_pipeline: 15 pipeline deals across stages
	•	base_simulation_config: 30-day, 1-path, deterministic, seed=42
	•	base_scenario: neutral scenario (all multipliers = 1.0)
	•	stress_scenario: recession scenario with elevated defaults
	•	sample_strategy_signals: 3 strategy statements with known translations
	•	sample_transition_matrix: 8x8 rating transition matrix
	•	business_day_calendar: US calendar for date range

	3.	Synthetic data generator tests

The synthetic data generator itself must be tested:
	•	generates valid schema-conforming records
	•	covers all product types
	•	covers all pipeline stages
	•	produces realistic value distributions
	•	is deterministic with seed

⸻

21.4 Phase 1 TDD Spec: Foundation

Write these tests BEFORE implementing Phase 1 code.

A. Data Model / Schema Tests (test first)

test_instrument_position_valid_funded:
  create InstrumentPosition with position_type=funded, all required fields
  assert: object created, no validation error

test_instrument_position_valid_pipeline:
  create InstrumentPosition with position_type=pipeline, pipeline_stage set
  assert: object created

test_instrument_position_rejects_negative_funded_amount:
  create InstrumentPosition with funded_amount=-100
  assert: ValidationError raised

test_instrument_position_rejects_utilisation_above_one:
  create InstrumentPosition with utilisation_rate=1.5
  assert: ValidationError raised

test_instrument_position_default_flag_defaults_false:
  create InstrumentPosition without default_flag
  assert: default_flag is False

test_scenario_definition_valid:
  create ScenarioDefinition with all required fields
  assert: object created

test_strategy_signal_valid:
  create StrategySignal with valid enum values
  assert: object created

test_strategy_signal_rejects_invalid_direction:
  create StrategySignal with direction="invalid"
  assert: ValidationError

B. Data Ingestion Tests

test_load_funded_portfolio_from_json:
  given: valid JSON file with 10 funded positions
  when: data_ingestion.load_funded_portfolio(path)
  then: returns DataFrame with 10 rows, correct dtypes

test_load_pipeline_from_json:
  given: valid JSON file with 15 pipeline records
  when: data_ingestion.load_pipeline(path)
  then: returns DataFrame with 15 rows

test_ingestion_flags_missing_required_fields:
  given: JSON with records missing instrument_id
  when: data_ingestion.load_funded_portfolio(path)
  then: returns quality report with flagged records

test_ingestion_fills_defaults:
  given: JSON with records missing optional fields
  when: data_ingestion.load_funded_portfolio(path)
  then: null optional fields filled with configured defaults

test_ingestion_rejects_empty_file:
  given: empty JSON file
  when: data_ingestion.load_funded_portfolio(path)
  then: raises DataIngestionError

C. Feature Engineering Tests

test_derive_tenor_bucket:
  given: position with tenor_months=36
  when: feature_engineering.derive_tenor_bucket(position)
  then: returns "3-5Y"

test_compute_undrawn_amount:
  given: position with committed=1000, funded=600
  when: feature_engineering.compute_undrawn(position)
  then: undrawn_amount = 400

test_derive_rating_band:
  given: position with internal_rating="BBB+"
  when: feature_engineering.derive_rating_band(position)
  then: returns "investment_grade"

test_map_industry_to_taxonomy:
  given: position with industry="Oil & Gas Exploration"
  when: feature_engineering.map_industry(position, taxonomy)
  then: mapped to canonical "Energy"

D. Deterministic Daily Engine Tests

test_engine_runs_one_day_no_crash:
  given: small portfolio, 1-day horizon, deterministic mode
  when: engine.run()
  then: completes without error, returns results

test_engine_runs_30_days:
  given: small portfolio, 30-day horizon, deterministic mode
  when: engine.run()
  then: returns 30 daily snapshots

test_engine_pipeline_deal_advances_one_stage:
  given: 1 pipeline deal in Underwriting with P(advance)=1.0
  when: engine runs 1 day
  then: deal is in Approved

test_engine_pipeline_deal_stays_if_prob_zero:
  given: 1 pipeline deal in Underwriting with P(advance)=0.0
  when: engine runs 1 day
  then: deal remains in Underwriting, days_in_stage incremented

test_engine_funded_position_amortises:
  given: 1 funded term loan, linear amortisation, 12-month tenor
  when: engine runs 30 days
  then: funded_amount reduced by expected amortisation schedule

test_engine_funded_position_matures:
  given: 1 funded position with maturity_date = today + 5 days
  when: engine runs 10 days
  then: position marked as matured on day 5

test_engine_preserves_total_count:
  given: 10 pipeline + 10 funded
  when: engine runs 30 days
  then: pipeline(active) + pipeline(dropped) + pipeline(funded) + funded(active) + funded(matured) = 20

test_engine_deterministic_reproducibility:
  given: same inputs, same seed
  when: engine.run() twice
  then: identical outputs

E. Simple Transition Rule Tests

test_base_transition_probability_lookup:
  given: deal in stage Approved, product_type=term_loan
  when: transition_engine.get_base_prob(deal)
  then: returns configured probability

test_stage_age_increases_transition_prob:
  given: deal in stage Approved for 30 days vs 5 days
  when: compare transition probabilities
  then: 30-day deal has higher probability

test_transition_probabilities_sum_valid:
  given: any deal state
  when: compute all outbound transition probabilities
  then: sum <= 1.0

F. Daily Roll-Forward Output Tests

test_output_contains_daily_balances:
  given: 30-day run
  when: inspect outputs
  then: each day has total_funded_balance, total_committed, total_pipeline_value

test_output_aggregates_by_segment:
  given: portfolio with 3 segments
  when: inspect daily aggregates
  then: segment-level breakdowns present and sum to total

⸻

21.5 Phase 2 TDD Spec: Stochastic & Risk

Write these tests BEFORE implementing Phase 2 code.

A. Stochastic Simulation Tests

test_stochastic_mode_produces_distribution:
  given: 100 paths, 30-day horizon
  when: engine.run(mode=stochastic)
  then: output has 100 path results

test_stochastic_paths_differ:
  given: 10 paths, same start
  when: engine.run()
  then: not all paths have identical day-30 balances

test_stochastic_mean_converges:
  given: 1000 paths, known transition probs
  when: compute mean outcome
  then: mean is within 5% of theoretical expected value

test_stochastic_percentiles_ordered:
  given: multi-path run
  when: compute p10, p50, p90 of funded_balance at day 30
  then: p10 <= p50 <= p90

test_stochastic_seed_reproducibility:
  given: seed=42, 100 paths
  when: run twice
  then: identical path-level results

B. Rating Migration Tests

test_rating_stays_same_if_no_migration_event:
  given: position rated BBB, P(stay)=1.0
  when: rating_engine.step()
  then: rating remains BBB

test_rating_downgrades:
  given: position rated BBB, P(downgrade to BBB-)=1.0
  when: rating_engine.step()
  then: rating is BBB-

test_rating_upgrades:
  given: position rated BBB, P(upgrade to BBB+)=1.0
  when: rating_engine.step()
  then: rating is BBB+

test_watchlist_increases_downgrade_probability:
  given: two identical positions, one on watchlist
  when: compare downgrade probabilities
  then: watchlist position has higher downgrade prob

test_stressed_sector_elevates_default:
  given: position in stressed sector under recession scenario
  when: rating_engine.step()
  then: default probability > base case

test_migration_matrix_rows_sum_to_one:
  given: any transition matrix
  when: sum each row
  then: all rows sum to 1.0 (within tolerance)

test_daily_migration_probability_derived_from_annual:
  given: annual transition matrix
  when: rating_engine.convert_to_daily()
  then: daily matrix^252 approximates annual matrix

test_new_origination_inherits_pipeline_rating:
  given: pipeline deal with internal_rating=A
  when: funded via pipeline conversion
  then: new funded position has internal_rating=A

C. Utilisation Module Tests

test_utilisation_stays_in_bounds:
  given: revolving position
  when: utilisation_engine.step() over 90 days
  then: utilisation_rate always in [0, 1]

test_utilisation_mean_reverts:
  given: position with utilisation=0.9, mean_target=0.5
  when: run 90 days with mean-reversion enabled
  then: utilisation trends toward 0.5

test_utilisation_undrawn_consistent:
  given: position with committed=1000
  when: any utilisation change
  then: undrawn = committed - funded_amount always

test_term_loan_utilisation_fixed:
  given: fully drawn term loan
  when: utilisation_engine.step()
  then: utilisation_rate stays at 1.0

D. Strategy Interpreter Tests

test_structured_strategy_parsed:
  given: YAML strategy with segment_overrides for C&I
  when: strategy_interpreter.parse(yaml)
  then: returns StrategyModifiers with C&I pipeline_inflow_multiplier=1.2

test_strategy_modifier_applied_to_transition:
  given: base_prob=0.05, strategy_multiplier=1.2
  when: compute adjusted probability
  then: adjusted = 0.06

test_strategy_with_no_applicable_signal_returns_neutral:
  given: strategy signals for CRE only, deal is C&I
  when: strategy_interpreter.get_modifiers(deal)
  then: all multipliers = 1.0

test_expired_strategy_signal_ignored:
  given: signal with expiry_date in the past
  when: strategy_interpreter.get_modifiers(today)
  then: signal not applied

E. Scenario Comparison Tests

test_recession_scenario_increases_defaults:
  given: base scenario vs recession scenario
  when: run both over 90 days
  then: recession has more defaults

test_scenario_comparison_output_structure:
  given: 3 named scenarios
  when: run all
  then: output contains comparison table with columns per scenario

test_scenario_modifiers_applied_correctly:
  given: scenario with booking_rate_multiplier=0.8
  when: inspect pipeline conversion rate
  then: conversion rate is 80% of base

⸻

21.6 Phase 3 TDD Spec: Advanced Features

Write these tests BEFORE implementing Phase 3 code.

A. Text-to-Strategy Translation Tests

test_earnings_call_growth_statement_detected:
  given: text = "We plan to grow C&I lending in the middle market"
  when: strategy_interpreter.parse_text(text)
  then: signal with dimension=segment, direction=increase, target includes C&I

test_earnings_call_tightening_statement_detected:
  given: text = "We are reducing our CRE exposure"
  when: strategy_interpreter.parse_text(text)
  then: signal with dimension=segment, target=CRE, direction=decrease

test_multiple_statements_produce_multiple_signals:
  given: paragraph with 3 distinct strategy statements
  when: strategy_interpreter.parse_text(paragraph)
  then: returns 3 StrategySignal objects

test_ambiguous_text_has_low_confidence:
  given: vague text = "We remain cautious"
  when: strategy_interpreter.parse_text(text)
  then: signal confidence < 0.5

B. Valuation Enhancement Tests

test_carrying_value_tracks_amortisation:
  given: term loan with known amort schedule
  when: run 90 days
  then: carrying_value decreases per schedule

test_market_value_responds_to_spread_change:
  given: position with fixed rate, scenario widens spreads +50bps
  when: valuation_engine.step()
  then: market_value decreases

test_accrued_interest_proxy_increases_daily:
  given: position with coupon_rate=5%
  when: valuation_engine.step() for 30 days
  then: accrued interest proxy = principal * 5% * 30/360

test_ecl_proxy_increases_on_downgrade:
  given: position downgraded from BBB to BB
  when: valuation_engine.compute_ecl_proxy()
  then: ECL proxy increases

C. Sensitivity Analysis Tests

test_sensitivity_to_booking_rate:
  given: base run vs run with booking_rate_multiplier=0.5
  when: compare day-90 funded balance
  then: quantified delta reported

test_sensitivity_report_ranks_drivers:
  given: sensitivity analysis across 5 parameters
  when: inspect sensitivity report
  then: drivers ranked by impact magnitude

D. Explainability Report Tests

test_every_state_change_has_reason_code:
  given: 30-day run on toy portfolio
  when: inspect explainability log
  then: every transition event has non-null reason_code

test_explainability_log_records_stochastic_draw:
  given: stochastic run
  when: inspect log for transition event
  then: random_draw value recorded

test_explainability_log_records_scenario_modifier:
  given: run under recession scenario
  when: inspect log
  then: scenario_modifier field populated for affected events

test_explainability_log_records_strategy_modifier:
  given: run with strategy signals
  when: inspect log for affected segment
  then: strategy_modifier field populated

⸻

21.7 Property-Based Tests (Invariants That Must Always Hold)

These run across random inputs using hypothesis or similar.

Portfolio Conservation:

	•	count(active_pipeline) + count(dropped) + count(funded_from_pipeline) = count(initial_pipeline) at all times
	•	no instrument_id appears in both pipeline and funded simultaneously (after conversion, pipeline record is archived)

Balance Invariants:

	•	funded_amount >= 0 for all positions at all times
	•	funded_amount <= committed_amount for all positions at all times
	•	utilisation_rate = funded_amount / committed_amount where committed > 0
	•	undrawn_amount = committed_amount - funded_amount

Probability Invariants:

	•	all transition probabilities in [0, 1]
	•	outbound transition probabilities from any state sum to <= 1.0
	•	strategy/scenario multipliers produce valid probabilities (clip to [0, 1] after multiplication)

Rating Invariants:

	•	rating is always a valid value from the configured rating scale
	•	defaulted positions do not migrate further (absorbing state)

Temporal Invariants:

	•	days_in_stage increments by 1 each business day if position did not transition
	•	days_in_stage resets to 0 on stage transition
	•	as_of_date advances monotonically

⸻

21.8 Golden File / Regression Tests

After each phase is complete, capture a golden output:

Phase 1 golden test:
	•	inputs: 10 funded + 15 pipeline, 30 days, deterministic, seed=42
	•	capture: final portfolio state, daily aggregates, event log
	•	store as: tests/fixtures/expected_outputs/golden_phase1_30day.json
	•	on every subsequent run, compare output to golden file byte-for-byte

Phase 2 golden test:
	•	inputs: same portfolio, 30 days, 50 paths, stochastic, seed=42
	•	capture: path-level final states, aggregate percentiles
	•	store as: tests/fixtures/expected_outputs/golden_phase2_30day_50path.json

Phase 3 golden test:
	•	inputs: same portfolio + 3 scenarios + 2 strategy signals, 90 days, 100 paths
	•	capture: scenario comparison, sensitivity analysis, explainability log
	•	store as: tests/fixtures/expected_outputs/golden_phase3_90day.json

Golden test update protocol:
	•	if a golden test fails, the developer must confirm the change is intentional
	•	update golden file only with explicit approval
	•	commit message must explain what changed and why

⸻

21.9 Performance Tests

test_100k_funded_90day_100path_completes_in_time:
  given: 100k funded positions, 90-day horizon, 100 paths
  when: engine.run()
  then: completes within 300 seconds on standard developer machine

test_vectorized_pipeline_step_faster_than_loop:
  given: 20k pipeline positions
  when: compare vectorized step vs row-by-row loop
  then: vectorized is at least 10x faster

test_memory_usage_within_bounds:
  given: 100k positions, 100 paths
  when: monitor peak memory
  then: peak memory < 8 GB

⸻

21.10 TDD Workflow Per Module

For each module in section 11.1, the coding agent must follow this exact order:

	1.	Write test file: tests/unit/test_{module_name}.py with all Category A tests
	2.	Run tests: confirm all fail (Red)
	3.	Write minimum implementation in src/{module_name}.py
	4.	Run tests: confirm all pass (Green)
	5.	Refactor: clean up implementation, re-run tests to confirm still passing
	6.	Write integration tests for connections to upstream/downstream modules
	7.	Run full test suite before moving to next module

Module build order (tests first for each):

	Phase 1:
	  1. data models / schemas (contract tests)
	  2. data_ingestion
	  3. feature_engineering
	  4. pipeline_transition_engine (deterministic only)
	  5. funded_evolution_engine (deterministic only)
	  6. aggregation_engine
	  7. explainability_logger
	  8. daily engine loop (integration)
	  9. synthetic data generator
	  10. Phase 1 golden test + acceptance test

	Phase 2:
	  1. stochastic layer (Monte Carlo paths)
	  2. rating_engine
	  3. utilisation module (within funded_evolution_engine)
	  4. strategy_interpreter (structured input)
	  5. scenario_engine
	  6. scenario comparison reporting
	  7. property-based invariant tests
	  8. Phase 2 golden test + acceptance test

	Phase 3:
	  1. strategy_interpreter text parsing (LLM-assisted)
	  2. valuation_engine
	  3. sensitivity analysis module
	  4. explainability report generator
	  5. Phase 3 golden test + acceptance test
	  6. performance test suite

⸻

21.11 Test Quality Gates

No PR or phase completion is accepted unless:

	•	all unit tests pass
	•	all integration tests pass
	•	all property-based tests pass (minimum 100 examples per property)
	•	golden file tests match or are explicitly updated with justification
	•	code coverage >= 90% for engine modules
	•	no test uses sleep, network calls, or non-deterministic behaviour without seed
	•	test names describe business behaviour, not implementation details

⸻

22. Feature Backlog: Decision Intelligence & Beyond

Future enhancements grouped into 6 categories: decision intelligence, calibration, portfolio physics, explainability, scenario intelligence, and productization.

⸻

22.1 Decision Intelligence Layer

22.1.1 Strategy optimizer

Instead of only simulating a strategy, allow the engine to search for the best strategy.

Example questions:

	•	What pipeline mix maximizes RORAC?
	•	What mix meets growth targets but keeps downgrade risk below X?
	•	What pricing discipline keeps balances stable if utilisation falls?

Implementation:

optimize:
  objective:
    maximize: portfolio_nim
  constraints:
    max_sector_concentration: 20%
    avg_rating >= BBB-
    capital_usage <= threshold

Techniques: Bayesian optimisation, heuristic search, reinforcement learning.

⸻

22.1.2 Management action simulation

Allow mid-simulation interventions:

	•	Day 60: tighten CRE underwriting
	•	Day 90: raise spread floors 20 bps
	•	Day 120: reduce tenor for leveraged loans

The engine evaluates policy reactions, similar to central bank policy modelling.

⸻

22.1.3 Deal selection engine

From pipeline of 5000 deals, rank which deals to prioritise funding.

Ranking features:

	•	expected margin
	•	capital efficiency
	•	diversification impact
	•	liquidity consumption
	•	sector appetite

Output: Deal Score = margin contribution + diversification benefit - capital cost - rating risk

This becomes a portfolio construction tool.

⸻

22.2 Calibration & Learning

Most simulations fail because parameters are static.

22.2.1 Automatic calibration from historical data

Train transition probabilities from:

	•	historical pipelines
	•	deal close data
	•	portfolio roll-forwards
	•	rating migrations

Learn: stage duration distributions, close probabilities, utilisation patterns, renewal probabilities.

⸻

22.2.2 Behavioural cohort learning

Loans behave differently depending on borrower type. Cluster behaviour into cohorts:

	•	Cohort A: Sponsor LBO loans
	•	Cohort B: SME revolvers
	•	Cohort C: CRE construction

Each cohort has unique evolution dynamics.

⸻

22.2.3 Strategy detection from earnings calls

Extend the strategy interpreter to use LLM classification to detect signals like:

	•	tightening credit
	•	deposit pricing pressure
	•	shifting sector exposure
	•	risk appetite changes

These update simulation parameters automatically.

⸻

22.3 Portfolio Physics (Risk/Finance Realism)

22.3.1 Capital usage (RWA / EC)

Compute Risk Weighted Assets, Economic capital, and leverage exposure. Then allow constraints: capital_limit, liquidity_limit, sector_limit.

This allows the engine to answer: "Growth under capital constraints."

⸻

22.3.2 Liquidity consumption

Track committed lines, draw risk, and liquidity buffers. Especially relevant for revolvers.

Key question: What happens if drawdown spikes in stress?

⸻

22.3.3 Pricing dynamics

Pricing evolves with market spreads, competition, and funding cost.

Model: spread = base_spread + scenario_shift + strategy_floor + rating_adjustment

⸻

22.3.4 Secondary market behaviour

Loans can trade, refinance, or be syndicated. Add events: sell_position, syndicate, refinance. This adds realism for large banks.

⸻

22.4 Explainability & Intelligence Objects

22.4.1 Intelligence object generation

Instead of just outputs, generate structured insights:

IntelligenceObject
type: portfolio_shift
description: CRE exposure fell 4%
driver: strategy tightening + pipeline mix
confidence: 0.82

These objects power dashboards, agent explanations, and decision support.

⸻

22.4.2 Driver attribution

Break down portfolio change into drivers:

	•	+ new originations
	•	- amortisation
	•	- prepayments
	•	+ utilisation increase
	•	+ rating upgrades
	•	- rating downgrades

⸻

22.4.3 Sensitivity analysis

The engine reports contribution breakdown:

	•	Pipeline growth: 42%
	•	Utilisation increase: 28%
	•	Lower prepayments: 19%
	•	Strategy shift: 11%

⸻

22.5 Scenario Intelligence

22.5.1 Reverse stress testing

Instead of "What happens if recession occurs?", ask "What scenario causes portfolio capital to breach limit?" The engine searches for conditions that break constraints.

⸻

22.5.2 Competitive dynamics

Simulate competitors. Example: competitors lower spreads 40bps. Impact on pipeline conversion and margin compression.

⸻

22.5.3 Climate / physical risk scenarios

Add physical risk factors: flood exposure, wildfire exposure, heat stress. Impact on sector rating migration, collateral values, and insurance costs.

⸻

22.6 Productization / Platform Features

22.6.1 Scenario authoring UI

Allow users to create scenarios via sliders or narrative prompts. Example: "Moderate recession with tightening credit standards" -- LLM converts into parameter set.

⸻

22.6.2 Simulation lineage tracking

Track portfolio version, scenario version, strategy version, and rules version. Essential for auditability.

⸻

22.6.3 Parallel simulation engine

Allow 10,000+ paths and multi-scenario runs. Tech options: Ray, Dask, Spark, GPU Monte Carlo.

⸻

22.6.4 Interactive exploration

Users should be able to ask "Why did CRE exposure fall?" and receive an explanation from simulation logs.

⸻

23. Portfolio Intelligence Engine

Every simulation produces decision objects:

Insight
title: Growth target unlikely to be met
driver: Pipeline conversion slowing in leveraged loans
confidence: 0.74
recommended action: Increase pipeline in sponsor finance or loosen approval thresholds

This turns the tool from simulation engine into a decision intelligence system: knowledge operationalised into judgement.

⸻

24. Prioritised Add-On Roadmap

Highest ROI features to build first:

	1.	Strategy interpreter from earnings calls
	2.	Deal prioritization / portfolio construction engine
	3.	Driver attribution / explainability layer
	4.	Historical calibration engine
	5.	Capital & liquidity constraints
