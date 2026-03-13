"""System-specific output views for the four source systems.

Each formatter takes simulation state and produces a DataFrame with column names
matching what the BDI team would receive from a real bank's systems:
- CRM (Salesforce/nCino CRM) — pipeline leads and term sheets
- LOS (Loan Origination System) — underwriting through closing
- Core Banking (FIS/Jack Henry/Fiserv) — funded on-balance-sheet loans
- Core Deposits — deposit accounts
"""

from __future__ import annotations

from typing import Any

import polars as pl

from portfolio_evolution.models import InstrumentPosition
from portfolio_evolution.models.deposit import DepositPosition


def format_crm_view(
    positions: list[InstrumentPosition],
    sim_day: int | None = None,
    sim_date: Any = None,
) -> pl.DataFrame:
    """Format pipeline_crm positions as a CRM system export.

    Columns mimic a Salesforce/nCino CRM extract.
    """
    crm_positions = [p for p in positions if p.position_type == "pipeline_crm"]

    if not crm_positions:
        return pl.DataFrame(schema={
            "OPP_ID": pl.Utf8, "BORROWER_NAME": pl.Utf8, "STAGE": pl.Utf8,
            "EXPECTED_AMOUNT": pl.Float64, "CLOSE_PROB": pl.Float64,
            "SEGMENT": pl.Utf8, "RM_NAME": pl.Utf8, "RM_CODE": pl.Utf8,
            "EXPECTED_CLOSE_DATE": pl.Utf8, "LAST_ACTIVITY_DATE": pl.Utf8,
            "STATE": pl.Utf8, "SOURCE": pl.Utf8, "SIM_DAY": pl.Int64,
        })

    rows = []
    for p in crm_positions:
        stage_display = (p.pipeline_stage or "").replace("_", " ").title()
        rows.append({
            "OPP_ID": p.instrument_id,
            "BORROWER_NAME": p.counterparty_name or p.counterparty_id,
            "STAGE": stage_display,
            "EXPECTED_AMOUNT": p.committed_amount,
            "CLOSE_PROB": p.close_probability,
            "SEGMENT": p.segment,
            "RM_NAME": p.relationship_manager,
            "RM_CODE": p.relationship_manager_id,
            "EXPECTED_CLOSE_DATE": str(p.expected_close_date) if p.expected_close_date else None,
            "LAST_ACTIVITY_DATE": str(p.as_of_date),
            "STATE": p.geography,
            "SOURCE": "CRM Pipeline",
            "SIM_DAY": sim_day,
        })

    return pl.DataFrame(rows)


def format_los_view(
    positions: list[InstrumentPosition],
    sim_day: int | None = None,
    sim_date: Any = None,
) -> pl.DataFrame:
    """Format pipeline_los positions as a Loan Origination System export.

    Columns mimic nCino/Abrigo LOS data.
    """
    los_positions = [p for p in positions if p.position_type == "pipeline_los"]

    if not los_positions:
        return pl.DataFrame(schema={
            "APP_ID": pl.Utf8, "BORROWER_NAME": pl.Utf8, "UW_STAGE": pl.Utf8,
            "REQUESTED_AMOUNT": pl.Float64, "APPROVED_AMOUNT": pl.Float64,
            "RISK_RATING": pl.Utf8, "RATING_NUMERIC": pl.Int64,
            "ANALYST_CODE": pl.Utf8, "APPROVAL_DATE": pl.Utf8,
            "EXPECTED_CLOSE_DATE": pl.Utf8, "RATE_TYPE": pl.Utf8,
            "EXPECTED_RATE": pl.Float64, "SEGMENT": pl.Utf8,
            "STATE": pl.Utf8, "IS_RENEWAL": pl.Boolean,
            "CONDITION_COUNT": pl.Int64, "SIM_DAY": pl.Int64,
        })

    rows = []
    for p in los_positions:
        stage_display = (p.pipeline_stage or "").replace("_", " ").title()
        approved_amt = p.committed_amount if p.pipeline_stage in ("approved", "documentation", "closing") else None
        approval_date = str(p.as_of_date) if p.pipeline_stage in ("approved", "documentation", "closing") else None

        rows.append({
            "APP_ID": p.instrument_id,
            "BORROWER_NAME": p.counterparty_name or p.counterparty_id,
            "UW_STAGE": stage_display,
            "REQUESTED_AMOUNT": p.committed_amount,
            "APPROVED_AMOUNT": approved_amt,
            "RISK_RATING": p.internal_rating,
            "RATING_NUMERIC": p.internal_rating_numeric,
            "ANALYST_CODE": p.relationship_manager_id,
            "APPROVAL_DATE": approval_date,
            "EXPECTED_CLOSE_DATE": str(p.expected_close_date) if p.expected_close_date else None,
            "RATE_TYPE": p.coupon_type,
            "EXPECTED_RATE": p.coupon_rate,
            "SEGMENT": p.segment,
            "STATE": p.geography,
            "IS_RENEWAL": p.is_renewal,
            "CONDITION_COUNT": 0,
            "SIM_DAY": sim_day,
        })

    return pl.DataFrame(rows)


