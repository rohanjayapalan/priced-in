"""Assemble site/data/live.json: static model inputs, slider guidance, prices,
backtest results, write-ups and sources, then run refresh.recompute()."""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import build_live as L  # noqa: E402  (constants only; main() is guarded)
import backtest as B    # noqa: E402
import refresh as R     # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "out")
SITE = os.path.join(ROOT, "site")
os.makedirs(os.path.join(SITE, "data"), exist_ok=True)

EXCHANGE = {"X": "TSX", "TW": "Nasdaq", "NDAQ": "Nasdaq", "MKTX": "Nasdaq", "MORN": "Nasdaq",
            "VRSK": "Nasdaq", "SSNC": "Nasdaq", "TRI": "NYSE and TSX", "CBOE": "Cboe BZX"}
WINDOW_LABEL = {
    ("fy2021", 4.5): "FY2021 to the 12 months ended June 2026",
    ("fy2022", 3.0): "FY2023 to FY2026 (August years)",
    ("fy2021", 4.0): "FY2022 to FY2026 (June years)",
    ("fy2021", 4.75): "FY2021 (September) to the 12 months ended June 2026",
    ("fy2022", 3.5): "FY2022 to the 12 months ended June 2026",
    ("fy2023", 2.5): "FY2023 to the 12 months ended June 2026",
}
WHY_WINDOW = {
    "FDS": "Starts after the CUSIP Global Services purchase so the window is organic.",
    "BR": "Starts after the Itiviti purchase so the window is organic.",
    "TRU": "Starts after the Neustar purchase so the window is organic.",
    "VRSK": "Starts after Verisk sold its non-insurance units so the window is like for like.",
}


def pct(x, nd=1):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x*100:.{nd}f}%"


def pts(x, nd=1):
    return f"{x*100:+.{nd}f} points"


def margin_history(t):
    """FCF (CFO - capex) / revenue for the last five fiscal years from SEC filings."""
    if not os.path.isdir(os.path.join(ROOT, "data", "raw", "sec", t)):
        return []
    try:
        f = B.fundamentals(t)
    except Exception:
        return []
    f = f.dropna(subset=["revenue", "fcfe"])
    f = f[f["revenue"] > 0].tail(5)
    return [(r.end.strftime("%Y"), float(r.fcfe / r.revenue)) for r in f.itertuples()]


