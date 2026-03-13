# Strategic Applications of the Synthetic Bank Capability

**For:** BDI/MGI Leadership | **Author:** Alexander Cannon | **Date:** March 13, 2026

---

## Executive Summary

The Portfolio Evolution Engine — the synthetic bank — was built to solve a specific problem: give BDI's onboarding and automation teams a realistic test harness. But the capability we've built is significantly more valuable than a single test environment. It is a **programmable, configurable, multi-system data generation engine** that can produce bank-shaped data at any scale, for any profile, with temporal dynamics.

This document identifies seven strategic applications beyond the original scope.

---

## Application 1: March Internal Release — Snapshot/Preview Data

**Roadmap item:** "Snapshot/preview data for consistent internal testing" (March 2026 target)

**The synthetic bank IS this deliverable.** It provides:
- Self-consistent data across four source systems
- A stable, reproducible dataset (seed-based determinism)
- Temporal depth (sim_day progression shows how data evolves)
- Already live in Databricks (`bdi_data_201.synthetic_bank`)

**Action:** Declare the March snapshot/preview data target as met. Point all internal testing workflows at the synthetic bank tables.

---

## Application 2: Non-Hosted Client Onboarding Testing

**Problem:** BDI's onboarding workflow for non-hosted clients involves AI-assisted schema mapping to the Banking Common Data Dictionary (CDD). This workflow has never been tested against a realistic, multi-system bank dataset.

**How the synthetic bank helps:**
- The four source-system tables (`crm_pipeline`, `los_underwriting`, `core_funded`, `core_deposits`) are deliberately shaped like raw bank extracts — different schemas, different naming conventions, different granularity
- We can run the CDD mapping engine against these tables as if they were a new client's data
- We can verify that the mapping produces correct canonical output
- We can test the conflict resolution UI with realistic unmapped fields

**Action:** Schedule a dry run of the non-hosted onboarding workflow using the synthetic bank as the "client."

---

## Application 3: Domain Agent Development and Testing

**Problem:** Every domain agent needs real-structured loan data to function. Currently, agents are tested against limited WAL (Western Alliance) data or manually curated samples.

**How the synthetic bank helps:**

| Agent | Data Need | Synthetic Bank Coverage |
|-------|-----------|------------------------|
| **Credit Analytics (EDF-X)** | Obligor financials, loan terms | `core_funded` has 20K loans with rates, ratings, maturities, collateral |
| **RPA** | Pipeline + funded + market data for profitability | `crm_pipeline` + `los_underwriting` + `core_funded` span the full RPA Famous Chart |
| **Portfolio Studio** | Instrument-level data for EC, RORAC, concentration | `core_funded` has all required dimensions (segment, geography, rating, size) |
| **Impairment Studio** | Loan-level data for CECL/IFRS-9 | `core_funded` has origination dates, maturities, ratings, collateral — all CECL inputs |
| **BSM (H2 2026)** | Assets + liabilities for ALM | `core_funded` (assets) + `core_deposits` (liabilities) = the two sides of the balance sheet |

**Key insight:** The synthetic bank provides the **only dataset in BDI** that spans all five domain agents' data requirements simultaneously. This makes it the ideal integration test environment for the Brain Agent's cross-domain orchestration.

**Action:** Set up each domain agent against the synthetic bank and validate end-to-end: Can the Credit Analytics agent answer questions about this portfolio? Can RPA calculate profitability? Can Portfolio Studio run concentration analysis?

---

## Application 4: Entity Resolution Testing (Open Question A3/A5)

**Problem:** Entity resolution across systems is a May target but has no test environment. How do you test whether "Metro Properties LLC" in CRM is the same entity as "Metro Properties" in core banking?

**How the synthetic bank helps:**
- The same borrower appears across CRM, LOS, core banking, and deposits with **known** identity links
- We control the data generation, so we can introduce deliberate variations (name formatting, ID differences) to test resolution quality
- The `CUSTOMER_ID` in deposits maps to `ACCT_NO` in core_funded — this is the ground truth for evaluating entity matching accuracy

**Action:** Use the synthetic bank as the test dataset for the entity resolution engine. Generate a variant with deliberate name/ID noise to stress-test matching algorithms.

---

## Application 5: Summit Demo Data (May 2026)