def format_core_view(
    positions: list[InstrumentPosition],
    sim_day: int | None = None,
    sim_date: Any = None,
) -> pl.DataFrame:
    """Format funded positions as a Core Banking system export.

    Columns mimic FIS/Jack Henry/Fiserv core system data.
    """
    funded_positions = [p for p in positions if p.position_type == "funded"]

    if not funded_positions:
        return pl.DataFrame(schema={
            "ACCT_NO": pl.Utf8, "BORROWER": pl.Utf8, "CURRENT_BAL": pl.Float64,
            "COMMITTED_AMT": pl.Float64, "INT_RATE": pl.Float64,
            "RATE_TYPE": pl.Utf8, "ORIG_DATE": pl.Utf8, "MATURITY_DATE": pl.Utf8,
            "AMORT_TYPE": pl.Utf8, "PMT_FREQ": pl.Utf8,
            "RISK_RATING": pl.Utf8, "RISK_RATING_NUM": pl.Int64,
            "SEGMENT": pl.Utf8, "PRODUCT_TYPE": pl.Utf8,
            "STATE": pl.Utf8, "ACCRUAL_STATUS": pl.Utf8,
            "COLLATERAL_TYPE": pl.Utf8, "PROPERTY_TYPE": pl.Utf8,
            "OWNER_OCC": pl.Boolean, "SNC_FLAG": pl.Boolean,
            "TDR_FLAG": pl.Boolean, "AS_OF_DATE": pl.Utf8, "SIM_DAY": pl.Int64,
        })

    rows = []
    for p in funded_positions:
        rows.append({
            "ACCT_NO": p.instrument_id,
            "BORROWER": p.counterparty_name or p.counterparty_id,
            "CURRENT_BAL": p.funded_amount,
            "COMMITTED_AMT": p.committed_amount,
            "INT_RATE": p.coupon_rate,
            "RATE_TYPE": (p.coupon_type or "").upper(),
            "ORIG_DATE": str(p.origination_date) if p.origination_date else None,
            "MATURITY_DATE": str(p.maturity_date) if p.maturity_date else None,
            "AMORT_TYPE": p.amortisation_type,
            "PMT_FREQ": p.payment_frequency,
            "RISK_RATING": p.internal_rating,
            "RISK_RATING_NUM": p.internal_rating_numeric,
            "SEGMENT": p.segment,
            "PRODUCT_TYPE": p.product_type,
            "STATE": p.geography,
            "ACCRUAL_STATUS": "Accruing" if p.accrual_status else "Non-Accrual",
            "COLLATERAL_TYPE": p.collateral_type,
            "PROPERTY_TYPE": p.property_type,
            "OWNER_OCC": p.owner_occupied_flag,
            "SNC_FLAG": p.snc_flag,
            "TDR_FLAG": p.tdr_flag,
            "AS_OF_DATE": str(p.as_of_date),
            "SIM_DAY": sim_day,
        })

    return pl.DataFrame(rows)


def format_deposits_view(
    deposits: list[DepositPosition],
    sim_day: int | None = None,
    sim_date: Any = None,
) -> pl.DataFrame:
    """Format deposit positions as a Core Deposit system export.

    Columns mimic core banking deposit data.
    """
    if not deposits:
        return pl.DataFrame(schema={
            "ACCOUNT_ID": pl.Utf8, "CUSTOMER_ID": pl.Utf8,
            "ACCOUNT_TYPE": pl.Utf8, "CURRENT_BAL": pl.Float64,
            "INT_RATE": pl.Float64, "RATE_TYPE": pl.Utf8,
            "DEPOSIT_BETA": pl.Float64, "OPEN_DATE": pl.Utf8,
            "LIQUIDITY_CLASS": pl.Utf8, "SEGMENT": pl.Utf8,
            "AS_OF_DATE": pl.Utf8, "SIM_DAY": pl.Int64,
        })

    rows = []
    for d in deposits:
        rows.append({
            "ACCOUNT_ID": d.deposit_id,
            "CUSTOMER_ID": d.counterparty_id,
            "ACCOUNT_TYPE": d.deposit_type,
            "CURRENT_BAL": d.current_balance,
            "INT_RATE": d.interest_rate,
            "RATE_TYPE": d.rate_type,
            "DEPOSIT_BETA": d.beta,
            "OPEN_DATE": str(d.origination_date) if d.origination_date else None,
            "LIQUIDITY_CLASS": d.liquidity_category,
            "SEGMENT": d.segment,
            "AS_OF_DATE": str(d.as_of_date),
            "SIM_DAY": sim_day,
        })

    return pl.DataFrame(rows)
