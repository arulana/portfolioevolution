#!/usr/bin/env python3
"""Generate synthetic bank data for a US superregional bank ($50-200B assets).

Produces funded portfolio, pipeline, and deposits calibrated to industry
benchmarks from FDIC call reports, MBA origination data, and peer institutions
(KeyBank, M&T, Citizens, Regions, Huntington).

Usage:
    python scripts/generate_synthetic_data.py

Output:
    data/sample/funded_portfolio.csv  (~20,000 rows, ~$45B funded)
    data/sample/pipeline.csv          (~1,500 rows)
    data/sample/deposits.csv          (~15,000 rows, ~$56B)
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
# Constants — Superregional Bank Profile
# ---------------------------------------------------------------------------

SEED = 42
AS_OF_DATE = "01/01/2026"
MONTH_END = "01/01/2026"

# Segment mix: C&I dominant (48%), CRE (28%), Multifamily (12%), Construction (7%), Specialty (5%)
SEGMENT_WEIGHTS = {
    "C&I": 0.48,
    "CRE": 0.28,
    "Multifamily": 0.12,
    "Construction": 0.07,
    "Specialty": 0.05,
}

# Deal size parameters by segment (lognormal mean_log, sigma_log, min, max)
DEAL_SIZE_PARAMS = {
    "C&I":          {"mean_log": 14.1, "sigma_log": 1.2, "min": 100_000, "max": 75_000_000},
    "CRE":          {"mean_log": 14.8, "sigma_log": 1.1, "min": 250_000, "max": 150_000_000},
    "Multifamily":  {"mean_log": 16.0, "sigma_log": 0.9, "min": 500_000, "max": 200_000_000},
    "Construction": {"mean_log": 15.2, "sigma_log": 1.0, "min": 250_000, "max": 100_000_000},
    "Specialty":    {"mean_log": 14.9, "sigma_log": 1.1, "min": 200_000, "max": 80_000_000},
}

# Risk ratings: ~70% pass (1-4), ~20% watch (5-6), ~10% classified (7-9)
# Segment-specific skews
RATING_DISTRIBUTIONS = {
    "C&I":          {"pass": 0.72, "watch": 0.20, "classified": 0.08},
    "CRE":          {"pass": 0.68, "watch": 0.21, "classified": 0.11},
    "Multifamily":  {"pass": 0.75, "watch": 0.18, "classified": 0.07},
    "Construction": {"pass": 0.60, "watch": 0.25, "classified": 0.15},
    "Specialty":    {"pass": 0.70, "watch": 0.22, "classified": 0.08},
}

# Rate types
RATE_TYPE_WEIGHTS = {"Fixed": 0.35, "SOFR": 0.40, "Prime": 0.25}

# Amort types by segment
AMORT_WEIGHTS = {
    "C&I":          {"P&I": 0.35, "I.O.": 0.25, "Single Payment at Maturity": 0.20, "Revolving": 0.20},
    "CRE":          {"P&I": 0.45, "I.O.": 0.35, "Single Payment at Maturity": 0.15, "Revolving": 0.05},
    "Multifamily":  {"P&I": 0.55, "I.O.": 0.30, "Single Payment at Maturity": 0.10, "Revolving": 0.05},
    "Construction": {"P&I": 0.10, "I.O.": 0.60, "Single Payment at Maturity": 0.25, "Revolving": 0.05},
    "Specialty":    {"P&I": 0.40, "I.O.": 0.30, "Single Payment at Maturity": 0.20, "Revolving": 0.10},
}

# Tenor (years) by segment — min, max for uniform draw
TENOR_RANGES = {
    "C&I":          (2, 7),
    "CRE":          (5, 10),
    "Multifamily":  (5, 12),
    "Construction": (1, 4),
    "Specialty":    (3, 8),
}

# Geography: 15-state superregional footprint
GEO_WEIGHTS = {
    "OH": 0.14, "PA": 0.12, "NY": 0.10, "MI": 0.09, "IN": 0.07,
    "IL": 0.07, "NJ": 0.06, "CT": 0.05, "MA": 0.05, "WI": 0.04,
    "MN": 0.04, "FL": 0.06, "NC": 0.04, "VA": 0.04, "TX": 0.03,
}

# Pipeline stages with steady-state distribution
PIPELINE_STAGES = ["Lead", "Term Sheet", "Underwriting", "Approved", "Documentation", "Closing"]
PIPELINE_STAGE_WEIGHTS = [0.35, 0.20, 0.20, 0.10, 0.10, 0.05]

# Expanded borrower name components
BORROWER_PREFIXES = [
    "ABC", "Metro", "Summit", "Park", "Riverside", "Harbor", "Crown", "Elm",
    "Oak", "Pine", "Maple", "Cedar", "Brook", "Lake", "Valley", "Highland",
    "Downtown", "Uptown", "Midtown", "Westside", "Eastside", "Northgate",
    "Capital", "Heritage", "Patriot", "Eagle", "Liberty", "Columbia",
    "Central", "Lakewood", "Fairview", "Greenfield", "Brookfield", "Stonebridge",
    "Westfield", "Eastwood", "Ridgeview", "Hillcrest", "Clearwater", "Bayshore",
    "Pinnacle", "Cornerstone", "Keystone", "Landmark", "Gateway", "Crossroads",
    "Premier", "National", "Atlantic", "Pacific", "Continental", "Evergreen",
    "Silverstone", "Ironwood", "Copper", "Sterling", "Golden", "Diamond",
    "Phoenix", "Falcon", "Cardinal", "Meridian", "Zenith", "Apex",
    "Bridgewater", "Canterbury", "Devonshire", "Wellington", "Kensington",
    "Montgomery", "Hamilton", "Jefferson", "Franklin", "Madison",
]
BORROWER_SUFFIXES = [
    "Properties LLC", "Realty LLC", "Holdings LLC", "Associates LLC",
    "Healthcare Group", "Development Corp", "Investments LLC", "Partners LP",
    "Management LLC", "Capital LLC", "Ventures LLC", "Equity LLC",
    "Limited Partnership", "Inc", "Corp", "Group LLC", "Fund LP",
    "Real Estate Trust", "Advisors LLC", "Solutions Inc", "Services Corp",
    "Industries Inc", "Technologies LLC", "Medical Group", "Logistics Corp",
    "Manufacturing Inc", "Energy LLC", "Financial Services", "Insurance Group",
    "Construction Co", "Engineering LLC", "Retail Partners", "Hospitality Group",
    "Senior Living LLC", "Student Housing LP", "Self Storage LLC",
]

# RM names — 40+ across 8 teams
RM_NAMES = [
    "Jay Shah", "Dennis Graham", "Vivek Baid", "Mark Scharfman",
    "Luke Kaufman", "Konstantin Grinberg", "Jeremy Romine", "Brett Bandazian",
    "Sarah Chen", "Michael Torres", "Rachel Goldman", "David Kim",
    "Jennifer Walsh", "Robert Martinez", "Amanda Foster", "Chris Nguyen",
    "Patricia O'Brien", "Thomas Wright", "Michelle Lee", "Andrew Cohen",
    "Katherine Murphy", "Brian Sullivan", "Nicole Anderson", "Steven Park",
    "Laura Bennett", "James O'Malley", "Diana Vasquez", "Eric Johnson",
    "Samantha Reed", "Daniel Harris", "Olivia Thompson", "Kevin Brown",
    "Victoria Adams", "Gregory Miller", "Rebecca Davis", "Nathan White",
    "Stephanie Clark", "Christopher Hall", "Maria Rodriguez", "Justin Taylor",
]

TEAMS = ["CRE East", "CRE West", "CRE Midwest", "C&I East", "C&I West",
         "C&I Midwest", "Construction", "Specialty Finance"]

# Property types by segment
CRE_PROP_TYPES = ["Office", "Retail", "Industrial", "Warehouse", "Mixed Use", "1-4 Family", "Land"]
MF_PROP_TYPES = ["Multifamily", "Student Housing", "Senior Living", "Affordable Housing"]
CANDI_PROP_TYPES = ["Office", "Industrial", "Warehouse", "Mixed Use", "None"]
CONSTRUCT_PROP_TYPES = ["Office", "Retail", "Multifamily", "Industrial", "Mixed Use", "Land"]
SPECIALTY_PROP_TYPES = ["Healthcare", "Hospitality", "Self Storage", "Data Center", "Life Sciences"]

# Class codes by segment
CRE_CLASS_CODES = ["Commercial Real Estate", "CRE secured by 1-4 Family", "Multi-family CRE",
                   "CRE Non-Owner Occupied", "CRE Income Producing"]
CANDI_CLASS_CODES = ["C&I CRE", "C&I Secured", "C&I LOC", "C&I Unsecured", "C&I ABL"]
MF_CLASS_CODES = ["Multi-family CRE", "CRE secured by 1-4 Family", "Affordable Housing"]
CONSTRUCT_CLASS_CODES = ["Construction - Commercial", "Construction - Residential", "Land Development"]
SPECIALTY_CLASS_CODES = ["Healthcare Finance", "Hospitality Finance", "Specialty CRE"]

# NAICS codes (6-digit) — expanded for C&I diversity
NAICS_CODES = {
    "CRE": ["531110", "531120", "531190", "531390", "531311"],
    "C&I": ["441310", "423120", "311919", "447110", "332710", "336111", "511210",
            "541511", "621111", "721110", "561720", "238220", "424410", "325411"],
    "Multifamily": ["531110", "531311", "623110", "624120"],
    "Construction": ["236220", "236210", "236115", "237310", "238910"],
    "Specialty": ["623110", "721110", "531130", "518210", "541711"],
}

REPORT_GROUPS = {
    "CRE": ["Real Estate and Rental and Leasing"],
    "C&I": ["Manufacturing", "Wholesale Trade", "Retail", "Health Care and Social Assistance",
             "Professional Services", "Information", "Transportation", "Accommodation and Food"],
    "Multifamily": ["Real Estate and Rental and Leasing", "Health Care and Social Assistance"],
    "Construction": ["Construction", "Real Estate and Rental and Leasing"],
    "Specialty": ["Health Care and Social Assistance", "Accommodation and Food", "Information"],
}

RATING_TO_LETTER = {
    "1": "AAA", "2": "AA", "3": "A", "4": "BBB", "5": "BB",
    "6": "B", "7": "CCC", "8": "CC", "9": "D",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_currency(val: float) -> str:
    return f"${val:,.2f}"


def fmt_date(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def rr_to_group(rr: int) -> str:
    if 1 <= rr <= 5:
        return "1 - 5"
    if rr == 6:
        return "6"
    return str(rr)


def sample_lognormal(params: dict, rng: np.random.Generator) -> float:
    x = rng.lognormal(params["mean_log"], params["sigma_log"])
    return float(np.clip(x, params["min"], params["max"]))


def sample_rating(seg: str, rng: np.random.Generator) -> int:
    dist = RATING_DISTRIBUTIONS.get(seg, RATING_DISTRIBUTIONS["C&I"])
    bucket = rng.choice(
        [(1, 4), (5, 6), (7, 9)],
        p=[dist["pass"], dist["watch"], dist["classified"]],
    )
    return int(rng.integers(bucket[0], bucket[1] + 1))


def get_prop_types(seg: str) -> list[str]:
    return {
        "CRE": CRE_PROP_TYPES,
        "Multifamily": MF_PROP_TYPES,
        "Construction": CONSTRUCT_PROP_TYPES,
        "Specialty": SPECIALTY_PROP_TYPES,
    }.get(seg, CANDI_PROP_TYPES)


def get_class_codes(seg: str) -> list[str]:
    return {
        "CRE": CRE_CLASS_CODES,
        "Multifamily": MF_CLASS_CODES,
        "Construction": CONSTRUCT_CLASS_CODES,
        "Specialty": SPECIALTY_CLASS_CODES,
    }.get(seg, CANDI_CLASS_CODES)


def generate_borrower_name(rng: np.random.Generator) -> str:
    prefix = rng.choice(BORROWER_PREFIXES)
    suffix = rng.choice(BORROWER_SUFFIXES)
    return f"{prefix} {suffix}"


# ---------------------------------------------------------------------------
# Funded Portfolio — 20,000 loans
# ---------------------------------------------------------------------------

def generate_funded_portfolio(rng: np.random.Generator, n: int = 20000) -> list[dict]:
    rows = []
    segments = list(SEGMENT_WEIGHTS.keys())
    seg_probs = list(SEGMENT_WEIGHTS.values())
    rate_types = list(RATE_TYPE_WEIGHTS.keys())
    rate_probs = list(RATE_TYPE_WEIGHTS.values())
    geos = list(GEO_WEIGHTS.keys())
    geo_probs = list(GEO_WEIGHTS.values())

    for i in range(n):
        acct_no = f"{i + 1:06d}"
        account_number = f"0000{acct_no}"
        seg = rng.choice(segments, p=seg_probs)

        risk_rating = sample_rating(seg, rng)
        size_params = DEAL_SIZE_PARAMS[seg]
        committed = sample_lognormal(size_params, rng)

        utilisation = float(rng.uniform(0.55, 1.0)) if seg != "Construction" else float(rng.uniform(0.20, 0.85))
        funded = committed * utilisation
        undrawn = max(committed - funded, 0)

        rate_type = rng.choice(rate_types, p=rate_probs)
        rate_code = {"Fixed": "FIXED", "SOFR": "SOFR", "Prime": "Prime"}[rate_type]
        if rate_type == "Fixed":
            rate = float(rng.uniform(5.0, 7.5))
        elif rate_type == "SOFR":
            rate = float(rng.uniform(6.5, 9.0))
        else:
            rate = float(rng.uniform(7.0, 9.5))
        rate_floor = float(rng.uniform(0, 4)) if rate_type != "Fixed" else 0
        rate_adj_basis = float(rng.uniform(-0.5, 4)) if rate_type != "Fixed" else 0

        amort_weights = AMORT_WEIGHTS[seg]
        amort = rng.choice(list(amort_weights.keys()), p=list(amort_weights.values()))
        if amort == "P&I":
            payment_type = "P&I"
        elif amort == "I.O.":
            payment_type = "I.O."
        elif amort == "Revolving":
            payment_type = "Revolving"
        else:
            payment_type = "Interest"
        payment_freq = "Single Payment at Maturity" if amort == "Single Payment at Maturity" else "Monthly"

        geo = rng.choice(geos, p=geo_probs)

        # Origination dates: weighted toward recent years
        orig_year = int(rng.choice([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
                                    p=[0.03, 0.05, 0.05, 0.08, 0.12, 0.18, 0.24, 0.25]))
        orig_month = int(rng.integers(1, 13))
        orig_day = int(rng.integers(1, 29))
        orig_date = date(orig_year, orig_month, orig_day)

        tenor_min, tenor_max = TENOR_RANGES[seg]
        tenor_years = int(rng.integers(tenor_min, tenor_max + 1))
        mat_date = date(orig_year + tenor_years, orig_month, min(orig_day, 28))
        renewal_date = orig_date

        borrower = generate_borrower_name(rng)

        prop_types = get_prop_types(seg)
        prop_type = rng.choice(prop_types)
        class_codes = get_class_codes(seg)
        class_desc = rng.choice(class_codes)

        prop_type_code = {"Office": 21, "Retail": 25, "Multifamily": 18, "Mixed Use": 22,
                          "Industrial": 16, "Warehouse": 26, "1-4 Family": 1, "Land": 17,
                          "Student Housing": 18, "Senior Living": 20, "Affordable Housing": 18,
                          "Healthcare": 20, "Hospitality": 23, "Self Storage": 24,
                          "Data Center": 22, "Life Sciences": 22, "None": 0}.get(prop_type, 22)

        seg_naics = NAICS_CODES.get(seg, NAICS_CODES["C&I"])
        naics = rng.choice(seg_naics)
        seg_reports = REPORT_GROUPS.get(seg, REPORT_GROUPS["C&I"])
        report_group = rng.choice(seg_reports)

        resp_code = str(int(rng.integers(200, 290)))
        resp_name = rng.choice(RM_NAMES)
        team = rng.choice(TEAMS) if seg not in ("CRE", "Multifamily") else rng.choice(["CRE East", "CRE West", "CRE Midwest"])
        if seg == "Construction":
            team = "Construction"
        elif seg == "Specialty":
            team = "Specialty Finance"
        rel_name = resp_name

        earned_def = float(rng.uniform(0, 50_000))
        earn_interest = float(rng.uniform(-500, 5_000))
        rbc = f"{committed:,.2f}"
        fhlb = 0
        owner_occ = 1 if (seg == "C&I" and rng.random() < 0.35) else (1 if rng.random() < 0.10 else 0)
        concentration_group = prop_type if seg in ("CRE", "Multifamily", "Construction") else report_group
        mgmt_group = str(int(rng.integers(40, 80)))
        io_flag = 1 if "Interest" in payment_type or "I.O." in payment_type else 0
        io_pick = "TRUE" if io_flag else 0
        bhg_flag = 0
        sort_order = int(rng.integers(1, 30))
        renewed = 1 if rng.random() < 0.20 else 0
        tdr = "TRUE" if (risk_rating >= 8 and rng.random() < 0.15) else "FALSE"
        snc = "TRUE" if (committed >= 30_000_000 and rng.random() < 0.30) else "FALSE"
        accrual = "TRUE" if (risk_rating >= 7 and rng.random() < 0.40) else "FALSE"

        coll_code = "Real Estate 1st Mortgage" if seg != "C&I" else rng.choice(
            ["Real Estate 1st Mortgage", "Equipment", "Accounts Receivable", "Inventory", "General Business Assets"])
        coll_code_num = {"Real Estate 1st Mortgage": 16, "Equipment": 10, "Accounts Receivable": 5,
                         "Inventory": 12, "General Business Assets": 11}.get(coll_code, 16)
        purpose_code = rng.choice(["110", "120", "130", "140", "150", "160", "170", "180"])
        purpose_group = rng.choice(["1-4 Fam 1st lien", "Non Owner Occupied",
                                     "Secured by Multifamily residential", "Owner Occupied",
                                     "Commercial and Industrial", "Construction and Development"])

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
            "CalcAvail": fmt_currency(undrawn),
            "Max Credit Line": fmt_currency(committed),
            "Rate Over Split": rate,
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
# Pipeline — 1,500 active deals
# ---------------------------------------------------------------------------

def generate_pipeline(rng: np.random.Generator, n: int = 1500, borrower_pool: list[str] | None = None) -> list[dict]:
    rows = []
    if borrower_pool is None:
        borrower_pool = [generate_borrower_name(rng) for _ in range(500)]

    segments = list(SEGMENT_WEIGHTS.keys())
    seg_probs = list(SEGMENT_WEIGHTS.values())
    geos = list(GEO_WEIGHTS.keys())
    geo_probs = list(GEO_WEIGHTS.values())

    for i in range(n):
        opp_id = f"OPP-{i + 1:05d}"
        # Mix of existing borrowers (40%) and new names (60%)
        if rng.random() < 0.40 and borrower_pool:
            borrower = rng.choice(borrower_pool)
        else:
            borrower = generate_borrower_name(rng)

        stage = rng.choice(PIPELINE_STAGES, p=PIPELINE_STAGE_WEIGHTS)
        seg = rng.choice(segments, p=seg_probs)
        size_params = DEAL_SIZE_PARAMS[seg].copy()
        size_params["mean_log"] += 0.2  # Pipeline skews larger
        amount = sample_lognormal(size_params, rng)

        # Close probability varies by stage
        stage_prob_ranges = {
            "Lead": (0.10, 0.30), "Term Sheet": (0.25, 0.50),
            "Underwriting": (0.40, 0.65), "Approved": (0.65, 0.85),
            "Documentation": (0.80, 0.95), "Closing": (0.90, 0.98),
        }
        prob_range = stage_prob_ranges.get(stage, (0.20, 0.60))
        close_prob = float(rng.uniform(*prob_range))

        prop_types = get_prop_types(seg)
        prop_type = rng.choice(prop_types)
        seg_naics = NAICS_CODES.get(seg, NAICS_CODES["C&I"])
        naics = rng.choice(seg_naics)
        rate_type = rng.choice(["Fixed", "SOFR", "Prime"], p=[0.35, 0.40, 0.25])
        expected_rate = float(rng.uniform(5.5, 8.5))
        close_date = date(2026, 1, 1) + timedelta(days=int(rng.integers(15, 270)))
        risk_rating = sample_rating(seg, rng)
        # Pipeline skews toward pass-rated (fewer classified deals make it to pipeline)
        if risk_rating >= 7:
            risk_rating = min(6, risk_rating)

        rm_code = str(int(rng.integers(200, 290)))
        rm_name = rng.choice(RM_NAMES)
        state = rng.choice(geos, p=geo_probs)
        owner_occ = 1 if (seg == "C&I" and rng.random() < 0.35) else (1 if rng.random() < 0.10 else 0)
        class_codes = get_class_codes(seg)
        product_class = rng.choice(class_codes)

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
# Deposits — 15,000 accounts (~$56B total)
# ---------------------------------------------------------------------------

def generate_deposits(
    rng: np.random.Generator,
    n: int = 15000,
    counterparty_ids: list[str] | None = None,
) -> list[dict]:
    rows = []
    if counterparty_ids is None:
        counterparty_ids = [f"CPTY-{i:04d}" for i in range(5000)]

    # Target ~$56B total deposits = ~$3.7M average per account (lognormal)
    account_types = ["Checking", "Commercial Checking", "Operating", "CD", "Savings", "Money Market"]
    account_type_weights = [0.20, 0.15, 0.15, 0.20, 0.10, 0.20]
    liquidity_classes = ["Stable", "Operational", "Non-Operational", "Rate Sensitive"]
    liquidity_weights = [0.35, 0.30, 0.20, 0.15]
    segments = list(SEGMENT_WEIGHTS.keys())
    industries = ["Real Estate", "Manufacturing", "Wholesale Trade", "Retail",
                  "Healthcare", "Professional Services", "Construction",
                  "Transportation", "Accommodation", "Technology"]
    geos = list(GEO_WEIGHTS.keys())
    geo_probs = list(GEO_WEIGHTS.values())

    for i in range(n):
        acct_id = f"DEP-{i + 1:06d}"
        cust_id = rng.choice(counterparty_ids)
        acct_type = rng.choice(account_types, p=account_type_weights)

        # Size depends on account type — target ~$94B total (1.25x LDR on $75B funded)
        if acct_type == "CD":
            current_bal = float(rng.lognormal(13.3, 1.8))
        elif acct_type in ("Checking", "Savings"):
            current_bal = float(rng.lognormal(12.3, 2.2))
        else:
            current_bal = float(rng.lognormal(14.3, 1.8))
        current_bal = min(current_bal, 400_000_000)

        avg_bal = current_bal * float(rng.uniform(0.85, 1.10))

        # Rates by type
        if acct_type in ("Checking", "Commercial Checking", "Operating"):
            int_rate = float(rng.uniform(0.0, 0.02))
        elif acct_type == "CD":
            int_rate = float(rng.uniform(0.035, 0.055))
        elif acct_type == "Money Market":
            int_rate = float(rng.uniform(0.03, 0.048))
        else:
            int_rate = float(rng.uniform(0.01, 0.035))

        rate_type = "fixed" if acct_type == "CD" else ("floating" if rng.random() < 0.3 else "fixed")
        benchmark = "Fed Funds" if rate_type == "floating" else ""
        deposit_beta = float(rng.uniform(0.1, 0.6)) if rate_type == "floating" else float(rng.uniform(0.0, 0.2))
        open_date = (date(2015, 1, 1) + timedelta(days=int(rng.integers(0, 3650)))).isoformat()
        liquidity = rng.choice(liquidity_classes, p=liquidity_weights)
        segment = rng.choice(segments)
        industry = rng.choice(industries)
        state = rng.choice(geos, p=geo_probs)
        branch_code = f"BR{rng.integers(1, 55):03d}"
        product_bundle = rng.choice(["Standard", "Premium", "Treasury", "Commercial"])
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
    cmt = float(r["CMT"].replace("$", "").replace(",", ""))
    curr = float(r["CurrBal"].replace("$", "").replace(",", ""))
    orig = datetime.strptime(r["Original Note Date"], "%m/%d/%Y").date()
    mat = datetime.strptime(r["Maturity Date"], "%m/%d/%Y").date()
    seg_raw = r["ClassGroup"]
    seg_map = {"CRE": "cre", "Multifamily": "multifamily", "C&I": "c_and_i",
               "Construction": "construction", "Specialty": "specialty"}
    seg_canonical = seg_map.get(seg_raw, "other")
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
    close_d = datetime.fromisoformat(r["EXPECTED_CLOSE_DATE"]).date()
    seg_raw = r["SEGMENT"]
    seg_map = {"CRE": "cre", "Multifamily": "multifamily", "C&I": "c_and_i",
               "Construction": "construction", "Specialty": "specialty"}
    seg_canonical = seg_map.get(seg_raw, "other")
    coupon_type = "fixed" if r["RATE_TYPE"] == "Fixed" else "floating"
    stage_canonical = r["STAGE"].lower().replace(" ", "_")

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
    print("Generating 20,000 funded positions...")
    funded = generate_funded_portfolio(rng, n=20000)
    funded_path = DATA_SAMPLE / "funded_portfolio.csv"
    with open(funded_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=funded[0].keys())
        writer.writeheader()
        writer.writerows(funded)
    total_committed = sum(float(r["CMT"].replace("$", "").replace(",", "")) for r in funded)
    total_funded = sum(float(r["CurrBal"].replace("$", "").replace(",", "")) for r in funded)
    print(f"  Wrote {funded_path}")
    print(f"  {len(funded)} loans, committed ~${total_committed/1e9:.1f}B, funded ~${total_funded/1e9:.1f}B")

    # Segment breakdown
    seg_counts = {}
    for r in funded:
        seg_counts[r["ClassGroup"]] = seg_counts.get(r["ClassGroup"], 0) + 1
    for seg, cnt in sorted(seg_counts.items(), key=lambda x: -x[1]):
        print(f"    {seg}: {cnt} ({cnt/len(funded)*100:.1f}%)")

    # 2. Pipeline
    print("\nGenerating 1,500 pipeline deals...")
    borrower_pool = list({r["Borrower Name"] for r in funded[:5000]})
    pipeline = generate_pipeline(rng, n=1500, borrower_pool=borrower_pool)
    pipeline_path = DATA_SAMPLE / "pipeline.csv"
    with open(pipeline_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=pipeline[0].keys())
        writer.writeheader()
        writer.writerows(pipeline)
    total_pipeline = sum(r["EXPECTED_AMOUNT"] for r in pipeline)
    print(f"  Wrote {pipeline_path}")
    print(f"  {len(pipeline)} deals, total ~${total_pipeline/1e9:.1f}B")

    stage_counts = {}
    for r in pipeline:
        stage_counts[r["STAGE"]] = stage_counts.get(r["STAGE"], 0) + 1
    for stage in PIPELINE_STAGES:
        cnt = stage_counts.get(stage, 0)
        print(f"    {stage}: {cnt} ({cnt/len(pipeline)*100:.1f}%)")

    # 3. Deposits
    print("\nGenerating 15,000 deposit accounts...")
    cpty_ids = list({r["AcctNO"] for r in funded[:8000]})
    deposits = generate_deposits(rng, n=15000, counterparty_ids=cpty_ids)
    deposits_path = DATA_SAMPLE / "deposits.csv"
    with open(deposits_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=deposits[0].keys())
        writer.writeheader()
        writer.writerows(deposits)
    total_deposits = sum(r["CURRENT_BAL"] for r in deposits)
    print(f"  Wrote {deposits_path}")
    print(f"  {len(deposits)} accounts, total ~${total_deposits/1e9:.1f}B")
    print(f"  Deposit-to-funded ratio: {total_deposits/total_funded:.2f}x")

    # 4. Test fixtures
    fixture_funded = [build_canonical_funded(r) for r in funded[:10]]
    fixture_pipeline = [build_canonical_pipeline(r) for r in pipeline[:5]]

    with open(TESTS_FIXTURES / "sample_funded_portfolio.json", "w", encoding="utf-8") as f:
        json.dump(fixture_funded, f, indent=2)
    print(f"\nWrote {TESTS_FIXTURES / 'sample_funded_portfolio.json'} (10 positions)")

    with open(TESTS_FIXTURES / "sample_pipeline.json", "w", encoding="utf-8") as f:
        json.dump(fixture_pipeline, f, indent=2)
    print(f"Wrote {TESTS_FIXTURES / 'sample_pipeline.json'} (5 deals)")

    print("\nDone. Superregional bank dataset generated.")


if __name__ == "__main__":
    main()
