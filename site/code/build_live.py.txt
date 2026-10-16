"""Build today's live valuations (model v1.0) from the raw inputs."""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import engine as E

ROOT = os.path.dirname(os.path.dirname(__file__))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "out")
os.makedirs(OUT, exist_ok=True)

AS_OF = "2026-10-13"  # last full close used for prices and market caps

# Market inputs (sources noted in data/sources.json)
RF_US = 0.0521        # 10-year Treasury, Oct 13 2026 (US Treasury)
RF_CA = 0.0387        # 10-year Government of Canada benchmark, Oct 13 2026 (Bank of Canada Valet)
REAL_10Y = 0.0288     # 10-year TIPS real yield, Oct 13 2026 (US Treasury)
BREAKEVEN = RF_US - REAL_10Y
ERP = 0.0423          # Damodaran implied ERP, start of 2026
TAX_US, TAX_CA = 0.25, 0.265

COMPANIES = {
    # ticker: (name, group, country, currency, index)
    "ICE": ("Intercontinental Exchange", "Exchanges", "US", "USD", "GSPC"),
    "CME": ("CME Group", "Exchanges", "US", "USD", "GSPC"),
    "NDAQ": ("Nasdaq", "Exchanges", "US", "USD", "GSPC"),
    "CBOE": ("Cboe Global Markets", "Exchanges", "US", "USD", "GSPC"),
    "X": ("TMX Group", "Exchanges", "Canada", "CAD", "GSPTSE"),
    "TW": ("Tradeweb", "Exchanges", "US", "USD", "GSPC"),
    "MKTX": ("MarketAxess", "Exchanges", "US", "USD", "GSPC"),
    "SPGI": ("S&P Global", "Ratings and indexes", "US", "USD", "GSPC"),
    "MCO": ("Moody's", "Ratings and indexes", "US", "USD", "GSPC"),
    "MSCI": ("MSCI", "Ratings and indexes", "US", "USD", "GSPC"),
    "MORN": ("Morningstar", "Ratings and indexes", "US", "USD", "GSPC"),
    "FDS": ("FactSet", "Data and software", "US", "USD", "GSPC"),
    "TRI": ("Thomson Reuters", "Data and software", "Canada", "USD", "GSPC"),
    "BR": ("Broadridge", "Data and software", "US", "USD", "GSPC"),
    "SSNC": ("SS&C Technologies", "Data and software", "US", "USD", "GSPC"),
    "VRSK": ("Verisk", "Data and software", "US", "USD", "GSPC"),
    "FICO": ("Fair Isaac", "Credit data", "US", "USD", "GSPC"),
    "EFX": ("Equifax", "Credit data", "US", "USD", "GSPC"),
    "TRU": ("TransUnion", "Credit data", "US", "USD", "GSPC"),
}

FLAGS = {
    "MKTX": ("Deal price", "ICE agreed on July 30, 2026 to buy MarketAxess for $167 a share in cash; the stock trades on the deal, not on growth."),
    "SPGI": ("History not comparable", "Mobility was spun off on July 1, 2026 and IHS Markit merged in 2022; revenue is S&P's recast figure without Mobility."),
    "ICE": ("History not comparable", "Black Knight joined in September 2023, so past growth includes an acquisition."),
    "NDAQ": ("History not comparable", "Adenza joined in November 2023, so past growth includes an acquisition."),
    "X": ("History not comparable", "VettaFi was consolidated in 2024 and the Cboe Canada purchase is pending."),
    "CME": ("Cyclical volumes", "Futures volumes swing with volatility; judge growth through the cycle."),
    "CBOE": ("Cyclical volumes", "Options volumes swing with volatility; revenue here is net of rebates and routing fees."),
    "TW": ("Cyclical volumes", "Bond and rates trading volumes move with rate volatility."),
}

# History windows: (start label, start revenue column, years to TTM). None = not usable.
# TTM ends Jun 2026 for December filers; FDS (Aug) and BR (Jun) TTM = latest fiscal year.
HISTORY_WINDOWS = {
    "MCO": ("fy2021", 4.5), "MSCI": ("fy2021", 4.5), "CME": ("fy2021", 4.5),
    "CBOE": ("fy2021", 4.5), "TW": ("fy2021", 4.5), "MKTX": ("fy2021", 4.5),
    "MORN": ("fy2021", 4.5), "TRI": ("fy2021", 4.5), "SSNC": ("fy2021", 4.5),
    "EFX": ("fy2021", 4.5),
    "FDS": ("fy2022", 3.0),   # FY2023 (Aug-23) -> FY2026 (Aug-26), after CUSIP
    "BR": ("fy2021", 4.0),    # FY2022 (Jun-22) -> FY2026 (Jun-26), after Itiviti
    "FICO": ("fy2021", 4.75), # FY2021 (Sep-21) -> TTM Jun-26
    "TRU": ("fy2022", 3.5),   # FY2022 -> TTM, after Neustar
    "VRSK": ("fy2023", 2.5),  # FY2023 -> TTM, after divestitures
    "SPGI": None, "ICE": None, "NDAQ": None, "X": None,
}

