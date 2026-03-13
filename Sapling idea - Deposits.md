Below is a working spec to extend the loan-centric portfolio simulator into a bank balance-sheet simulator by adding deposits.

⸻

Spec: Deposit Layer — From Credit Portfolio Simulator to Bank Balance Sheet Simulator

⸻

1. Purpose

Add three objects that complete a full bank digital twin: assets, liabilities, and capital. These fit the BDI intelligence object model already in place.

To extend the loan-centric portfolio simulator into a bank balance-sheet simulator that includes deposits, you need:

	1.	Deposit objects (data model)
	2.	Deposit behaviour physics (evolution rules)
	3.	Pipeline linkage between loans and deposits

This is an incremental plan that keeps the existing architecture intact.

⸻

2. Extend the Object Model

Right now the core object is:

	InstrumentPosition → loans / facilities

Introduce two additional entity types plus a pipeline extension.

⸻

2.1 Deposit Account Object

DepositPosition

	deposit_id: string
	counterparty_id: string
	relationship_id: string|null

	deposit_type: enum[
	  operating,
	  corporate_transaction,
	  escrow,
	  term_deposit,
	  savings,
	  retail_checking,
	  sweep,
	  brokered
	]

	segment: string
	industry: string|null
	geography: string|null
	currency: string

	# balances
	current_balance: float
	average_balance_30d: float|null
	committed_operating_balance: float|null

	# pricing
	interest_rate: float
	rate_type: enum[fixed, floating]
	benchmark: string|null
	spread: float|null
	fee_offset: float|null

	# behavioural
	beta: float
	stickiness_score: float
	decay_half_life_days: int|null
	withdrawal_probability: float|null

	# lifecycle
	origination_date: date
	expected_duration_days: int|null
	linked_loan_ids: list[string]|null

	# liquidity classification
	liquidity_category: enum[
	  stable_operational,
	  non_operational,
	  rate_sensitive,
	  volatile,
	  brokered
	]

	# risk
	deposit_runoff_score: float|null

	# metadata
	source: string
	as_of_date: date

Key idea: deposits are not contracts like loans — they are behavioural balances.

⸻

2.2 Relationship Object

To properly connect loans and deposits introduce a relationship layer.

BankRelationship

	relationship_id: string
	counterparty_id: string
	segment: string
	relationship_manager: string|null

	primary_product: enum[credit, deposits, treasury, mixed]

	credit_facilities: list[string]
	deposit_accounts: list[string]

	cross_sell_score: float
	deposit_attachment_ratio: float

This allows:

	•	deposit expectations at loan origination
	•	cross-sell modeling
	•	relationship-level balance behaviour

⸻

2.3 Deposit Proposal in Pipeline

Extend pipeline objects to include deposit expectations.

Add to pipeline schema:

	deposit_attachment_expected: bool
	expected_operating_balance: float|null
	expected_term_deposit_balance: float|null
	deposit_cross_sell_probability: float
	deposit_beta_expected: float|null

Example: a new corporate revolver might include:

	Loan commitment:          $50M
	Expected operating deposits: $8M
	Expected term deposit:       $3M

This lets the engine generate deposits when the loan books.

⸻

3. Extend Pipeline Simulation

The pipeline simulation should generate two outputs:

	1.	loan origination
	2.	deposit capture

⸻

3.1 At Funding Event

When a pipeline loan becomes funded:

	pipeline deal
	     ↓
	funded loan
	     ↓
	expected deposit creation

Deposit creation logic:

	if deposit_attachment_expected:
	   deposit_amount = expected_operating_balance × draw_probability
	   create DepositPosition

Parameters that affect capture:

	•	borrower segment
	•	relationship depth
	•	treasury service offering
	•	pricing competitiveness
	•	strategy focus on deposits

⸻

3.2 Deposit Capture Probability

Formula:

	deposit_capture_prob =
	   base_prob
	 × relationship_factor
	 × segment_factor
	 × treasury_product_presence
	 × strategy_multiplier

Example capture rates:

	Segment             Capture probability
	Middle market       70%
	Sponsor finance     35%
	Large corporate     55%

⸻

4. Deposit Behaviour Simulation

Deposits evolve differently than loans.

Simulate:

	•	inflow
	•	runoff
	•	rate sensitivity
	•	client activity
	•	competitive pressure

⸻

4.1 Daily Deposit Balance Evolution

Model:

	balance(t+1) =
	  balance(t)
	  + inflow
	  - withdrawals
	  - decay

Components:

Base decay:

	decay_rate = 1 / half_life

Rate-sensitive withdrawals:

	withdrawal_probability =
	   base
	 + rate_gap × beta

Where:

	rate_gap = market_rate - deposit_rate

⸻

4.2 Utilisation Linkage

For operating deposits linked to credit lines:

	deposit_balance ∝ loan_utilisation

