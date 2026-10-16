"""Preseason backtest for Priced In.

Question: did the names whose prices implied the least growth (relative to their
own history) beat the group over the next month?

Point in time: each month-end only uses 10-K data whose SEC filing date is on or
before that day. Prices are Yahoo monthly closes; returns use dividend-adjusted
closes. The valuation is the equity-level version of the live model (free cash
flow to equity at the cost of equity), because 15 years of clean debt data was
not available for free.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(__file__))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "out")
os.makedirs(OUT, exist_ok=True)

GROUPS = {
    "CME": "Exchanges", "ICE": "Exchanges", "NDAQ": "Exchanges", "MKTX": "Exchanges",
    "MCO": "Ratings and indexes", "MSCI": "Ratings and indexes", "MORN": "Ratings and indexes",
    "FDS": "Data and software", "BR": "Data and software", "SSNC": "Data and software",
    "EFX": "Credit data", "FICO": "Credit data",
}
EXCLUDED = {
    "SPGI": "SEC data feed returned empty for S&P Global's long filing history",
    "VRSK": "SEC data feed returned empty for Verisk",
    "TRU": "SEC data feed returned empty for TransUnion",
    "CBOE": "Yahoo rate-limited the price history request",
    "X": "TMX files in Canada (SEDAR+), with no machine-readable history",
    "TRI": "Thomson Reuters files IFRS statements without a long machine-readable history",
    "TW": "Tradeweb listed in April 2019 with LLC units held by its former parent, so a point-in-time share count is unreliable",
}
START, END = "2015-01", "2026-08"     # month-ends where portfolios are formed; last month held is Sep 2026 (the live season starts Oct 14)
N_PICKS = 5
COST = 0.001                            # 0.10% per unit of one-way turnover
TG = 0.025                              # terminal growth, capped at the risk-free rate
COVID = ("2020-02", "2021-03")          # holding months treated as the COVID window
MA_UP, MA_DOWN = 0.25, -0.20            # yearly revenue jumps treated as acquisitions/divestitures
NORMALIZED_RF = 0.025                   # normalized risk-free rate used by valuers in 2020
DEAL_FROM = {"MKTX": "2026-07"}         # ICE agreed to buy MarketAxess on Jul 30, 2026

EXPLICIT, FADE = 5, 5


def read(p):
    return pd.read_csv(p, parse_dates=["end", "filed"]) if os.path.exists(p) else None


def merge_series(t: str, names: list[str]) -> pd.DataFrame:
    """Priority merge: earlier names win for a given fiscal year end."""
    out = {}
    for n in names:
        df = read(os.path.join(RAW, "sec", t, f"{n}.csv"))
        if df is None:
            continue
        for r in df.itertuples():
            key = r.end.strftime("%Y-%m-%d")
            if key not in out:
                out[key] = (r.end, float(r.val), r.filed)
    rows = sorted(out.values(), key=lambda x: x[0])
    return pd.DataFrame(rows, columns=["end", "val", "filed"])


def split_adjust(shares: pd.DataFrame) -> pd.DataFrame:
    s = shares.sort_values("end").reset_index(drop=True).copy()
    factor = np.ones(len(s))
    for i in range(1, len(s)):
        r = s.loc[i, "val"] / s.loc[i - 1, "val"]
        k = round(r)
        if k >= 2 and abs(r - k) / k < 0.10:
            factor[:i] *= k
    s["val"] = s["val"] * factor
    return s


def fundamentals(t: str) -> pd.DataFrame:
    rev = merge_series(t, ["rev_a", "rev_c", "rev_b"])
    cfo = merge_series(t, ["cfo", "cfo_b"])
    capex = merge_series(t, ["capex"])
    sh = split_adjust(merge_series(t, ["shares"]))
    df = rev.rename(columns={"val": "revenue", "filed": "filed_rev"})
    for name, d in [("cfo", cfo), ("capex", capex), ("shares", sh)]:
        d = d.rename(columns={"val": name, "filed": f"filed_{name}"})
        df = df.merge(d, on="end", how="outer")
    df = df.sort_values("end").reset_index(drop=True)
    # capex gaps: carry the last known capex/revenue ratio forward (point-in-time safe)
    ratio = (df["capex"] / df["revenue"]).ffill()
    df["capex"] = df["capex"].fillna(ratio * df["revenue"])
    df["filed"] = df[["filed_rev", "filed_cfo"]].max(axis=1)
    df["fcfe"] = df["cfo"] - df["capex"]
    return df


def monthly(sym: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(RAW, "monthly", f"{sym}.csv"))
    df = df.groupby("month", as_index=False).last().set_index("month").sort_index()
    if "adjclose" not in df.columns:
        df["adjclose"] = df["close"]
    df["adjclose"] = df["adjclose"].fillna(df["close"])
    return df


def rates() -> pd.Series:
    # multpl monthly averages of the 10-year Treasury (data/raw/rates/ust10_monthly.csv)
    df = pd.read_csv(os.path.join(RAW, "rates", "ust10_monthly.csv"))
    return df.set_index("month")["rate"].sort_index()


def erp_for(month: str, erp_table: dict) -> float:
    y = int(month[:4])
    return erp_table.get(y - 1, erp_table[max(erp_table)])


def value_ps(r0, margin, g, gT, k, shares):
    rev, pv = r0, 0.0
    for t in range(1, EXPLICIT + FADE + 1):
        gt = g if t <= EXPLICIT else g - (g - gT) * (t - EXPLICIT) / FADE
        rev *= 1 + gt
        pv += rev * margin / (1 + k) ** t
    tv = rev * margin * (1 + gT) / (k - gT)
    pv += tv / (1 + k) ** (EXPLICIT + FADE)
    return pv / shares


def implied_g(r0, margin, gT, k, shares, price):
    if margin <= 0 or k <= gT:
        return None
    lo, hi = -0.5, 1.0
    if value_ps(r0, margin, lo, gT, k, shares) > price or value_ps(r0, margin, hi, gT, k, shares) < price:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if value_ps(r0, margin, mid, gT, k, shares) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def rolling_beta(px: pd.Series, mkt: pd.Series, month: str) -> float | None:
    r = pd.concat([px.pct_change(), mkt.pct_change()], axis=1, keys=["s", "m"]).dropna()
    r = r[r.index <= month].tail(60)
    if len(r) < 36:
        return None
    c = np.cov(r["s"], r["m"], ddof=1)
    return c[0, 1] / c[1, 1]


def covid_neutral(f: pd.DataFrame) -> pd.DataFrame:
    """Replace fiscal 2020-21 revenue and FCF margin with the 2019->2022 path."""
    g = f.copy()
    g["year"] = g["end"].dt.year
    def by_year(y):
        m = g[g["year"] == y]
        return m.index[0] if len(m) else None
    i19, i20, i21, i22 = (by_year(y) for y in (2019, 2020, 2021, 2022))
    if None in (i19, i22):
        return f
    r19, r22 = g.loc[i19, "revenue"], g.loc[i22, "revenue"]
    m19 = g.loc[i19, "fcfe"] / r19
    m22 = g.loc[i22, "fcfe"] / r22
    for i, k in ((i20, 1), (i21, 2)):
        if i is None:
            continue
        rev = r19 * (r22 / r19) ** (k / 3)
        g.loc[i, "revenue"] = rev
        g.loc[i, "fcfe"] = rev * (m19 + (m22 - m19) * k / 3)
    return g.drop(columns=["year"])


def build_panel(neutral: bool = False, normalize_rf: bool = False) -> pd.DataFrame:
    mkt = monthly("GSPC")["close"]
    rf = rates()
    erp_df = pd.read_csv(os.path.join(RAW, "rates", "damodaran_erp.csv"))
    erp_table = dict(zip(erp_df["year"], erp_df["erp"]))
    funds = {t: fundamentals(t) for t in GROUPS}
    if neutral:
        funds = {t: covid_neutral(f) for t, f in funds.items()}
    pxs = {t: monthly(t) for t in GROUPS}
    months = [m for m in mkt.index if START <= m <= END]
    rows = []
    for m in months:
        d = pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0)
        rf_m = float(rf.get(m, np.nan)) / 100
        if normalize_rf and COVID[0] <= m <= COVID[1]:
            rf_m = max(rf_m, NORMALIZED_RF)
        erp = erp_for(m, erp_table)
        betas = {}
        for t in GROUPS:
            p = pxs[t]
            if m in p.index:
                b = rolling_beta(p["adjclose"], mkt, m)
                if b is not None:
                    betas[t] = b
        group_beta = {}
        for grp in set(GROUPS.values()):
            vals = [betas[t] for t in GROUPS if GROUPS[t] == grp and t in betas]
            if vals:
                group_beta[grp] = float(np.median(vals))
        for t in GROUPS:
            if t in DEAL_FROM and m >= DEAL_FROM[t]:
                continue
            p = pxs[t]
            if m not in p.index:
                continue
            f = funds[t]
            avail = f[(f["filed"] <= d) & f["revenue"].notna() & f["fcfe"].notna() & f["shares"].notna()]
            if avail.empty:
                continue
            last = avail.iloc[-1]
            # anchor: up to 5 fiscal years of revenue CAGR, at least 3
            hist = f[(f["filed_rev"] <= d) & f["revenue"].notna()].copy()
            hist = hist[hist["end"] <= last["end"]]
            if len(hist) < 4:
                continue
            span = min(5, len(hist) - 1)
            win = hist.iloc[-1 - span:]
            yrs_total = (win.iloc[-1]["end"] - win.iloc[0]["end"]).days / 365.25
            if yrs_total < 2.5:
                continue
            growth = (win["revenue"] / win["revenue"].shift(1) - 1).dropna()
            organic = growth[(growth <= MA_UP) & (growth >= MA_DOWN)]
            if len(organic) < 2:
                continue
            anchor = float(np.prod(1 + organic) ** (1 / len(organic)) - 1)
            grp = GROUPS[t]
            if grp not in group_beta or math.isnan(rf_m):
                continue
            beta = group_beta[grp]
            ke = rf_m + beta * erp
            gT = min(TG, rf_m)
            margin = last["fcfe"] / last["revenue"]
            price = float(p.loc[m, "close"])
            g = implied_g(last["revenue"], margin, gT, ke, last["shares"], price)
            if g is None:
                continue
            rows.append({"month": m, "ticker": t, "group": grp, "price": price, "adj": float(p.loc[m, "adjclose"]),
                         "implied": g, "anchor": anchor, "gap": g - anchor, "ke": ke, "beta": beta,
                         "margin": margin, "fy_end": last["end"].strftime("%Y-%m-%d")})
    panel = pd.DataFrame(rows)
    # next-month return
    nxt = {}
    for t in GROUPS:
        p = pxs[t]["adjclose"]
        nxt[t] = p.shift(-1) / p - 1
    panel["ret_next"] = [nxt[r.ticker].get(r.month, np.nan) for r in panel.itertuples()]
    return panel


def run_portfolio(panel: pd.DataFrame) -> pd.DataFrame:
    out, prev = [], set()
    for m, grp in panel.groupby("month"):
        grp = grp.dropna(subset=["ret_next"])
        if len(grp) < 8:
            continue
        grp = grp.sort_values("gap")
        picks = grp.head(N_PICKS)
        worst = grp.tail(N_PICKS)
        cur = set(picks["ticker"])
        turnover = len(cur.symmetric_difference(prev)) / (2 * N_PICKS) if prev else 1.0
        prev = cur
        port = picks["ret_next"].mean() - COST * turnover
        bench = grp["ret_next"].mean()
        high = worst["ret_next"].mean()
        nxt_month = (pd.Period(m) + 1).strftime("%Y-%m")
        out.append({"formed": m, "held": nxt_month, "n": len(grp), "picks": ",".join(picks["ticker"]),
                    "port": port, "bench": bench, "high": high, "excess": port - bench,
                    "spread": picks["ret_next"].mean() - high})
    return pd.DataFrame(out)


def stats(res: pd.DataFrame, label: str, seed: int = 7) -> dict:
    x = res["excess"].to_numpy()
    n = len(x)
    if n == 0:
        return {"label": label, "months": 0}
    mean = x.mean()
    sd = x.std(ddof=1)
    # circular block bootstrap (6-month blocks, wrapping at the end so every month is
    # equally likely to be drawn) for a 90% interval on the annualized mean
    rng = np.random.default_rng(seed)
    B, L = 4000, 6
    boots = []
    for _ in range(B):
        idx = []
        while len(idx) < n:
            s = int(rng.integers(0, n))
            idx.extend((s + k) % n for k in range(min(L, n)))
        boots.append(x[idx[:n]].mean())
    lo, hi = np.percentile(boots, [5, 95])
    cum_p = float(np.prod(1 + res["port"]) - 1)
    cum_b = float(np.prod(1 + res["bench"]) - 1)
    yrs = n / 12
    return {
        "label": label, "months": int(n),
        "first_held": res["held"].iloc[0], "last_held": res["held"].iloc[-1],
        "excess_ann": float(mean * 12), "excess_ann_lo90": float(lo * 12), "excess_ann_hi90": float(hi * 12),
        "t_stat": float(mean / (sd / math.sqrt(n))) if sd > 0 else None,
        "hit_rate": float((x > 0).mean()),
        "port_cagr": float((1 + cum_p) ** (1 / yrs) - 1), "bench_cagr": float((1 + cum_b) ** (1 / yrs) - 1),
        "spread_ann": float(res["spread"].mean() * 12),
    }


def in_covid(held: str) -> bool:
    return COVID[0] <= held <= COVID[1]


def main():
    results = {}
    variants = [("as_reported", False, False), ("covid_neutral_fundamentals", True, False),
                ("covid_neutral_fundamentals_and_rates", True, True)]
    for tag, neutral, norm in variants:
        panel = build_panel(neutral=neutral, normalize_rf=norm)
        res = run_portfolio(panel)
        panel.to_csv(os.path.join(OUT, f"bt_panel_{tag}.csv"), index=False)
        res.to_csv(os.path.join(OUT, f"bt_months_{tag}.csv"), index=False)
        results[tag] = {
            "all_months": stats(res, "All months"),
            "ex_covid": stats(res[~res["held"].map(in_covid)], "Excluding Feb 2020 to Mar 2021"),
            "covid_only": stats(res[res["held"].map(in_covid)], "Feb 2020 to Mar 2021 only"),
            "train": stats(res[res["held"] <= "2024-12"], "2015 to 2024 (design period)"),
            "holdout": stats(res[res["held"] >= "2025-01"], "2025 to 2026 (held out)"),
        }
    results["universe"] = sorted(GROUPS)
    results["excluded"] = EXCLUDED
    results["settings"] = {"picks": N_PICKS, "cost_per_turnover": COST, "terminal_growth": TG,
                           "covid_window": COVID, "start": START, "end": END,
                           "ma_filter": [MA_UP, MA_DOWN], "normalized_rf": NORMALIZED_RF}
    json.dump(results, open(os.path.join(OUT, "backtest_results.json"), "w"), indent=2)
    for tag, _, _ in variants:
        print("==", tag)
        for k, v in results[tag].items():
            if v.get("months"):
                print(f"  {v['label']:<34} n={v['months']:>3}  excess/yr {v['excess_ann']*100:6.2f}%  "
                      f"90% [{v['excess_ann_lo90']*100:6.2f}, {v['excess_ann_hi90']*100:6.2f}]  "
                      f"t={v['t_stat']:.2f}  hit {v['hit_rate']*100:4.1f}%  port {v['port_cagr']*100:5.1f}%/yr "
                      f"bench {v['bench_cagr']*100:5.1f}%/yr  spread {v['spread_ann']*100:6.2f}%/yr")


if __name__ == "__main__":
    main()