# Consensus: stockanalysis 3-year revenue CAGR forecast, except where that figure
# compares unlike revenue (see notes).
CONSENSUS_OVERRIDE = {
    "SPGI": (0.070, "Average of 2026e growth over recast 2025 (+8.7%) and 2027e over 2026e (+5.5%), Yahoo Finance consensus"),
    "CBOE": (0.060, "Forward net revenue implied by forward P/S (stockanalysis) over trailing net revenue"),
}

# Revenue / FCF overrides
SPGI_REV_EX_MOBILITY = 14317e6  # Q3'25 3,443 + Q4'25 3,472 + Q1'26 3,717 (recast) + Q2'26 est 3,685
SPGI_NCI_FCF = 0.32e9           # CME's 27% share of S&P Dow Jones Indices cash flow


def load_stats():
    df = pd.read_csv(os.path.join(RAW, "fund", "stats_batch1.csv"))
    return df.set_index("ticker")


def load_rev_hist():
    df = pd.read_csv(os.path.join(RAW, "fund", "revenue_history.csv"))
    return df.set_index("ticker")


def load_monthly(sym: str) -> pd.Series:
    p = os.path.join(RAW, "monthly", f"{sym}.csv")
    df = pd.read_csv(p)
    col = "adjclose" if "adjclose" in df.columns else "close"
    df = df.dropna(subset=[col])
    # keep the last row listed for each month (the monthly bar, not the live snapshot)
    df = df.groupby("month", as_index=False).last()
    s = df.set_index("month")[col].astype(float).sort_index()
    return s


def beta_60m(sym: str, index: str, end_month: str = "2026-09") -> tuple[float, int]:
    s = load_monthly(sym)
    m = load_monthly(index)
    r = pd.concat([s.pct_change(), m.pct_change()], axis=1, keys=["s", "m"]).dropna()
    r = r[r.index <= end_month].tail(60)
    if len(r) < 36:
        return float("nan"), len(r)
    cov = np.cov(r["s"], r["m"], ddof=1)
    return cov[0, 1] / cov[1, 1], len(r)


TG_CA = 0.025  # Bank of Canada 2% inflation target + 0.5 points of real growth


def group_betas(stats):
    """Bottom-up beta: median unlevered regression beta of each group."""
    raw, unlev = {}, {}
    for t, (name, group, country, ccy, idx) in COMPANIES.items():
        s = stats.loc[t]
        if t == "CBOE":
            b = float(s["beta5y"])
        else:
            b, _ = beta_60m(t, idx)
        tax = TAX_CA if ccy == "CAD" else TAX_US
        de = float(s["total_debt"]) / float(s["market_cap"])
        raw[t] = b
        unlev[t] = b / (1 + (1 - tax) * de)
    med = {}
    for g in sorted({v[1] for v in COMPANIES.values()}):
        vals = [unlev[t] for t, v in COMPANIES.items() if v[1] == g]
        med[g] = float(np.median(vals))
    return raw, unlev, med