def nan_none(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return x


def build_companies(live, lock):
    comps = {}
    for r in live.itertuples():
        t = r.ticker
        inputs = {"revenue": r.revenue_ttm, "fcf_margin": r.fcf_margin, "wacc": r.wacc,
                  "terminal_growth": r.terminal_growth, "debt": r.debt, "cash": r.cash,
                  "shares": r.shares, "minority": 0.0}
        hist = nan_none(r.hist_cagr)
        win = L.HISTORY_WINDOWS.get(t)
        flag = None if pd.isna(r.flag) else {"label": r.flag, "note": r.flag_note}
        # ---- slider guidance -------------------------------------------------
        # WACC: model value; zone spans own-beta WACC and ERP +/- 0.5 points
        def wacc_with(beta, erp):
            ke = r.rf + beta * erp
            return r.we * ke + r.wd * r.kd * (1 - r.tax)
        own = wacc_with(r.beta_own_blume, r.erp)
        lo_erp = wacc_with(r.beta_adj, r.erp - 0.005)
        hi_erp = wacc_with(r.beta_adj, r.erp + 0.005)
        wz = [min(own, lo_erp, hi_erp, r.wacc), max(own, lo_erp, hi_erp, r.wacc)]
        wacc_why = (f"I use the {r.group.lower()} group's median unlevered beta ({r.beta_group_unlevered:.2f}), "
                    f"relevered for this company's debt to {r.beta_adj:.2f}. The shaded zone runs from "
                    f"{pct(wz[0])} to {pct(wz[1])}: its own 60-month beta ({r.beta_own_blume:.2f} after Blume) and an "
                    f"equity risk premium half a point either side of {pct(r.erp, 2)}.")
        # terminal growth
        if r.currency == "CAD":
            tz = [0.020, 0.030]
            tg_why = ("Canadian names use 2.5%: the Bank of Canada's 2% inflation target plus half a point of real growth. "
                      "The zone is 2% (inflation only) to 3%.")
        else:
            be = L.BREAKEVEN
            tz = [round(be, 4), round(be + 0.01, 4)]
            tg_why = (f"US names use {pct(r.terminal_growth, 2)}: 10-year breakeven inflation ({pct(be, 2)}) plus half a point "
                      f"of real growth, capped at the risk-free rate. The zone runs from inflation alone to one point above it.")
        # FCF margin
        mh = margin_history(t)
        fcfe_now = r.fcf_ttm / r.revenue_ttm
        add_back = r.fcf_margin - fcfe_now
        if len(mh) >= 3:
            vals = [m + add_back for _y, m in mh]
            mz = [min(vals + [r.fcf_margin]), max(vals + [r.fcf_margin])]
            m_why = (f"The model holds the trailing unlevered margin ({pct(r.fcf_margin)}). The zone is the range over "
                     f"fiscal {mh[0][0]} to {mh[-1][0]} from SEC filings, with today's interest add-back so the years compare.")
        else:
            mz = [r.fcf_margin - 0.03, r.fcf_margin + 0.03]
            m_why = (f"The model holds the trailing unlevered margin ({pct(r.fcf_margin)}). I don't have five clean years of "
                     f"cash flow for this name, so the zone is three points either side.")
        # your view of growth
        parts = [x for x in (hist, r.consensus) if x is not None]
        vz = [min(parts), max(parts)]
        if hist is None:
            v_why = (f"The recommended spot is my anchor, {pct(r.anchor)}, which here is the analysts' forecast alone "
                     f"because past growth isn't comparable. Move it to see what the stock is worth if you're right.")
        else:
            v_why = (f"The recommended spot is my anchor, {pct(r.anchor)}: the average of past growth ({pct(hist)}) and "
                     f"the analysts' forecast ({pct(r.consensus)}). The zone spans the two. Move it to see what the stock "
                     f"is worth if you're right.")
        sliders = {
            "wacc": {"min": round(max(0.04, r.wacc - 0.03), 4), "max": round(r.wacc + 0.03, 4), "step": 0.0005,
                     "rec": r.wacc, "zone": wz, "why": wacc_why},
            "tg": {"min": 0.0, "max": round(min(0.04, r.wacc - 0.01), 4), "step": 0.0005,
                   "rec": r.terminal_growth, "zone": tz, "why": tg_why},
            "margin": {"min": round(max(0.02, r.fcf_margin - 0.15), 4), "max": round(min(0.9, r.fcf_margin + 0.15), 4),
                       "step": 0.0025, "rec": r.fcf_margin, "zone": mz, "why": m_why,
                       "history": [[y, round(m + add_back, 4)] for y, m in mh]},
            "view": {"min": -0.05, "max": 0.25, "step": 0.0025, "rec": r.anchor, "zone": vz, "why": v_why},
        }
        lk = lock["universe_gaps"].get(t)
        comps[t] = {
            "ticker": t, "name": r.name, "group": r.group, "country": r.country, "currency": r.currency,
            "exchange": EXCHANGE.get(t, "NYSE"),
            "inputs": inputs,
            "wacc_build": {
                "rf": r.rf, "rf_source": "10-year Government of Canada bond" if r.currency == "CAD" else "10-year US Treasury",
                "erp": r.erp, "beta_raw": r.beta_raw, "beta_own_blume": r.beta_own_blume,
                "beta_group_unlevered": r.beta_group_unlevered, "beta_adj": r.beta_adj, "beta_source": r.beta_source,
                "ke": r.ke, "kd": r.kd, "spread": r.spread, "tax": r.tax, "we": r.we, "wd": r.wd,
                "debt_to_ebitda": r.debt_to_ebitda, "market_cap": r.market_cap,
            },
            "fcf_build": {"fcf_ttm": r.fcf_ttm, "ufcf_ttm": r.ufcf_ttm, "interest_add_back": r.ufcf_ttm - r.fcf_ttm,
                          "notes": "" if pd.isna(r.notes) else r.notes},
            "anchor": {"hist_cagr": hist, "hist_window": WINDOW_LABEL.get(win) if win else None,
                       "hist_note": WHY_WINDOW.get(t), "consensus": r.consensus, "consensus_note": r.consensus_note,
                       "anchor": r.anchor},
            "flag": flag,
            "sliders": sliders,
            "lock": {"date": "2026-10-13", "price": r.price, "implied": r.implied_growth, "gap": lk,
                     "verdict": r.verdict},
        }
    return comps


def load_prices():
    out = {}
    for t in L.COMPANIES:
        rows = []
        with open(os.path.join(ROOT, "data", "raw", "daily", f"{t}.csv")) as fh:
            for d in csv.DictReader(fh):
                rows.append([d["date"], float(d["close"]), int(d["volume"])])
        out[t] = rows
    return out


def build_backtest():
    res = json.load(open(os.path.join(OUT, "backtest_results.json")))
    nf = json.load(open(os.path.join(OUT, "backtest_nofilter.json")))
    variants = {}
    for tag, label in [("as_reported", "As reported"),
                       ("covid_neutral_fundamentals", "COVID-neutral fundamentals"),
                       ("covid_neutral_fundamentals_and_rates", "COVID-neutral fundamentals and rates")]:
        m = pd.read_csv(os.path.join(OUT, f"bt_months_{tag}.csv"))
        cum_p, cum_b = 1.0, 1.0
        series = []
        for x in m.itertuples():
            cum_p *= 1 + x.port
            cum_b *= 1 + x.bench
            series.append([x.held, round(x.port, 5), round(x.bench, 5), round(x.excess, 5), x.picks,
                           round(cum_p, 4), round(cum_b, 4)])
        variants[tag] = {"label": label, "stats": res[tag], "months": series}
    nfm = pd.read_csv(os.path.join(OUT, "bt_months_no_filter.csv"))
    return {
        "variants": variants,
        "no_filter": {"label": "As reported, without the acquisition filter", "stats": nf},
        "universe": res["universe"], "excluded": res["excluded"], "settings": res["settings"],
        "covid_window": ["2020-02", "2021-03"],
        "notes": [
            "Each month I value every company with only the filings public by that month-end, at that month-end's price.",
            "The backtest values equity directly: cash flow from operations minus capex, discounted at the cost of equity. "
            "It needs fewer inputs than the live model; on today's data the two rank the names almost identically "
            "(Spearman rank correlation 0.965).",
            "The anchor is past revenue growth only (there is no free archive of old analyst forecasts), using years with "
            "growth between -20% and +25% so acquisitions don't count as growth.",
            "Five names with the most negative gap are held for a month, equal weight, against an equal-weight portfolio of "
            "every name, with 0.10% charged on each unit of turnover.",
            "COVID: Feb 2020 to Mar 2021 is reported separately. Variant two replaces fiscal 2020-21 revenue and margins with "
            "a straight line from 2019 to 2022. Variant three also floors the risk-free rate at 2.5% in that window, the "
            "normalized rate Kroll recommended from June 30, 2020.",
            "The 90% ranges come from a circular block bootstrap: 4,000 reshuffles of 6-month blocks of the monthly results, "
            "wrapping at the end so every month is equally likely to be drawn. With only 14 COVID months, read that window's "
            "range as a direction, not a size.",
        ],
    }


def build_writeups(comps):
    def c(t):
        return comps[t]

    def sens(t, dw):
        inp = dict(c(t)["inputs"])
        inp["wacc"] += dw
        return R.implied_growth(inp, c(t)["lock"]["price"])

    x, cb, tw = c("X"), c("CBOE"), c("TW")
    body = [
        {"ticker": "X", "title": "TMX Group: the gap is real, but part of it is purchased revenue",
         "paras": [
             f"At the lock, the price implied {pct(x['lock']['implied'])} a year of revenue growth for five years. "
             f"My anchor is {pct(x['anchor']['anchor'])}, which is the analysts' three-year forecast on its own: TMX's past "
             f"growth isn't comparable because VettaFi was consolidated in 2024 and TMX bought Cboe Australia this August.",
             f"That forecast includes revenue TMX bought, so the organic gap is narrower than the {abs(x['lock']['gap'])*100:.1f} points shown. "
             f"The discount rate matters too. TMX's cost of capital is low at {pct(x['inputs']['wacc'])} because Canadian "
             f"rates are low. At one point higher, implied growth rises to {pct(sens('X', 0.01))}.",
             "What would prove me wrong: organic revenue growth below about 5% in the next two quarterly reports, or a "
             "pending deal falling apart.",
         ]},
        {"ticker": "CBOE", "title": "Cboe: priced for shrinking net revenue",
         "paras": [
             f"At the lock, the price implied net revenue falling {pct(-cb['lock']['implied'])} a year for five years. My "
             f"anchor is {pct(cb['anchor']['anchor'])}: past net revenue growth of {pct(cb['anchor']['hist_cagr'])} and a "
             f"forward estimate of {pct(cb['anchor']['consensus'])}.",
             "Two things make me cautious. Options volumes swing with volatility, so a few busy years can flatter past "
             "growth. And Cboe is selling Cboe Australia and Cboe Canada to TMX, which shrinks revenue. "
             f"Trailing free cash flow is {pct(cb['inputs']['fcf_margin'])} of net revenue, above operating margin, so "
             "some of it may be timing. If that margin is too high, implied growth is understated.",
             "What would prove me wrong: net revenue falling in the next two quarters once the sale closes.",
         ]},
        {"ticker": "TW", "title": "Tradeweb: a growth platform priced like a utility",
         "paras": [
             f"At the lock, the price implied {pct(tw['lock']['implied'])} a year of revenue growth. Tradeweb grew "
             f"{pct(tw['anchor']['hist_cagr'])} a year from fiscal 2021, and analysts expect {pct(tw['anchor']['consensus'])}. "
             f"My anchor, the average, is {pct(tw['anchor']['anchor'])}.",
             "The market may be pricing slower bond and rates trading volumes and fee pressure, and past growth includes "
             "bolt-on purchases. But Tradeweb has net cash and a "
             f"{pct(tw['inputs']['fcf_margin'])} free-cash-flow margin. Even at a cost of capital one point higher "
             f"({pct(tw['inputs']['wacc'] + 0.01)}), implied growth is only {pct(sens('TW', 0.01))}.",
             "What would prove me wrong: average daily volume falling year over year for two quarters in a row.",
         ]},
    ]
    return [{
        "id": "season-1-opener",
        "date": "2026-10-14",
        "title": "Season 1 opener: the three biggest gaps",
        "dek": "Why the screen likes TMX, Cboe and Tradeweb, and what would make me wrong. Written at the lock, before the first close.",
        "items": body,
    }]


SOURCES = [
    {"group": "Prices and fundamentals", "items": [
        {"title": "Stock Analysis: statistics, financials and daily price history", "url": "https://stockanalysis.com/stocks/mco/statistics/", "note": "Market caps, shares, trailing revenue and cash flow, analyst forecasts, daily prices. One page per company; Moody's shown."},
        {"title": "Yahoo Finance: monthly and daily price history", "url": "https://finance.yahoo.com/quote/MCO/history/", "note": "60-month returns for betas, and the backtest's monthly prices. Moody's shown."},
        {"title": "SEC EDGAR XBRL company concepts", "url": "https://data.sec.gov/api/xbrl/companyconcept/CIK0000059858/us-gaap/Revenues.json", "note": "Point-in-time revenue, operating cash flow, capex and shares with filing dates, for the backtest. Moody's revenue shown."},
        {"title": "S&P Global recast financials without Mobility (8-K/A exhibit 99.1)", "url": "https://www.sec.gov/Archives/edgar/data/0000064040/000110465926080571/tm2619099d2_ex99-1.htm", "note": "Revenue base for S&P Global after the spin-off."},
    ]},
    {"group": "Rates and risk premium", "items": [
        {"title": "US Treasury daily par yield curve rates", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month=202610", "note": "10-year Treasury, 5.21% on Oct 13, 2026."},
        {"title": "US Treasury daily real yield curve rates", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve&field_tdr_date_value_month=202610", "note": "10-year TIPS real yield, 2.88% on Oct 13, 2026; breakeven inflation = 5.21% - 2.88%."},
        {"title": "Bank of Canada Valet: 10-year benchmark bond yield", "url": "https://www.bankofcanada.ca/valet/observations/BD.CDN.10YR.DQ.YLD/json?recent=3", "note": "3.87% on Oct 13, 2026."},
        {"title": "Damodaran: implied equity risk premiums", "url": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histimpl.html", "note": "4.23% at the start of 2026; earlier years for the backtest."},
        {"title": "Kroll: US normalized risk-free rate lowered to 2.5% (June 30, 2020)", "url": "https://www.kroll.com/en/reports/cost-of-capital/us-normalized-risk-free-rate-lowered-june-30-2020", "note": "Basis for the COVID rates variant."},
    ]},
    {"group": "Company events", "items": [
        {"title": "ICE to acquire MarketAxess", "url": "https://ir.theice.com/press/news-details/2026/Intercontinental-Exchange-to-Acquire-MarketAxess-Creating-a-Premier-Fixed-Income-Marketplace/default.aspx", "note": "Why MarketAxess carries the deal-price flag."},
        {"title": "MarketAxess definitive proxy (DEFM14A)", "url": "https://www.sec.gov/Archives/edgar/data/0001278021/000119312526395678/d171374ddefm14a.htm", "note": "Shareholder vote on the ICE deal."},
        {"title": "Cboe agrees to sell Cboe Australia and Cboe Canada to TMX", "url": "https://ir.cboe.com/news/news-details/2026/Cboe-Announces-Agreement-to-Sell-Cboe-Australia-and-Cboe-Canada-to-TMX-Group-2026-sskiJDRRf-/default.aspx", "note": "Affects both Cboe's and TMX's revenue base."},
        {"title": "The TRADE: TMX closes Cboe Australia acquisition", "url": "https://www.thetradenews.com/tmx-group-closes-cboe-australia-acquisition/", "note": "Why TMX's history isn't comparable."},
        {"title": "S&P Global completes separation of Mobility", "url": "https://press.spglobal.com/2026-07-01-S-P-GLOBAL-INC-COMPLETES-SEPARATION-OF-MOBILITY-GLOBAL-INC", "note": "Why S&P's history isn't comparable."},
        {"title": "The Motley Fool: why Fair Isaac plunged (Sept 29, 2026)", "url": "https://www.fool.com/investing/2026/09/29/why-fair-isaac-corporation-plunged-today/", "note": "Context for FICO's move into the screen."},
    ]},
    {"group": "Method", "items": [
        {"title": "CFA Institute: book review of Expectations Investing (Mauboussin and Rappaport)", "url": "https://rpc.cfainstitute.org/blogs/enterprising-investor/2022/book-review-expectations-investing", "note": "The idea behind the site: read the expectations in the price, then judge them."},
        {"title": "Damodaran: spreadsheets (synthetic ratings, cost of capital)", "url": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm", "note": "Background for the debt-spread table and bottom-up betas."},
    ]},
]

EVENTS = [
    {"ticker": "MKTX", "date": "2026-10-29", "kind": "Shareholder vote", "label": "MarketAxess holders vote on the ICE deal",
     "url": "https://www.sec.gov/Archives/edgar/data/0001278021/000119312526395678/d171374ddefm14a.htm"},
]

INPLAY_RULES = [
    {"kind": "Price shock", "rule": "A daily move at least 3 times the stock's normal daily move (a robust standard deviation of the prior 49 days)."},
    {"kind": "Volume spike", "rule": "Daily volume at least 3 times the average of the prior 50 days."},
    {"kind": "Implied-growth swing", "rule": "Implied growth moves at least 2 points over 5 trading days."},
    {"kind": "Dated event", "rule": "A deal, vote, results day or management change I log with a source."},
    {"kind": "Decay", "rule": "Each signal fades by 15% a trading day, so a name stays in play for about a week unless something new happens."},
]


def main():
    live = pd.read_csv(os.path.join(OUT, "live_v1.csv"))
    lock = json.load(open(os.path.join(OUT, "season_v1_lock.json")))
    comps = build_companies(live, lock)
    state = {
        "meta": {
            "site": "Priced In", "model_version": "1.0", "locked_at_utc": lock["locked_at_utc"],
            "lock_commit": "0735af0", "data_as_of_close": lock["data_as_of_close"],
            "rf_us": L.RF_US, "rf_ca": L.RF_CA, "real_10y": L.REAL_10Y, "breakeven": L.BREAKEVEN,
            "erp": L.ERP, "tax_us": L.TAX_US, "tax_ca": L.TAX_CA, "tg_us": min(L.BREAKEVEN + 0.005, L.RF_US),
            "tg_ca": L.TG_CA, "verdict_band": 0.03, "explicit_years": 5, "fade_years": 5,
            "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "companies": comps,
        "prices": load_prices(),
        "events": EVENTS,
        "inplay": {"rules": INPLAY_RULES},
        "season": {
            "name": "Season 1", "start": "2026-10-14", "locked_at_utc": lock["locked_at_utc"], "commit": "0735af0",
            "entry_rule": lock["entry_rule"], "rebalance_rule": lock["rebalance_rule"], "benchmark": lock["benchmark"],
            "picks": lock["picks"],
        },
        "backtest": build_backtest(),
        "writeups": build_writeups(comps),
        "sources": SOURCES,
    }
    R.recompute(state)
    path = os.path.join(SITE, "data", "live.json")
    json.dump(state, open(path, "w"), separators=(",", ":"))
    print("wrote", path, os.path.getsize(path), "bytes")
    ip = state["inplay"]
    for r in ip["ranking"][:6]:
        print(f"  {r['ticker']:5} {r['score']:.2f}  " + " | ".join(x["text"] for x in r["reasons"]))
    for t, c in sorted(state["companies"].items(), key=lambda kv: kv[1]["live"]["gap"] or 0):
        lv = c["live"]
        print(f"  {t:5} {lv['date']} px {lv['price']:>8.2f} impl {pct(lv['implied'])} gap {pct(lv['gap'])} {lv['verdict']}")
    for w in state["writeups"][0]["items"]:
        print("\n" + w["title"]); [print("  " + p) for p in w["paras"]]


if __name__ == "__main__":
    main()
