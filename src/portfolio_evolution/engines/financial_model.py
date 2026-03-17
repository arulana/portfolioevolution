"""Coherent financial statement perturbation model.

Ensures changes flow logically through the income statement and balance sheet:
  Revenue -> COGS -> Gross Profit -> Operating Expenses -> EBITDA ->
  EBIT -> Net Income, with balance sheet adjustments to maintain A = L + E.

Used at two points in the simulation:
  1. Renewal: existing borrower gets slightly perturbed financials
  2. New origination: clone a similar borrower's statement and perturb

All field names use SCREAMING_SNAKE_CASE to match the raw bank data model
produced by reverse_map_financial_spreads.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe(val) -> float:
    """Convert to float, treating None/NaN as 0."""
    try:
        v = float(val)
        return 0.0 if np.isnan(v) else v
    except (ValueError, TypeError):
        return 0.0


def perturb_income_statement(
    row: dict,
    revenue_growth: float,
    cogs_margin_drift: float,
    expense_growth_multiplier: float,
    rng: np.random.Generator,
) -> dict:
    """Perturb income statement fields with coherent cascading.

    1. Revenue grows by revenue_growth
    2. COGS margin drifts slightly (costOfSalesDepreciation carried proportionally)
    3. SG&A and other expenses grow at a fraction of revenue growth
    4. Cascades: Gross Profit -> EBITDA -> EBIT -> pre-tax -> Net Income
    """
    out = dict(row)

    rev = _safe(row.get("NET_SALES"))
    new_rev = rev * (1.0 + revenue_growth)
    out["NET_SALES"] = round(new_rev, 2)

    total_rev = _safe(row.get("TOTAL_OPERATING_REVENUE"))
    if total_rev > 0:
        out["TOTAL_OPERATING_REVENUE"] = round(total_rev * (1.0 + revenue_growth), 2)
    elif new_rev > 0:
        out["TOTAL_OPERATING_REVENUE"] = round(new_rev, 2)

    # COGS margin drift
    cogs = _safe(row.get("TOTAL_COST_OF_GOODS_SOLD"))
    cogs_margin = cogs / rev if rev > 0 else 0.65
    new_cogs_margin = max(0.1, min(0.95, cogs_margin + rng.normal(0, cogs_margin_drift)))
    new_cogs = new_rev * new_cogs_margin
    out["TOTAL_COST_OF_GOODS_SOLD"] = round(new_cogs, 2)

    # costOfSalesDepreciation scales proportionally with COGS
    csd = _safe(row.get("COST_OF_SALES_DEPRECIATION"))
    if cogs > 0 and csd > 0:
        out["COST_OF_SALES_DEPRECIATION"] = round(csd * (new_cogs / cogs), 2)

    new_gross = new_rev - new_cogs
    out["GROSS_PROFIT"] = round(new_gross, 2)

    # SG&A grows at a fraction of revenue growth
    sga = _safe(row.get("SGA_EXPENSES"))
    sga_growth = revenue_growth * expense_growth_multiplier + rng.normal(0, 0.005)
    new_sga = max(0, sga * (1.0 + sga_growth))
    out["SGA_EXPENSES"] = round(new_sga, 2)

    other_opex = _safe(row.get("OPERATING_EXPENSE_OTHER"))
    new_other_opex = max(0, other_opex * (1.0 + sga_growth * 0.5))
    out["OPERATING_EXPENSE_OTHER"] = round(new_other_opex, 2)

    da = _safe(row.get("TOTAL_AMORTIZATION_AND_DEPRECIATION"))
    out["TOTAL_AMORTIZATION_AND_DEPRECIATION"] = round(da, 2)

    new_total_opex = new_cogs + new_sga + new_other_opex + da
    out["TOTAL_OPERATING_EXPENSE"] = round(new_total_opex, 2)

    new_op_profit = new_rev - new_total_opex
    out["TOTAL_OPERATING_PROFIT"] = round(new_op_profit, 2)

    new_ebitda = new_op_profit + da
    out["EBITDA"] = round(new_ebitda, 2)
    out["EBIT"] = round(new_op_profit, 2)

    # Below the line
    interest_exp = _safe(row.get("TOTAL_INTEREST_EXPENSE"))
    gross_int_inc = _safe(row.get("GROSS_INTEREST_INCOME"))
    other_inc = _safe(row.get("OTHER_INCOME"))
    other_exp = _safe(row.get("OTHER_EXPENSES"))
    cap_int = _safe(row.get("CAPITALIZED_INTEREST_EXPENSE"))
    tax = _safe(row.get("CURRENT_INCOME_TAX_EXPENSE"))

    pre_tax = new_op_profit + other_inc - other_exp + gross_int_inc - interest_exp + cap_int
    if pre_tax > 0 and tax > 0:
        old_pre_tax = (_safe(row.get("TOTAL_OPERATING_PROFIT"))
                       + _safe(row.get("OTHER_INCOME"))
                       - _safe(row.get("OTHER_EXPENSES"))
                       + _safe(row.get("GROSS_INTEREST_INCOME"))
                       - _safe(row.get("TOTAL_INTEREST_EXPENSE"))
                       + _safe(row.get("CAPITALIZED_INTEREST_EXPENSE")))
        implied_rate = tax / max(abs(old_pre_tax), 1)
        implied_rate = min(0.40, max(0.10, implied_rate))
        new_tax = pre_tax * implied_rate
    else:
        new_tax = tax
    out["CURRENT_INCOME_TAX_EXPENSE"] = round(new_tax, 2)

    extras = _safe(row.get("TOTAL_EXTRAORDINARY_ITEMS"))
    minority = _safe(row.get("MINORITY_INTEREST_EXPENSE"))
    new_net_income = pre_tax - new_tax - minority + extras
    out["NET_INCOME"] = round(new_net_income, 2)

    return out


def perturb_balance_sheet(
    row: dict,
    revenue_growth: float,
    asset_growth_multiplier: float,
    net_income_delta: float,
    da_amount: float,
    rng: np.random.Generator,
) -> dict:
    """Perturb balance sheet maintaining A = L + E.

    1. Current assets scale with revenue growth
    2. Fixed assets scale more slowly; accumulated depreciation increases by D&A
    3. Retained earnings absorb net income change
    4. Liabilities forced to balance: L = A - E
    """
    out = dict(row)
    asset_growth = revenue_growth * asset_growth_multiplier + rng.normal(0, 0.005)

    # --- Current assets (scale sub-components, derive total) ---
    cash = _safe(row.get("CASH_AND_MARKETABLE_SECURITIES")) * (1.0 + asset_growth)
    recv = _safe(row.get("RECEIVABLE_FROM_TRADE")) * (1.0 + asset_growth)
    ar = _safe(row.get("TOTAL_ACCOUNTS_RECEIVABLE"))
    # If receivableFromTrade is a sub-component of totalAccountsReceivable,
    # scale the total consistently
    if ar > 0 and recv > 0:
        ar_new = ar * (1.0 + asset_growth)
    else:
        ar_new = recv
    inv = _safe(row.get("TOTAL_INVENTORY")) * (1.0 + asset_growth)
    other_ca = _safe(row.get("OTHER_CURRENT_ASSETS")) * (1.0 + asset_growth)

    out["CASH_AND_MARKETABLE_SECURITIES"] = round(cash, 2)
    out["RECEIVABLE_FROM_TRADE"] = round(recv, 2)
    out["TOTAL_ACCOUNTS_RECEIVABLE"] = round(ar_new, 2)
    out["TOTAL_INVENTORY"] = round(inv, 2)
    out["OTHER_CURRENT_ASSETS"] = round(other_ca, 2)

    total_ca = cash + ar_new + inv + other_ca
    out["TOTAL_CURRENT_ASSETS"] = round(total_ca, 2)

    # --- Non-current assets (slower growth, accumulated depreciation increases) ---
    fa_growth = asset_growth * 0.3
    fixed = _safe(row.get("TOTAL_FIXED_ASSETS")) * (1.0 + fa_growth)
    lt_inv = _safe(row.get("TOTAL_LONG_TERM_INVESTMENTS")) * (1.0 + fa_growth)
    intang = _safe(row.get("TOTAL_INTANGIBLE_ASSETS")) * (1.0 + fa_growth)
    other_a = _safe(row.get("OTHER_ASSETS")) * (1.0 + fa_growth)

    # Accumulated depreciation is a CONTRA asset (negative): increases by annual D&A
    # Capped so it never exceeds gross fixed assets
    accum_dep = _safe(row.get("TOTAL_ACCUMULATED_DEPRECIATION"))
    new_accum_dep = max(accum_dep - abs(da_amount), -abs(fixed))

    out["TOTAL_FIXED_ASSETS"] = round(fixed, 2)
    out["TOTAL_LONG_TERM_INVESTMENTS"] = round(lt_inv, 2)
    out["TOTAL_INTANGIBLE_ASSETS"] = round(intang, 2)
    out["OTHER_ASSETS"] = round(other_a, 2)
    out["TOTAL_ACCUMULATED_DEPRECIATION"] = round(new_accum_dep, 2)

    total_nca = fixed + new_accum_dep + lt_inv + intang + other_a
    out["TOTAL_NON_CURRENT_ASSETS"] = round(total_nca, 2)

    new_total_assets = total_ca + total_nca
    out["TOTAL_ASSETS"] = round(new_total_assets, 2)

    # --- Equity: retained earnings absorbs net income delta ---
    retained = _safe(row.get("RETAINED_EARNINGS"))
    new_retained = retained + net_income_delta
    out["RETAINED_EARNINGS"] = round(new_retained, 2)

    old_nw = _safe(row.get("NET_WORTH"))
    new_nw = old_nw + net_income_delta
    out["NET_WORTH"] = round(new_nw, 2)

    # --- Liabilities = Assets - Equity (force balance) ---
    new_total_liabilities = new_total_assets - new_nw
    out["TOTAL_LIABILITIES"] = round(new_total_liabilities, 2)
    out["TOTAL_LIABILITIES_AND_NET_WORTH"] = round(new_total_assets, 2)

    # Distribute liabilities change proportionally
    old_total_liab = _safe(row.get("TOTAL_LIABILITIES"))
    liab_ratio = new_total_liabilities / old_total_liab if old_total_liab > 0 else 1.0

    # Current liabilities (scale sub-components, derive total)
    std = _safe(row.get("SHORT_TERM_DEBT")) * liab_ratio
    payable = _safe(row.get("PAYABLE_TO_TRADE")) * liab_ratio
    ap = _safe(row.get("TOTAL_ACCOUNTS_PAYABLE"))
    if ap > 0 and payable > 0:
        ap_new = ap * liab_ratio
    else:
        ap_new = payable
    accrued = _safe(row.get("TOTAL_ACCRUED_LIABILITIES")) * liab_ratio
    other_cl = _safe(row.get("OTHER_CURRENT_LIABILITIES")) * liab_ratio

    out["SHORT_TERM_DEBT"] = round(std, 2)
    out["PAYABLE_TO_TRADE"] = round(payable, 2)
    out["TOTAL_ACCOUNTS_PAYABLE"] = round(ap_new, 2)
    out["TOTAL_ACCRUED_LIABILITIES"] = round(accrued, 2)
    out["OTHER_CURRENT_LIABILITIES"] = round(other_cl, 2)

    cl = std + ap_new + accrued + other_cl
    out["TOTAL_CURRENT_LIABILITIES"] = round(cl, 2)

    # Non-current liabilities
    ltd = _safe(row.get("TOTAL_LONG_TERM_DEBT")) * liab_ratio
    sub = _safe(row.get("TOTAL_SUBORDINATED_DEBT")) * liab_ratio
    other_ncl = _safe(row.get("OTHER_NON_CURRENT_LIABILITIES")) * liab_ratio

    out["TOTAL_LONG_TERM_DEBT"] = round(ltd, 2)
    out["TOTAL_SUBORDINATED_DEBT"] = round(sub, 2)
    out["OTHER_NON_CURRENT_LIABILITIES"] = round(other_ncl, 2)

    ncl = ltd + sub + other_ncl
    out["TOTAL_NON_CURRENT_LIABILITIES"] = round(ncl, 2)

    # --- Balance assertion ---
    a = out["TOTAL_ASSETS"]
    l_plus_e = out["TOTAL_LIABILITIES"] + out["NET_WORTH"]
    if abs(a - l_plus_e) > 0.05:
        # Force-balance via rounding residual into other_assets
        out["OTHER_ASSETS"] = round(_safe(out.get("OTHER_ASSETS")) + (l_plus_e - a), 2)
        out["TOTAL_NON_CURRENT_ASSETS"] = round(
            _safe(out["TOTAL_NON_CURRENT_ASSETS"]) + (l_plus_e - a), 2)
        out["TOTAL_ASSETS"] = round(l_plus_e, 2)
        out["TOTAL_LIABILITIES_AND_NET_WORTH"] = round(l_plus_e, 2)

    return out


def perturb_financial_statement(
    row: dict,
    config: dict,
    rng: np.random.Generator,
) -> dict:
    """Apply a coherent perturbation to a single financial statement row.

    Config keys:
      revenue_growth_range: [min, max] for uniform draw
      cogs_margin_drift: std dev of COGS margin noise
      expense_growth_multiplier: fraction of revenue growth applied to expenses
      asset_growth_multiplier: fraction of revenue growth applied to assets
    """
    rev_range = config.get("revenue_growth_range", [-0.05, 0.05])
    revenue_growth = float(rng.uniform(rev_range[0], rev_range[1]))

    cogs_drift = config.get("cogs_margin_drift", 0.005)
    expense_mult = config.get("expense_growth_multiplier", 0.7)
    asset_mult = config.get("asset_growth_multiplier", 0.5)

    old_ni = _safe(row.get("NET_INCOME"))
    perturbed = perturb_income_statement(row, revenue_growth, cogs_drift, expense_mult, rng)
    new_ni = _safe(perturbed.get("NET_INCOME"))
    ni_delta = new_ni - old_ni

    da = _safe(perturbed.get("TOTAL_AMORTIZATION_AND_DEPRECIATION"))
    perturbed = perturb_balance_sheet(perturbed, revenue_growth, asset_mult, ni_delta, da, rng)

    return perturbed


def perturb_entity_financials(
    financials_df: pd.DataFrame,
    entity_ids: list[str],
    new_statement_date: str,
    config: dict,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Perturb financial statements for entities at renewal.

    Creates new statement rows with new_statement_date.
    Old statements stay intact for historical context.
    """
    new_rows = []

    for eid in entity_ids:
        ent_stmts = financials_df[financials_df["ENTITY_IDENTIFIER"] == eid]
        if ent_stmts.empty:
            continue

        latest = ent_stmts.sort_values("FINANCIAL_STATEMENT_DATE", ascending=False).iloc[0]
        row_dict = latest.to_dict()

        perturbed = perturb_financial_statement(row_dict, config, rng)
        perturbed["FINANCIAL_STATEMENT_DATE"] = new_statement_date
        perturbed["FINANCIAL_STATEMENT_YEAR"] = new_statement_date[:4]
        perturbed["AS_OF_DATE"] = new_statement_date

        new_rows.append(perturbed)

    if not new_rows:
        return pd.DataFrame()

    return pd.DataFrame(new_rows)


def clone_and_perturb(
    financials_df: pd.DataFrame,
    source_entity_id: str,
    new_entity_id: str,
    statement_date: str,
    config: dict,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Clone a source entity's financials for a new borrower, with perturbation.

    Used when generating new originations that need financial statements.
    """
    source_stmts = financials_df[financials_df["ENTITY_IDENTIFIER"] == source_entity_id]
    if source_stmts.empty:
        return pd.DataFrame()

    latest = source_stmts.sort_values("FINANCIAL_STATEMENT_DATE", ascending=False).iloc[0]
    row_dict = latest.to_dict()

    perturbed = perturb_financial_statement(row_dict, config, rng)
    perturbed["ENTITY_IDENTIFIER"] = new_entity_id
    perturbed["FINANCIAL_STATEMENT_DATE"] = statement_date
    perturbed["FINANCIAL_STATEMENT_YEAR"] = statement_date[:4]
    perturbed["AS_OF_DATE"] = statement_date
    perturbed["FINANCIAL_STATEMENT_REFERENCE"] = f"FS-{new_entity_id}-{statement_date}"

    return pd.DataFrame([perturbed])