def main():
    stats = load_stats()
    hist = load_rev_hist()
    tg = min(BREAKEVEN + 0.005, RF_US)
    raw_b, unlev_b, group_bu = group_betas(stats)
    rows = []
    for t, (name, group, country, ccy, idx) in COMPANIES.items():
        s = stats.loc[t]
        shares = float(s["shares"])
        price = float(s["market_cap"]) / shares
        revenue = float(s["revenue"])
        fcf = float(s["fcf"])
        notes = []
        if t == "CBOE":
            revenue = float(s["gross_profit"])  # net revenue
            notes.append("Revenue is net of rebates and routing fees.")
        if t == "SPGI":
            margin_reported = fcf / revenue
            revenue = SPGI_REV_EX_MOBILITY
            fcf = revenue * margin_reported - SPGI_NCI_FCF
            notes.append("Revenue excludes Mobility; free cash flow excludes CME's 27% share of S&P Dow Jones Indices.")
        tax = TAX_CA if ccy == "CAD" else TAX_US
        op, pre = float(s["operating_income"]), float(s["pretax"])
        interest_proxy = max(0.0, op - pre)
        ufcf = fcf + interest_proxy * (1 - tax)
        margin = ufcf / revenue
        debt, cash = float(s["total_debt"]), float(s["cash"])
        ebitda = float(s["ebitda"]) if not pd.isna(s["ebitda"]) else op
        d_ebitda = debt / ebitda if ebitda > 0 else 9.9
        rf = RF_CA if ccy == "CAD" else RF_US
        mcap = float(s["market_cap"])
        beta_raw = raw_b[t]
        if t == "CBOE":
            beta_src = "stockanalysis 5-year beta (Yahoo price history unavailable)"
        else:
            _, n = beta_60m(t, idx)
            beta_src = f"{n} monthly returns vs {'S&P/TSX' if idx == 'GSPTSE' else 'S&P 500'}"
        bu = group_bu[group]
        beta_adj = bu * (1 + (1 - tax) * debt / mcap)  # relevered bottom-up beta
        spread = E.debt_spread(d_ebitda)
        wc = E.wacc(rf, beta_adj, ERP, debt, mcap, spread, tax)
        tg_c = TG_CA if ccy == "CAD" else tg
        inp = E.Inputs(revenue=revenue, fcf_margin=margin, wacc=wc["wacc"],
                       terminal_growth=tg_c, debt=debt, cash=cash, shares=shares)
        g = E.implied_growth(inp, price)
        # anchor
        win = HISTORY_WINDOWS.get(t)
        h = hist.loc[t]
        hist_cagr = None
        if win:
            col, yrs = win
            start = float(h[col])
            end = float(h["ttm"])
            hist_cagr = (end / start) ** (1 / yrs) - 1
        if t in CONSENSUS_OVERRIDE:
            cons, cons_note = CONSENSUS_OVERRIDE[t]
        else:
            cons, cons_note = float(s["rev_growth_3y"]), "Analysts' 3-year revenue CAGR forecast (stockanalysis)"
        parts = [x for x in (hist_cagr, cons) if x is not None]
        anchor = sum(parts) / len(parts)
        gap = None if g is None else g - anchor
        flag = FLAGS.get(t)
        rows.append({
            "ticker": t, "name": name, "group": group, "country": country, "currency": ccy,
            "price": price, "shares": shares, "market_cap": mcap,
            "revenue_ttm": revenue, "fcf_ttm": fcf, "ufcf_ttm": ufcf, "fcf_margin": margin,
            "debt": debt, "cash": cash, "debt_to_ebitda": d_ebitda,
            "rf": rf, "beta_raw": beta_raw, "beta_own_blume": E.blume(beta_raw),
            "beta_group_unlevered": bu, "beta_adj": beta_adj, "beta_source": beta_src,
            "erp": ERP, "ke": wc["ke"], "kd": wc["kd"], "spread": spread, "tax": tax,
            "we": wc["we"], "wd": wc["wd"], "wacc": wc["wacc"], "terminal_growth": tg_c,
            "implied_growth": g, "hist_cagr": hist_cagr, "consensus": cons,
            "consensus_note": cons_note, "anchor": anchor, "gap": gap,
            "verdict": E.verdict(gap) if not (flag and flag[0] == "Deal price") else "Deal price",
            "flag": flag[0] if flag else None, "flag_note": flag[1] if flag else None,
            "notes": " ".join(notes),
        })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "live_v1.csv"), index=False)
    print({k: round(v, 3) for k, v in group_bu.items()})
    show = df[["ticker", "price", "fcf_margin", "beta_raw", "beta_adj", "wacc", "implied_growth", "hist_cagr", "consensus", "anchor", "gap", "verdict", "flag"]].copy()
    for c in ["fcf_margin", "wacc", "implied_growth", "hist_cagr", "consensus", "anchor", "gap"]:
        show[c] = show[c].map(lambda v: "" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v*100:5.1f}%")
    show["beta_raw"] = show["beta_raw"].map(lambda v: f"{v:.2f}")
    show["beta_adj"] = show["beta_adj"].map(lambda v: f"{v:.2f}")
    show["price"] = show["price"].map(lambda v: f"{v:,.2f}")
    print(show.sort_values("gap").to_string(index=False))
    print("terminal growth", round(tg * 100, 2), "breakeven", round(BREAKEVEN * 100, 2))


if __name__ == "__main__":
    main()
