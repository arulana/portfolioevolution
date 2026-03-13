#!/usr/bin/env python3
"""Generate synthetic bank data for Portfolio Evolution simulation engine.

Produces funded portfolio, pipeline, and deposits for a NY-based community bank
with heavy CRE focus. Uses numpy seed=42 for reproducibility.

Usage:
    python scripts/generate_synthetic_data.py

Output:
    data/sample/funded_portfolio.csv  (~500 rows)
    data/sample/pipeline.csv          (~250 rows)
    data/sample/deposits.csv          (~300 rows)
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_SAMPLE = PROJECT_ROOT / "data" / "sample"
TESTS_FIXTURES = PROJECT_ROOT / "tests" / "fixtures"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED = 42
AS_OF_DATE = "01/01/2026"
MONTH_END = "01/01/2026"

# Segment mix: ~50% CRE, ~25% C&I, ~15% Multifamily, ~10% Other
SEGMENT_WEIGHTS = {"CRE": 0.50, "C&I": 0.25, "Multifamily": 0.15, "Other": 0.10}

# Risk ratings: ~70% pass (1-4), ~20% watch (5-6), ~10% classified (7-9)
# CRE tends slightly higher risk than C&I

# Rate types: ~40% Fixed, ~35% LIBOR/SOFR, ~25% Prime
RATE_TYPE_WEIGHTS = {"Fixed": 0.40, "LIBOR": 0.35, "Prime": 0.25}

# Amort types: ~40% P&I, ~30% I/O, ~20% Bullet, ~10% other
AMORT_WEIGHTS = {"P&I": 0.40, "I.O.": 0.30, "Single Payment at Maturity": 0.30}

# Geography: ~60% NY, ~15% NJ, ~10% CT, ~15% Other
GEO_WEIGHTS = {"NY": 0.60, "NJ": 0.15, "CT": 0.10, "PA": 0.05, "MA": 0.05, "FL": 0.05}

# Pipeline stages (canonical names that stage_crosswalk maps to)
PIPELINE_STAGES = ["Lead", "Underwriting", "Approved", "Documentation", "Closing", "Term Sheet"]
PIPELINE_STAGE_WEIGHTS = [0.20, 0.25, 0.15, 0.15, 0.10, 0.15]

# Borrower name components
BORROWER_PREFIXES = [
    "ABC", "Metro", "Summit", "Park", "Riverside", "Harbor", "Crown", "Elm",
    "Oak", "Pine", "Maple", "Cedar", "Brook", "Lake", "Valley", "Highland",
    "Downtown", "Uptown", "Midtown", "Westside", "Eastside", "Northgate",
]
BORROWER_SUFFIXES = [
    "Properties LLC", "Realty LLC", "Holdings LLC", "Associates LLC",
    "Healthcare Group", "Development Corp", "Investments LLC", "Partners LP",
    "Management LLC", "Capital LLC", "Ventures LLC", "Equity LLC",
    "Limited Partnership", "Inc", "Corp",
]

# RM names
RM_NAMES = [
    "Jay Shah", "Dennis Graham", "Vivek Baid", "Mark Scharfman",
    "Luke Kaufman", "Konstantin Grinberg", "Jeremy Romine", "Brett Bandazian",
]

# Property types by segment
CRE_PROP_TYPES = ["Office", "Retail", "Multifamily", "Mixed Use", "Industrial", "Warehouse", "1-4 Family"]
CANDI_PROP_TYPES = ["Office", "Industrial", "Mixed Use", "Warehouse"]
MULTIFAMILY_PROP_TYPES = ["Multifamily", "1-4 Family"]
OTHER_PROP_TYPES = ["Office", "Retail", "Industrial", "Land"]

# ClassCodeDescriptions by segment
CRE_CLASS_CODES = ["Commercial Real Estate", "CRE secured by 1-4 Family", "Multi-family CRE"]
CANDI_CLASS_CODES = ["C&I CRE", "C&I Secured", "C&I LOC"]
MULTIFAMILY_CLASS_CODES = ["Multi-family CRE", "CRE secured by 1-4 Family"]
OTHER_CLASS_CODES = ["Commercial Real Estate", "C&I CRE"]

# NAICS codes (6-digit)
NAICS_CODES = ["531110", "531120", "531190", "531390", "441310", "423120", "623110", "311919", "447110", "531311"]

# Rating to canonical letter grade
RATING_TO_LETTER = {"1": "AAA", "2": "AA", "3": "A", "4": "BBB", "5": "BB", "6": "B", "7": "CCC", "8": "CC", "9": "D"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fmt_currency(val: float) -> str:
    """Format as $1,234,567.89"""
    return f"${val:,.2f}"


def fmt_date(d: date) -> str:
    """Format as MM/DD/YYYY"""
    return d.strftime("%m/%d/%Y")


def rr_to_group(rr: int) -> str:
    """Map risk rating to RRGroup."""
    if 1 <= rr <= 5:
        return "1 - 5"
    if rr == 6:
        return "6"
    return str(rr)


def sample_lognormal(low: float, high: float, mean_log: float, sigma_log: float, rng: np.random.Generator) -> float:
    """Sample amount from lognormal, clipped to [low, high]."""
    x = rng.lognormal(mean_log, sigma_log)
    return float(np.clip(x, low, high))


# ---------------------------------------------------------------------------
# Funded Portfolio
# ---------------------------------------------------------------------------


def generate_funded_portfolio(rng: np.random.Generator, n: int = 500) -> list[dict]:
    """Generate ~500 funded loan positions."""
    rows = []
    # Lognormal params: target ~$800M-1.2B total for 500 loans (~$1.6-2.4M avg)
    mean_log = 14.0
    sigma_log = 1.0

    for i in range(n):
        acct_no = f"{i + 1:06d}"
        account_number = f"0000{acct_no}"

        # Segment
        seg = rng.choice(list(SEGMENT_WEIGHTS.keys()), p=list(SEGMENT_WEIGHTS.values()))

        # Risk rating (CRE slightly higher risk)
        rr_bucket = rng.choice(
            [(1, 4), (5, 6), (7, 9)],
            p=[0.72 if seg == "C&I" else 0.68, 0.22 if seg == "C&I" else 0.21, 0.06 if seg == "C&I" else 0.11],
        )
        risk_rating = int(rng.integers(rr_bucket[0], rr_bucket[1] + 1))

        # Amounts
        committed = sample_lognormal(100_000, 50_000_000, mean_log, sigma_log, rng)
        utilisation = float(rng.uniform(0.6, 1.0))
        funded = committed * utilisation
        undrawn = max(committed - funded, 0)
        calc_avail = undrawn

        # Rate type
        rate_type = rng.choice(list(RATE_TYPE_WEIGHTS.keys()), p=list(RATE_TYPE_WEIGHTS.values()))
        rate_code = {"Fixed": "FIXED", "LIBOR": "LIBOR", "Prime": "Prime"}[rate_type]
        rate_over_split = float(rng.uniform(3.5, 7.5))
        rate_floor = float(rng.uniform(0, 5)) if rate_type == "LIBOR" else 0
        rate_adj_basis = float(rng.uniform(-0.5, 5)) if rate_type != "Fixed" else 0

        # Amort
        amort = rng.choice(list(AMORT_WEIGHTS.keys()), p=list(AMORT_WEIGHTS.values()))
        if amort == "P&I":
            payment_type = "P&I"
        elif amort == "I.O.":
            payment_type = "I.O."
        else:
            payment_type = "Interest"
        payment_freq = "Single Payment at Maturity" if amort == "Single Payment at Maturity" else "Monthly"

        # Geography
        geo = rng.choice(list(GEO_WEIGHTS.keys()), p=list(GEO_WEIGHTS.values()))

        # Dates
        orig_year = int(rng.integers(2018, 2026))
        orig_month = int(rng.integers(1, 13))
        orig_day = int(rng.integers(1, 29))
        orig_date = date(orig_year, orig_month, orig_day)
        tenor_years = int(rng.integers(3, 11))
        mat_date = date(orig_year + tenor_years, orig_month, min(orig_day, 28))
        renewal_date = orig_date

        # Borrower
        prefix = rng.choice(BORROWER_PREFIXES)
        suffix = rng.choice(BORROWER_SUFFIXES)
        borrower = f"{prefix} {suffix}"

        # Property / class
        if seg == "CRE":
            prop_type = rng.choice(CRE_PROP_TYPES)
            class_desc = rng.choice(CRE_CLASS_CODES)
        elif seg == "C&I":
            prop_type = rng.choice(CANDI_PROP_TYPES)
            class_desc = rng.choice(CANDI_CLASS_CODES)
        elif seg == "Multifamily":
            prop_type = rng.choice(MULTIFAMILY_PROP_TYPES)
            class_desc = rng.choice(MULTIFAMILY_CLASS_CODES)
        else:
            prop_type = rng.choice(OTHER_PROP_TYPES)
            class_desc = rng.choice(OTHER_CLASS_CODES)

        prop_type_code = {"Office": 21, "Retail": 25, "Multifamily": 18, "Mixed Use": 22, "Industrial": 16,
                          "Warehouse": 26, "1-4 Family": 1, "Land": 17, "Nursing Home": 20}.get(prop_type, 22)

        naics = rng.choice(NAICS_CODES)
        report_group = "Real Estate and Rental and Leasing" if seg in ("CRE", "Multifamily") else rng.choice(
            ["Retail", "Manufacturing", "Health Care and Social Assistance", "Wholesale Trade"]
        )

        resp_code = str(int(rng.integers(200, 290)))
        resp_name = rng.choice(RM_NAMES)
        team = "CRE" if seg in ("CRE", "Multifamily") else "C&I"
        rel_name = resp_name

        # Def fees, interest (small)
        earned_def = float(rng.uniform(0, 50_000))
        earn_interest = float(rng.uniform(-500, 5_000))
        rbc = f"{committed:,.2f}"
        fhlb = 0
        owner_occ = 1 if rng.random() < 0.2 else 0
        concentration_group = prop_type if seg == "CRE" else report_group
        mgmt_group = str(int(rng.integers(40, 60)))
        io_flag = 1 if "Interest" in payment_type or "I.O." in payment_type else 0
        io_pick = "TRUE" if io_flag else 0
        bhg_flag = 0
        sort_order = int(rng.integers(1, 30))
        renewed = 1 if rng.random() < 0.15 else 0
        tdr = "FALSE"
        snc = "FALSE"
        accrual = "FALSE"

        coll_code = "Real Estate 1st Mortgage"
        coll_code_num = 16
        purpose_code = rng.choice(["140", "160", "170", "180", "110"])
        purpose_group = rng.choice(["1-4 Fam 1st lien", "Non Owner Occupied", "Secured by Multifamily residential", "Owner Occupied"])

        row = {
            "AcctNO": acct_no,
            "Borrower Name": borrower,
            "Account Number": account_number,
            "ClassGroup": seg,
            "PropTypeDesc": prop_type,
            "ClassCodeDescriptions": class_desc,
            "Naics Code": naics,
            "ReportGroup": report_group,
            "STAbbr": geo,
            "CurrBal": fmt_currency(funded),
            "CMT": fmt_currency(committed),
            "CalcAvail": fmt_currency(calc_avail),
            "Max Credit Line": fmt_currency(committed),
            "Rate Over Split": rate_over_split,
            "Loan Rate Code": rate_code,
            "Interest Rate Floor": rate_floor,
            "Rate Adj Basis": rate_adj_basis,
            "Original Note Date": fmt_date(orig_date),
            "Maturity Date": fmt_date(mat_date),
            "Renewal Date": fmt_date(renewal_date),
            "Payment Frequency": payment_freq,
            "Payment Type": payment_type,
            "CollCodeDescription": coll_code,
            "Collateral Code": coll_code_num,
            "Property Type Code": prop_type_code,
            "Owner Occupied Code": owner_occ,
            "Purpose Code": purpose_code,
            "Purpose Group": purpose_group,
            "Risk Rating": risk_rating,
            "RRGroup": rr_to_group(risk_rating),
            "TDR": tdr,
            "SNC": snc,
            "Accrual": accrual,
            "Resp Code": resp_code,
            "RespName": resp_name,
            "Team": team,
            "Rel Name": rel_name,
            "MonthEnd": MONTH_END,
            "Renewed": renewed,
            "Current Earned Def fees": fmt_currency(earned_def),
            "Earn Interest Bal": fmt_currency(earn_interest),
            "RBC": rbc,
            "Fhlb Reporting Code": fhlb,
            "ConcentrationGroup": concentration_group,
            "MgmtGroup": mgmt_group,
            "IOFlag": io_flag,
            "IOPickFlag": io_pick,
            "BHGFlag": bhg_flag,
            "SortOrder": sort_order,
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def generate_pipeline(rng: np.random.Generator, n: int = 250, borrower_pool: list[str] | None = None) -> list[dict]:
    """Generate ~250 pipeline deals."""
    rows = []
    if borrower_pool is None:
        borrower_pool = []
        for _ in range(100):
            prefix = rng.choice(BORROWER_PREFIXES)
            suffix = rng.choice(BORROWER_SUFFIXES)
            borrower_pool.append(f"{prefix} {suffix}")

    mean_log = 14.2
    sigma_log = 1.3

    for i in range(n):
        opp_id = f"OPP-{i + 1:05d}"
        borrower = rng.choice(borrower_pool)
        stage = rng.choice(PIPELINE_STAGES, p=PIPELINE_STAGE_WEIGHTS)
        amount = sample_lognormal(100_000, 35_000_000, mean_log, sigma_log, rng)
        close_prob = float(rng.uniform(0.2, 0.95))
        seg = rng.choice(list(SEGMENT_WEIGHTS.keys()), p=list(SEGMENT_WEIGHTS.values()))
        prop_type = rng.choice(CRE_PROP_TYPES + CANDI_PROP_TYPES)
        naics = rng.choice(NAICS_CODES)
        rate_type = rng.choice(["Fixed", "LIBOR", "SOFR", "Prime"], p=[0.4, 0.2, 0.15, 0.25])
        expected_rate = float(rng.uniform(4.0, 8.0))
        close_date = date(2026, 1, 1) + timedelta(days=int(rng.integers(30, 365)))
        risk_rating = int(rng.integers(1, 7))
        rm_code = str(int(rng.integers(200, 290)))
        rm_name = rng.choice(RM_NAMES)
        state = rng.choice(list(GEO_WEIGHTS.keys()), p=list(GEO_WEIGHTS.values()))
        owner_occ = 1 if rng.random() < 0.25 else 0
        product_class = rng.choice(["Commercial Real Estate", "Multi-family CRE", "C&I CRE", "CRE secured by 1-4 Family"])

        row = {
            "OPP_ID": opp_id,
            "BORROWER_NAME": borrower,
            "STAGE": stage,
            "EXPECTED_AMOUNT": round(amount, 2),
            "CLOSE_PROB": round(close_prob, 2),
            "SEGMENT": seg,
            "PROPERTY_TYPE": prop_type,
            "NAICS_CODE": naics,
            "RATE_TYPE": rate_type,
            "EXPECTED_RATE": round(expected_rate, 2),
            "EXPECTED_CLOSE_DATE": close_date.isoformat(),
            "RISK_RATING": risk_rating,
            "RM_CODE": rm_code,
            "RM_NAME": rm_name,
            "STATE": state,
            "OWNER_OCCUPIED": owner_occ,
            "PRODUCT_CLASS": product_class,
            "AS_OF_DATE": "2026-01-01",
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------


def generate_deposits(
    rng: np.random.Generator,
    n: int = 300,
    counterparty_ids: list[str] | None = None,
) -> list[dict]:
    """Generate ~300 deposit accounts linked to funded counterparties."""
    rows = []
    if counterparty_ids is None:
        counterparty_ids = [f"CPTY-{i:04d}" for i in range(100)]

    account_types = ["Checking", "Commercial Checking", "Operating", "CD", "Savings", "Money Market"]
    account_type_weights = [0.35, 0.25, 0.15, 0.15, 0.08, 0.02]
    liquidity_classes = ["Stable", "Operational", "Non-Operational", "Rate Sensitive"]
    liquidity_weights = [0.4, 0.3, 0.2, 0.1]
    segments = ["CRE", "C&I", "Commercial"]
    industries = ["Real Estate", "Retail", "Manufacturing", "Healthcare"]

    for i in range(n):
        acct_id = f"DEP-{i + 1:06d}"
        cust_id = rng.choice(counterparty_ids)
        acct_type = rng.choice(account_types, p=account_type_weights)
        current_bal = float(rng.lognormal(10, 2.5))
        current_bal = min(current_bal, 50_000_000)
        avg_bal = current_bal * float(rng.uniform(0.85, 1.05))
        int_rate = float(rng.uniform(0.01, 0.055))
        rate_type = "fixed" if rng.random() < 0.7 else "floating"
        benchmark = "Fed Funds" if rate_type == "floating" else ""
        deposit_beta = float(rng.uniform(0.1, 0.6))
        open_date = (date(2020, 1, 1) + timedelta(days=int(rng.integers(0, 1800)))).isoformat()
        liquidity = rng.choice(liquidity_classes, p=liquidity_weights)
        segment = rng.choice(segments)
        industry = rng.choice(industries)
        state = rng.choice(list(GEO_WEIGHTS.keys()), p=list(GEO_WEIGHTS.values()))
        branch_code = f"BR{rng.integers(1, 20):02d}"
        product_bundle = "Standard" if rng.random() < 0.7 else "Premium"
        linked_loans = ""

        row = {
            "ACCOUNT_ID": acct_id,
            "CUSTOMER_ID": cust_id,
            "ACCOUNT_TYPE": acct_type,
            "CURRENT_BAL": round(current_bal, 2),
            "AVG_BAL_30D": round(avg_bal, 2),
            "INT_RATE": round(int_rate, 4),
            "RATE_TYPE": rate_type,
            "BENCHMARK": benchmark,
            "DEPOSIT_BETA": round(deposit_beta, 2),
            "OPEN_DATE": open_date,
            "LIQUIDITY_CLASS": liquidity,
            "SEGMENT": segment,
            "INDUSTRY": industry,
            "STATE": state,
            "BRANCH_CODE": branch_code,
            "PRODUCT_BUNDLE": product_bundle,
            "LINKED_LOAN_IDS": linked_loans,
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Test Fixtures (canonical InstrumentPosition format)
# ---------------------------------------------------------------------------


def build_canonical_funded(r: dict) -> dict:
    """Convert funded source row to canonical InstrumentPosition dict."""
    cmt = float(r["CMT"].replace("$", "").replace(",", ""))
    curr = float(r["CurrBal"].replace("$", "").replace(",", ""))
    orig = datetime.strptime(r["Original Note Date"], "%m/%d/%Y").date()
    mat = datetime.strptime(r["Maturity Date"], "%m/%d/%Y").date()
    seg_raw = r["ClassGroup"]
    seg_canonical = "cre" if seg_raw in ("CRE", "Multifamily") else "c_and_i" if seg_raw == "C&I" else "other"
    rate_code = r["Loan Rate Code"]
    coupon_type = "fixed" if rate_code in ("FIXED", "Fixed", "FXD") else "floating"

    return {
        "instrument_id": r["AcctNO"],
        "counterparty_id": r["AcctNO"],
        "counterparty_name": r["Borrower Name"],
        "facility_id": r["Account Number"],
        "position_type": "funded",
        "segment": seg_canonical,
        "subsegment": r["PropTypeDesc"].lower().replace(" ", "_").replace("-", "_"),
        "committed_amount": cmt,
        "funded_amount": curr,
        "coupon_type": coupon_type,
        "coupon_rate": r["Rate Over Split"] / 100,
        "origination_date": orig.isoformat(),
        "maturity_date": mat.isoformat(),
        "internal_rating_numeric": r["Risk Rating"],
        "internal_rating": RATING_TO_LETTER.get(str(r["Risk Rating"]), "BBB"),
        "as_of_date": "2026-01-01",
    }


def build_canonical_pipeline(r: dict) -> dict:
    """Convert pipeline source row to canonical InstrumentPosition dict."""
    close_d = datetime.fromisoformat(r["EXPECTED_CLOSE_DATE"]).date()
    seg_raw = r["SEGMENT"]
    seg_canonical = "cre" if seg_raw in ("CRE", "Multifamily") else "c_and_i" if seg_raw == "C&I" else "other"
    coupon_type = "fixed" if r["RATE_TYPE"] == "Fixed" else "floating"
    stage_canonical = r["STAGE"].lower().replace(" ", "_")
    if stage_canonical == "term_sheet":
        stage_canonical = "approved"

    return {
        "instrument_id": r["OPP_ID"],
        "counterparty_id": r["OPP_ID"],
        "counterparty_name": r["BORROWER_NAME"],
        "position_type": "pipeline",
        "segment": seg_canonical,
        "committed_amount": r["EXPECTED_AMOUNT"],
        "funded_amount": 0.0,
        "coupon_type": coupon_type,
        "coupon_rate": r["EXPECTED_RATE"] / 100,
        "pipeline_stage": stage_canonical,
        "close_probability": r["CLOSE_PROB"],
        "expected_close_date": close_d.isoformat(),
        "internal_rating_numeric": r["RISK_RATING"],
        "internal_rating": RATING_TO_LETTER.get(str(r["RISK_RATING"]), "BBB"),
        "as_of_date": "2026-01-01",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    rng = np.random.default_rng(SEED)

    DATA_SAMPLE.mkdir(parents=True, exist_ok=True)
    TESTS_FIXTURES.mkdir(parents=True, exist_ok=True)

    # 1. Funded portfolio
    funded = generate_funded_portfolio(rng, n=500)
    funded_path = DATA_SAMPLE / "funded_portfolio.csv"
    with open(funded_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=funded[0].keys())
        writer.writeheader()
        writer.writerows(funded)
    total_committed = sum(float(r["CMT"].replace("$", "").replace(",", "")) for r in funded)
    print(f"Wrote {funded_path} ({len(funded)} rows, total committed ~${total_committed/1e9:.2f}B)")

    # 2. Pipeline
    borrower_pool = list({r["Borrower Name"] for r in funded[:200]})
    pipeline = generate_pipeline(rng, n=250, borrower_pool=borrower_pool)
    pipeline_path = DATA_SAMPLE / "pipeline.csv"
    with open(pipeline_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=pipeline[0].keys())
        writer.writeheader()
        writer.writerows(pipeline)
    print(f"Wrote {pipeline_path} ({len(pipeline)} rows)")

    # 3. Deposits
    cpty_ids = [r["AcctNO"] for r in funded[:150]]
    deposits = generate_deposits(rng, n=300, counterparty_ids=cpty_ids)
    deposits_path = DATA_SAMPLE / "deposits.csv"
    with open(deposits_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=deposits[0].keys())
        writer.writeheader()
        writer.writerows(deposits)
    print(f"Wrote {deposits_path} ({len(deposits)} rows)")

    # 4. Test fixtures
    fixture_funded = [build_canonical_funded(r) for r in funded[:10]]
    fixture_pipeline = [build_canonical_pipeline(r) for r in pipeline[:5]]

    with open(TESTS_FIXTURES / "sample_funded_portfolio.json", "w", encoding="utf-8") as f:
        json.dump(fixture_funded, f, indent=2)
    print(f"Wrote {TESTS_FIXTURES / 'sample_funded_portfolio.json'} (10 positions)")

    with open(TESTS_FIXTURES / "sample_pipeline.json", "w", encoding="utf-8") as f:
        json.dump(fixture_pipeline, f, indent=2)
    print(f"Wrote {TESTS_FIXTURES / 'sample_pipeline.json'} (5 deals)")

    print("Done.")


if __name__ == "__main__":
    main()