Example:

	operating_balance = utilisation × operating_balance_ratio

⸻

4.3 Scenario Sensitivity

Deposits respond to macro scenarios.

	Scenario              Effect
	Rate spike            higher runoff
	Recession             balances fall with revenue
	Credit tightening     deposits increase (precautionary cash)

Scenario modifiers:

	deposit_runoff_multiplier
	deposit_beta_shift
	operating_balance_multiplier

⸻

5. Liquidity Metrics

Deposits matter because of funding and liquidity.

⸻

5.1 Loan-to-Deposit Ratio

	LDR = funded_loans / total_deposits

Track evolution over time.

⸻

5.2 Deposit Stability

Compute:

	•	stable deposits
	•	volatile deposits

	stable_deposits = operational + relationship_deposits

⸻

5.3 Liquidity Coverage Proxy

Simplified metric:

	LCR_proxy = stable_deposits / stressed_outflows

⸻

6. Pricing Dynamics

Deposits compete with market rates. Model deposit pricing.

⸻

6.1 Deposit Rate Adjustment

Formula:

	deposit_rate = benchmark_rate × beta

Example betas:

	Deposit type           Beta
	Retail                 0.25
	Operating corporate    0.35
	Rate sensitive         0.75
	Brokered               0.95

⸻

6.2 Strategy Effects

Strategy signals:

	•	grow deposits
	•	defend deposits
	•	allow runoff

Modifiers:

	deposit_rate_floor_shift
	deposit_beta_shift
	deposit_capture_multiplier

⸻

7. Portfolio Outputs

Extend reporting.

⸻

7.1 Balance Sheet View

	Metric                    Description
	Total deposits            all deposit balances
	Operating deposits        relationship balances
	Term deposits             fixed deposits
	Brokered deposits         wholesale
	Loan-to-deposit ratio     funding balance
	Deposit beta              pricing sensitivity

⸻

7.2 Cross-Sell Metrics

Track:

	deposit_to_loan_ratio

Segment view:

	Segment              Ratio
	MM corporate         0.25
	Sponsor finance      0.10

⸻

8. Strategy Extensions

The strategy interpreter should add deposit signals.

⸻

8.1 Example — Growth Signal

Statement: "We are prioritizing operating deposit growth with commercial clients."

Translate to:

	deposit_capture_multiplier: 1.25
	operating_balance_ratio: +10%
	deposit_pricing_floor_shift: +10bps

⸻

8.2 Example — Runoff Signal

Statement: "We are comfortable letting rate-sensitive deposits run off."

Translate to:

	deposit_beta_shift: +0.15
	deposit_capture_multiplier: 0.85

⸻

9. Simulation Engine Changes

Add one new engine module.

⸻

9.1 New Module

	deposit_evolution_engine

Pipeline now produces:

	pipeline
	  ↓
	loan funding
	  ↓
	deposit creation

Daily loop becomes:

	pipeline step
	loan evolution
	deposit evolution
	rating migration
	valuation
	aggregation

⸻

10. UI Additions

Extend operator UI.

⸻

10.1 Deposits Tab

Charts:

	•	deposits balance
	•	loan-to-deposit ratio
	•	deposit runoff
	•	deposit beta
	•	deposit capture rate

⸻

10.2 Pipeline View

Add columns:

	expected_operating_deposits
	expected_term_deposits
	deposit_capture_probability

⸻

10.3 Strategy UI

Add controls:

	•	Deposit growth appetite
	•	Deposit pricing aggressiveness
	•	Deposit beta tolerance

⸻

11. Backlog Features for Deposits

⸻

11.1 Deposit Capture Engine

Goal: generate deposits from loan origination.

Acceptance:

	•	pipeline deals create deposit accounts
	•	deposit balance linked to loan relationship
	•	capture probability configurable

⸻

11.2 Deposit Behaviour Model

Goal: simulate daily deposit evolution.

Acceptance:

	•	decay
	•	rate sensitivity
	•	scenario modifiers
	•	relationship link to loans

⸻

11.3 Deposit Pricing Model

Goal: simulate deposit interest rates.

Acceptance:

	•	beta model
	•	strategy adjustments
	•	macro scenario effects

⸻

11.4 Liquidity Metrics

Goal: compute liquidity indicators.

Acceptance:

	•	LDR
	•	stable deposits
	•	runoff risk
	•	concentration

⸻

12. Why This Matters

Without deposits you simulate asset growth. With deposits you simulate balance sheet dynamics.

This unlocks questions like:

	•	Can loan growth be funded by deposits?
	•	What deposit capture is needed for pipeline growth?
	•	How does rate competition affect funding costs?
	•	What happens to liquidity under stress?

This turns the model from:

	credit portfolio simulator

into:

	bank balance sheet simulator
