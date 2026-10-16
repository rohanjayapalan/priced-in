"""Priced In valuation engine, model v1.0.

Reverse DCF: solve for the 5-year revenue growth rate that makes a 10-year
free-cash-flow model equal today's share price.

Structure (locked as v1.0 on Oct 14, 2026):
  * Years 1-5: revenue grows at g (the unknown).
  * Years 6-10: growth fades in a straight line from g to terminal growth.
  * Free cash flow each year = revenue x FCF margin (held at its trailing level).
  * Terminal value after year 10 = FCF_10 x (1 + gT) / (WACC - gT).
  * Discounted at WACC, end-of-year convention.
  * Equity value = enterprise value - debt + cash; per share = / shares.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import math

MODEL_VERSION = "1.0"
EXPLICIT_YEARS = 5
FADE_YEARS = 5
VERDICT_BAND = 0.03  # +/- 3 percentage points, set before any backtest


@dataclass
class Inputs:
    revenue: float          # trailing 12 months, in the reporting currency
    fcf_margin: float       # unlevered free cash flow / revenue
    wacc: float
    terminal_growth: float
    debt: float
    cash: float
    shares: float
    minority: float = 0.0


def revenue_path(r0: float, g: float, gT: float) -> list[float]:
    """Revenue for years 1..10 under the growth-then-fade schedule."""
    rev, out = r0, []
    for t in range(1, EXPLICIT_YEARS + FADE_YEARS + 1):
        if t <= EXPLICIT_YEARS:
            gt = g
        else:
            k = t - EXPLICIT_YEARS  # 1..5
            gt = g - (g - gT) * k / FADE_YEARS
        rev *= 1 + gt
        out.append(rev)
    return out


def enterprise_value(inp: Inputs, g: float) -> float:
    revs = revenue_path(inp.revenue, g, inp.terminal_growth)
    w = inp.wacc
    pv = 0.0
    for t, r in enumerate(revs, start=1):
        pv += r * inp.fcf_margin / (1 + w) ** t
    fcf10 = revs[-1] * inp.fcf_margin
    tv = fcf10 * (1 + inp.terminal_growth) / (w - inp.terminal_growth)
    pv += tv / (1 + w) ** len(revs)
    return pv


def value_per_share(inp: Inputs, g: float) -> float:
    ev = enterprise_value(inp, g)
    equity = ev - inp.debt + inp.cash - inp.minority
    return equity / inp.shares


def implied_growth(inp: Inputs, price: float, lo: float = -0.50, hi: float = 1.00,
                   tol: float = 1e-7) -> float | None:
    """Bisection: find g with value_per_share(g) == price. None if out of range."""
    if inp.wacc <= inp.terminal_growth:
        return None
    f_lo = value_per_share(inp, lo) - price
    f_hi = value_per_share(inp, hi) - price
    if f_lo > 0 or f_hi < 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = value_per_share(inp, mid) - price
        if abs(f_mid) < tol * max(1.0, price) or (hi - lo) < 1e-9:
            return mid
        if f_mid > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def blume(beta_raw: float) -> float:
    return 0.67 * beta_raw + 0.33


def debt_spread(debt_to_ebitda: float) -> float:
    """Synthetic credit spread from leverage (documented approximation)."""
    if debt_to_ebitda < 1.0:
        return 0.0100
    if debt_to_ebitda < 2.0:
        return 0.0125
    if debt_to_ebitda < 3.0:
        return 0.0160
    if debt_to_ebitda < 4.0:
        return 0.0200
    return 0.0275


def wacc(rf: float, beta_adj: float, erp: float, debt: float, equity: float,
         spread: float, tax: float) -> dict:
    ke = rf + beta_adj * erp
    kd = rf + spread
    v = debt + equity
    wd = debt / v if v > 0 else 0.0
    we = 1 - wd
    w = we * ke + wd * kd * (1 - tax)
    return {"ke": ke, "kd": kd, "kd_after_tax": kd * (1 - tax), "we": we, "wd": wd, "wacc": w}


def verdict(gap: float | None) -> str:
    if gap is None:
        return "n/a"
    if gap >= VERDICT_BAND:
        return "Expectations too high"
    if gap <= -VERDICT_BAND:
        return "Expectations too low"
    return "About right"


def sensitivity_grid(inp: Inputs, price: float, waccs: list[float], tgs: list[float]):
    grid = []
    for w in waccs:
        row = []
        for gT in tgs:
            alt = Inputs(**{**asdict(inp), "wacc": w, "terminal_growth": gT})
            row.append(implied_growth(alt, price))
        grid.append(row)
    return grid