**Problem:** The Summit demo has three scenarios that need realistic data:
1. **Deal Context Agent** — "Help me prepare for loan committee on this deal"
2. **Production Optimizer** — "Where am I making concessions on margin vs. volume?"
3. **Portfolio Scanner** — "Identify risk/return tradeoffs in my CRE book"

**How the synthetic bank helps:**
- **Deal Context:** Pick any deal from `los_underwriting` — it has borrower, amount, rating, stage, rate, and is linked to the funded book and deposits
- **Production Optimizer:** `core_funded` has 20K loans with rates, segments, and ratings — enough to find real margin/volume tradeoffs at the segment, geography, and RM level
- **Portfolio Scanner:** `core_funded` has CRE loans across 15 states with varying ratings and concentrations — natural risk/return patterns emerge from the simulation

**Key advantage:** The synthetic bank is deterministic. We can guarantee that specific interesting patterns exist in the data for the demo (e.g., a CRE concentration in OH, a downgraded construction portfolio, a profitable C&I segment with low growth).

**Action:** Generate a Summit-specific variant of the synthetic bank seeded to produce the exact patterns needed for the three demo scenarios. Run the simulation for 90 days to build temporal depth.

---

## Application 6: Genie Space Testing

**Problem:** Genie (NL-to-SQL) needs tables with real data to produce meaningful results. Current Genie spaces are limited to single-tenant, single-product data.

**How the synthetic bank helps:**
- Four tables with rich schemas already in Databricks
- Column-level descriptions already applied (Genie uses these for query understanding)
- Realistic data distributions (not all values the same, not random noise)
- Cross-table joins that make sense (loans ↔ deposits via customer ID)

**Example Genie queries the synthetic bank can answer:**
- "Show me all CRE loans in Ohio over $5M with risk rating below 5"
- "What's the total pipeline by segment?"
- "Which RMs have the most deals in underwriting?"
- "What's the average deposit balance for customers with funded loans over $10M?"

**Action:** Create a Genie space over `bdi_data_201.synthetic_bank.*`. Add the column descriptions as Genie instructions. Test with the evaluation framework's 50 prompts.

---

## Application 7: Reusable POC/Demo Data Generation

**Problem:** Every POC, demo, and client workshop needs custom data. Currently this is a manual, one-off exercise.

**How the synthetic data generator helps:**
- **Configurable profiles:** Community bank ($5B), regional ($30B), superregional ($100B), national ($500B+)
- **Configurable segments:** CRE-heavy, C&I-heavy, consumer, specialty, mixed
- **Configurable geography:** Single state, multi-state, national
- **Configurable risk profiles:** Pristine, stressed, realistic
- **Reproducible:** Seed-based, deterministic — same seed always produces same data
- **Fast:** 20K loans + 1.5K pipeline + 15K deposits generated in ~20 seconds

**Use cases:**
- Pre-Summit: "Generate a $15B community bank in the Southeast with heavy CRE concentration for the Wells Fargo follow-up"
- Client workshop: "Generate data that looks like their portfolio profile for the live demo"
- Beta onboarding: "Generate test data matching the client's reported portfolio size and mix before they send real data"

**Action:** Create a CLI wrapper or parameterized notebook that takes a bank profile (size, segment mix, geography) and produces a complete dataset, optionally pushing it to Databricks.

---

## Priority Matrix

| Application | Impact | Effort | Timeline |
|-------------|--------|--------|----------|
| March snapshot data (done) | High | Done | Now |
| Domain agent testing | High | Low | This sprint |
| Genie space setup | High | Low | This sprint |
| Non-hosted onboarding dry run | High | Medium | March |
| Summit demo data | High | Medium | April |
| Entity resolution testing | Medium | Medium | April |
| Reusable POC generator | High | Low | Ongoing |

---

## Recommendation

The synthetic bank should be treated as **BDI platform infrastructure**, not a one-off test tool. It should be:

1. **Maintained** — the daily scheduler keeps it alive, but the engine itself should be iterated as BDI's data model evolves
2. **Extended** — when new domain agents or data sources come online, the synthetic bank should generate corresponding data
3. **Shared** — every pillar team should know it exists and use it for testing
4. **Parameterized** — the data generator should become a service that any team can call to produce custom datasets

The investment in this capability pays compound returns: every new feature, agent, or workflow that needs test data can use it instead of waiting for real client data or hand-crafting samples.
