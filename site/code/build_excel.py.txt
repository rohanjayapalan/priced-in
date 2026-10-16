"""Build one live-formula Excel model per company (model v1.0, lock inputs).

Tabs: Cover, Inputs, History, WACC, Solver, DCF, Sensitivity, Check.
Blue = typed inputs, black = formulas, green = links to another sheet,
yellow fill = the one cell meant for your own view.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import refresh as R  # noqa: E402

ROOT = os.path.dirname(HERE)
SITE_URL = os.environ.get("PRICED_IN_URL", "")
OUTDIR = os.path.join(ROOT, "site", "models")
os.makedirs(OUTDIR, exist_ok=True)

ARIAL = "Arial"
BLUE, BLACK, GREEN, GREY, WHITE = "0000FF", "000000", "008000", "666666", "FFFFFF"
NAVY = "1F3A5F"
F_IN = Font(name=ARIAL, size=10, color=BLUE)
F_FX = Font(name=ARIAL, size=10, color=BLACK)
F_LK = Font(name=ARIAL, size=10, color=GREEN)
F_LB = Font(name=ARIAL, size=10, color=BLACK)
F_NOTE = Font(name=ARIAL, size=9, color=GREY, italic=True)
F_HEAD = Font(name=ARIAL, size=10, bold=True, color=WHITE)
F_SEC = Font(name=ARIAL, size=11, bold=True, color=NAVY)
F_TITLE = Font(name=ARIAL, size=16, bold=True, color=NAVY)
F_SUB = Font(name=ARIAL, size=10, color=GREY)
F_BOLD = Font(name=ARIAL, size=10, bold=True)
FILL_HEAD = PatternFill("solid", fgColor=NAVY)
FILL_YEL = PatternFill("solid", fgColor="FFFF00")
FILL_KEY = PatternFill("solid", fgColor="EEF3F8")
THIN = Side(style="thin", color="BBBBBB")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)

MM = '#,##0;(#,##0);"-"'
MM1 = '#,##0.0;(#,##0.0);"-"'
PCT = '0.0%;(0.0%);"-"'
PCT2 = '0.00%;(0.00%);"-"'
BETA = '0.00;(0.00);"-"'
MULT = '0.0"x"'

COLS = ["fy2021", "fy2022", "fy2023", "fy2024", "fy2025", "ttm"]
LABELS_DEFAULT = ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "TTM Jun-26"]
LABELS = {
    "FDS": ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026", "TTM (= FY2026)"],
    "BR": ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026", "TTM (= FY2026)"],
}
WINDOW_START = {  # column used as the start of the history window, and years to TTM
    "MCO": ("fy2021", 4.5), "MSCI": ("fy2021", 4.5), "CME": ("fy2021", 4.5), "CBOE": ("fy2021", 4.5),
    "TW": ("fy2021", 4.5), "MKTX": ("fy2021", 4.5), "MORN": ("fy2021", 4.5), "TRI": ("fy2021", 4.5),
    "SSNC": ("fy2021", 4.5), "EFX": ("fy2021", 4.5), "FDS": ("fy2022", 3.0), "BR": ("fy2021", 4.0),
    "FICO": ("fy2021", 4.75), "TRU": ("fy2022", 3.5), "VRSK": ("fy2023", 2.5),
}


def put(ws, ref, value, kind="fx", fmt=None, bold=False, note=None):
    c = ws[ref]
    c.value = value
    font = {"in": F_IN, "fx": F_FX, "lk": F_LK, "lb": F_LB, "note": F_NOTE, "sec": F_SEC,
            "title": F_TITLE, "sub": F_SUB, "bold": F_BOLD}[kind]
    if bold and kind in ("in", "fx", "lk", "lb"):
        font = Font(name=ARIAL, size=10, bold=True, color=font.color)
    c.font = font
    if fmt:
        c.number_format = fmt
    if note:
        nc = ws.cell(row=c.row, column=c.column + 2 if c.column == 3 else c.column + 1)
        nc.value = note
        nc.font = F_NOTE
    return c


def header_row(ws, row, labels, start_col=2):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=lab)
        c.font = F_HEAD
        c.fill = FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def load_csv(path, key="ticker"):
    with open(path) as fh:
        return {r[key]: r for r in csv.DictReader(fh)}


def fnum(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def build(t, state, stats, revhist):
    c = state["companies"][t]
    meta = state["meta"]
    s = stats[t]
    inp, wb_, an = c["inputs"], c["wacc_build"], c["anchor"]
    ccy = "C$" if c["currency"] == "CAD" else "$"
    mm = f"({ccy}mm)"
    ps_fmt = f'"{ccy}"#,##0.00;("{ccy}"#,##0.00);"-"'
    us = c["currency"] != "CAD"

    wb = Workbook()
    cov = wb.active
    cov.title = "Cover"
    wi = wb.create_sheet("Inputs")
    hi = wb.create_sheet("History")
    wa = wb.create_sheet("WACC")
    so = wb.create_sheet("Solver")
    dc = wb.create_sheet("DCF")
    se = wb.create_sheet("Sensitivity")
    ck = wb.create_sheet("Check")
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False

    # ------------------------------------------------------------------ Inputs
    widths(wi, {"A": 2, "B": 50, "C": 14, "D": 2, "E": 90})
    put(wi, "B2", f"{c['name']} ({t}): inputs", "title")
    put(wi, "B3", "Blue cells are typed inputs with a source. Black cells are formulas. Change a blue cell and every tab recalculates.", "sub")
    I = {}

    def irow(r, label, value, kind, fmt, note=None, key=None, fill=None):
        put(wi, f"B{r}", label, "lb")
        cell = put(wi, f"C{r}", value, kind, fmt)
        if fill:
            cell.fill = fill
        if note:
            put(wi, f"E{r}", note, "note")
        if key:
            I[key] = f"Inputs!$C${r}"
        return cell

    put(wi, "B5", "Market and price", "sec")
    price_note = "Market cap divided by shares from Stock Analysis at the Oct 13, 2026 close."
    if t == "X":
        price_note += " The TSX close that day was C$53.22; the lock used C$54.50."
    irow(6, f"Price per share at the lock ({ccy})", c["lock"]["price"], "in", ps_fmt, price_note, "price")
    irow(7, "Diluted shares outstanding (mm)", inp["shares"] / 1e6, "in", MM1, "Stock Analysis statistics page, Oct 13, 2026.", "shares")
    irow(8, f"Market value of equity {mm}", "=C6*C7", "fx", MM, "Price x shares.", "mcap")

    put(wi, "B10", "Trailing 12 months", "sec")
    rev_rep = fnum(s["revenue"]) / 1e6
    irow(11, f"Revenue, reported {mm}", rev_rep, "in", MM, "Stock Analysis income statement, trailing 12 months.", "rev_rep")
    if t == "SPGI":
        irow(12, f"Revenue used in the model {mm}", inp["revenue"] / 1e6, "in", MM,
             "S&P Global recast without Mobility (8-K/A exhibit 99.1): Q3'25 3,443 + Q4'25 3,472 + Q1'26 3,717 + Q2'26 est. 3,685.", "rev")
    elif t == "CBOE":
        irow(12, f"Revenue used in the model: net revenue {mm}", inp["revenue"] / 1e6, "in", MM,
             "Revenue less cost of revenue (rebates, routing and clearing fees), from Stock Analysis.", "rev")
    else:
        irow(12, f"Revenue used in the model {mm}", "=C11", "fx", MM, "Same as reported.", "rev")
    irow(13, f"Free cash flow, reported (cash from operations - capex) {mm}", fnum(s["fcf"]) / 1e6, "in", MM,
         "Stock Analysis cash flow statement, trailing 12 months.", "fcf_rep")
    if t == "SPGI":
        irow(14, f"Free cash flow scaled to revenue used {mm}", "=C12*C13/C11", "fx", MM,
             "Holds the reported free-cash-flow margin on the smaller revenue base.")
        irow(15, f"Less: CME's 27% share of S&P Dow Jones Indices cash flow {mm}", 320, "in", MM,
             "Estimate: the index business's cash flow times CME's 27% minority stake.")
    else:
        irow(14, f"Free cash flow before adjustments {mm}", "=C13", "fx", MM, "Same as reported.")
        irow(15, f"Less: adjustments {mm}", 0, "in", MM, "None for this company.")
    irow(16, f"Free cash flow used {mm}", "=C14-C15", "fx", MM, None, "fcf")
    irow(17, f"Operating income {mm}", fnum(s["operating_income"]) / 1e6, "in", MM, "Stock Analysis, trailing 12 months.", "oi")
    irow(18, f"Pretax income {mm}", fnum(s["pretax"]) / 1e6, "in", MM, "Stock Analysis, trailing 12 months.", "pti")
    irow(19, f"Interest proxy: operating income - pretax, floored at zero {mm}", "=MAX(0,C17-C18)", "fx", MM,
         "Net interest and other non-operating costs. Adding it back (after tax) turns levered FCF into unlevered FCF.")
    irow(20, "Tax rate", inp and wb_["tax"], "in", PCT,
         "Statutory blend: 25% US (21% federal plus state), 26.5% Canada (federal plus Ontario).", "tax")
    irow(21, f"After-tax interest added back {mm}", "=C19*(1-C20)", "fx", MM)
    irow(22, f"Unlevered free cash flow {mm}", "=C16+C21", "fx", MM, None, "ufcf")
    irow(23, "Unlevered free-cash-flow margin", "=C22/C12", "fx", PCT, "Held flat for all 10 years in the model.", "margin")
    ebitda = fnum(s["ebitda"])
    if ebitda is None:
        irow(24, f"EBITDA {mm}", "=C17", "fx", MM, "Not reported by the source; operating income used.", "ebitda")
    else:
        irow(24, f"EBITDA {mm}", ebitda / 1e6, "in", MM, "Stock Analysis, trailing 12 months.", "ebitda")

    put(wi, "B26", "Balance sheet", "sec")
    irow(27, f"Total debt {mm}", inp["debt"] / 1e6, "in", MM, "Stock Analysis balance sheet, latest quarter.", "debt")
    irow(28, f"Cash and equivalents {mm}", inp["cash"] / 1e6, "in", MM, "Stock Analysis balance sheet, latest quarter.", "cash")
    irow(29, f"Net debt {mm}", "=C27-C28", "fx", MM)

    put(wi, "B31", "Rates", "sec")
    if us:
        irow(32, "10-year US Treasury yield", meta["rf_us"], "in", PCT2, "US Treasury daily par yield curve, Oct 13, 2026.", "y10")
        irow(33, "10-year TIPS real yield", meta["real_10y"], "in", PCT2, "US Treasury daily real yield curve, Oct 13, 2026.", "real")
        irow(34, "Breakeven inflation", "=C32-C33", "fx", PCT2, "Nominal minus real: the market's inflation expectation.")
    else:
        irow(32, "10-year Government of Canada yield", meta["rf_ca"], "in", PCT2, "Bank of Canada Valet, Oct 13, 2026.", "y10")
        irow(33, "Inflation target", 0.02, "in", PCT2, "Bank of Canada 2% target.", "real")
        irow(34, "Inflation used", "=C33", "fx", PCT2)
    irow(35, "Risk-free rate used", "=C32", "fx", PCT2, None, "rf")
    irow(36, "Real growth added to inflation", 0.005, "in", PCT2, "Half a point of long-run real growth.")
    if us:
        irow(37, "Terminal growth", "=MIN(C34+C36,C35)", "fx", PCT2, "Capped at the risk-free rate.", "tg")
    else:
        irow(37, "Terminal growth", "=C34+C36", "fx", PCT2, None, "tg")
    irow(38, "Equity risk premium", meta["erp"], "in", PCT2, "Damodaran implied equity risk premium, start of 2026.", "erp")

    put(wi, "B40", "Growth anchor and verdict", "sec")
    if an["hist_cagr"] is not None:
        irow(41, "Past revenue growth (CAGR)", "=History!$C$12", "lk", PCT, an["hist_window"] or "", "hist")
    else:
        irow(41, "Past revenue growth (CAGR)", "n/a", "fx", None, "Not used: past growth isn't comparable (see Cover).", "hist")
    irow(42, "Analysts' revenue growth forecast", an["consensus"], "in", PCT, an["consensus_note"], "cons")
    irow(43, "Anchor (average of the two)", "=AVERAGE(C41:C42)", "fx", PCT, "AVERAGE skips the n/a text when history isn't used.", "anchor")
    irow(44, "Verdict band (+/-)", 0.03, "in", PCT, "Set before any backtest and never changed.", "band")
    irow(45, "Your view of 5-year revenue growth", an["anchor"], "in", PCT,
         "Type your own view. It starts at the anchor. DCF panel B and the Cover show what the stock is worth at your view.",
         "view", FILL_YEL)
    irow(46, "Years at the solved growth rate", 5, "in", '0', "Model v1.0: 5 years at the growth rate, then a straight-line fade.", "yrs")
    irow(47, "Years of fade to terminal growth", 5, "in", '0', "Years 1 to 10 are on the Solver and DCF tabs; years past 10 grow at the terminal rate.", "fade")

    # ------------------------------------------------------------------ History
    widths(hi, {"A": 2, "B": 34, "C": 13, "D": 13, "E": 13, "F": 13, "G": 13, "H": 16, "I": 60})
    put(hi, "B2", f"{c['name']} ({t}): revenue history", "title")
    put(hi, "B3", "Revenue from Stock Analysis income statements; the window is chosen so acquisitions and disposals don't count as growth.", "sub")
    labels = LABELS.get(t, LABELS_DEFAULT)
    header_row(hi, 5, ["Fiscal year"] + labels)
    row = revhist[t]
    put(hi, "B6", f"Revenue {mm}", "lb")
    for i, col in enumerate(COLS):
        put(hi, f"{get_column_letter(3 + i)}6", fnum(row[col]), "in", MM)
    put(hi, "B7", "Growth on the prior year", "lb")
    for i in range(1, 5):
        L = get_column_letter(3 + i)
        P = get_column_letter(2 + i)
        put(hi, f"{L}7", f"={L}6/{P}6-1", "fx", PCT)
    if row.get("note"):
        put(hi, "B8", "Source note: " + row["note"], "note")
    put(hi, "B10", "History window", "sec")
    if t in WINDOW_START:
        col, yrs = WINDOW_START[t]
        lab = labels[COLS.index(col)]
        put(hi, "B11", "Start year", "lb")
        put(hi, "C11", lab, "in")
        put(hi, "E11", "Years from start to TTM", "lb")
        put(hi, "G11", yrs, "in", '0.00')
        put(hi, "B12", "Revenue CAGR, start to TTM", "lb")
        put(hi, "C12", f"=(H6/INDEX(C6:H6,MATCH(C11,C5:H5,0)))^(1/G11)-1", "fx", PCT)
        put(hi, "I12", (an["hist_window"] or "") + (". " + an["hist_note"] if an.get("hist_note") else ""), "note")
    else:
        put(hi, "B11", "Not used for this company: " + (c["flag"]["note"] if c.get("flag") else ""), "note")
    mh = c["sliders"]["margin"].get("history") or []
    if mh:
        add_back = inp["fcf_margin"] - c["fcf_build"]["fcf_ttm"] / inp["revenue"]
        put(hi, "B15", "Free-cash-flow margin history", "sec")
        header_row(hi, 16, ["Fiscal year"] + [y for y, _m in mh])
        put(hi, "B17", "(CFO - capex) / revenue", "lb")
        put(hi, "B18", "Plus today's interest add-back", "lb")
        for i, (y, m) in enumerate(mh):
            L = get_column_letter(3 + i)
            put(hi, f"{L}17", round(m - add_back, 4), "in", PCT)
            put(hi, f"{L}18", f"={L}17+(Inputs!$C$23-Inputs!$C$16/Inputs!$C$12)", "fx", PCT)
        last = get_column_letter(2 + len(mh))
        put(hi, "B19", "Range (the margin slider's shaded zone)", "lb")
        put(hi, "C19", f"=MIN(C18:{last}18)", "fx", PCT)
        put(hi, "D19", f"=MAX(C18:{last}18)", "fx", PCT)
        put(hi, "I17", "SEC XBRL filings (NetCashProvidedByOperatingActivities, PaymentsToAcquirePropertyPlantAndEquipment, revenue tags).", "note")

    # ------------------------------------------------------------------ WACC
    widths(wa, {"A": 2, "B": 40, "C": 14, "D": 14, "E": 14, "F": 14, "G": 14, "H": 60})
    put(wa, "B2", f"{c['name']} ({t}): cost of capital", "title")
    put(wa, "B3", "Bottom-up beta: the median unlevered beta of the company's group, relevered for this company's debt.", "sub")
    peers = [p for p, pc in state["companies"].items() if pc["group"] == c["group"]]
    header_row(wa, 5, ["Peer", "Raw beta", "Debt ($mm)", "Equity ($mm)", "Tax rate", "Unlevered beta"])
    r0 = 6
    for i, p in enumerate(peers):
        pc = state["companies"][p]
        r = r0 + i
        put(wa, f"B{r}", f"{pc['name']} ({p})", "lb", bold=(p == t))
        put(wa, f"C{r}", pc["wacc_build"]["beta_raw"], "in", BETA)
        put(wa, f"D{r}", pc["inputs"]["debt"] / 1e6, "in", MM)
        put(wa, f"E{r}", pc["wacc_build"]["market_cap"] / 1e6, "in", MM)
        put(wa, f"F{r}", pc["wacc_build"]["tax"], "in", PCT)
        put(wa, f"G{r}", f"=C{r}/(1+(1-F{r})*D{r}/E{r})", "fx", BETA)
    rl = r0 + len(peers) - 1
    put(wa, f"H{r0}", "Raw betas: 60 monthly returns to Sep 2026 against the S&P 500 (S&P/TSX for TMX); Cboe uses Stock Analysis's 5-year beta. Debt and equity from Stock Analysis, Oct 13, 2026.", "note")
    r = rl + 2
    W = {}

    def wrow(label, value, kind, fmt, note=None, key=None):
        nonlocal r
        put(wa, f"B{r}", label, "lb")
        put(wa, f"C{r}", value, kind, fmt)
        if note:
            put(wa, f"H{r}", note, "note")
        if key:
            W[key] = f"WACC!$C${r}"
        r += 1

    wrow("Group median unlevered beta", f"=MEDIAN(G{r0}:G{rl})", "fx", BETA, None, "bu")
    wrow(f"Debt {mm}", "=" + I["debt"], "lk", MM, None, "d")
    wrow(f"Market value of equity {mm}", "=" + I["mcap"], "lk", MM, None, "e")
    wrow("Tax rate", "=" + I["tax"], "lk", PCT, None, "t")
    wrow("Relevered beta", f"={W['bu']}*(1+(1-{W['t']})*{W['d']}/{W['e']})", "fx", BETA,
         "Hamada: unlevered beta x (1 + (1 - tax) x debt / equity).", "bl")
    wrow("Risk-free rate", "=" + I["rf"], "lk", PCT2, None, "rf")
    wrow("Equity risk premium", "=" + I["erp"], "lk", PCT2, None, "erp")
    wrow("Cost of equity", f"={W['rf']}+{W['bl']}*{W['erp']}", "fx", PCT2, "CAPM: risk-free + beta x premium.", "ke")
    r += 1
    put(wa, f"B{r}", "Debt-to-EBITDA spread table", "sec")
    r += 1
    header_row(wa, r, ["Debt / EBITDA below", "Spread"])
    r += 1
    spread_top = r
    for lim, sp in [(1, 0.0100), (2, 0.0125), (3, 0.0160), (4, 0.0200), (99, 0.0275)]:
        put(wa, f"B{r}", lim, "in", '0.0"x"')
        put(wa, f"C{r}", sp, "in", PCT2)
        r += 1
    spread_bot = r - 1
    put(wa, f"H{spread_top}", "Synthetic spread over the risk-free rate by leverage, a simplified version of Damodaran's ratings table; the last row covers anything at 4x or above.", "note")
    r += 1
    wrow("Debt / EBITDA", f"={I['debt']}/{I['ebitda']}", "fx", MULT, None, "lev")
    wrow("Credit spread", f'=INDEX(C{spread_top}:C{spread_bot},COUNTIF(B{spread_top}:B{spread_bot},"<="&{W["lev"]})+1)',
         "fx", PCT2, "First row whose limit is above this company's leverage.", "spread")
    wrow("Pre-tax cost of debt", f"={W['rf']}+{W['spread']}", "fx", PCT2, None, "kd")
    wrow("After-tax cost of debt", f"={W['kd']}*(1-{W['t']})", "fx", PCT2, None, "kdat")
    wrow("Weight of debt", f"={W['d']}/({W['d']}+{W['e']})", "fx", PCT, "Market-value weights.", "wd")
    wrow("Weight of equity", f"=1-{W['wd']}", "fx", PCT, None, "we")
    wrow("WACC", f"={W['we']}*{W['ke']}+{W['wd']}*{W['kdat']}", "fx", PCT2, None, "wacc")
    wa[W["wacc"].split("!")[1].replace("$", "")].fill = FILL_KEY
    wa[W["wacc"].split("!")[1].replace("$", "")].font = Font(name=ARIAL, size=10, bold=True)

    # ------------------------------------------------------------------ Solver
    widths(so, {"A": 6, "B": 10, "C": 10, "D": 11})
    for i in range(5, 21):
        so.column_dimensions[get_column_letter(i)].width = 11
    put(so, "A1", "Solver: bisection for the growth rate that makes the model equal the price (replaces Goal Seek)", "sec")
    put(so, "B2", "Revenue", "lb"); put(so, "C2", "=" + I["rev"], "lk", MM)
    put(so, "D2", "Margin", "lb"); put(so, "E2", "=" + I["margin"], "lk", PCT)
    put(so, "F2", "Debt", "lb"); put(so, "G2", "=" + I["debt"], "lk", MM)
    put(so, "H2", "Cash", "lb"); put(so, "I2", "=" + I["cash"], "lk", MM)
    put(so, "J2", "Shares", "lb"); put(so, "K2", "=" + I["shares"], "lk", MM1)
    put(so, "L2", "Price", "lb"); put(so, "M2", "=" + I["price"], "lk", ps_fmt)
    put(so, "N2", "Years", "lb"); put(so, "O2", "=" + I["yrs"], "lk", '0')
    put(so, "P2", "Fade", "lb"); put(so, "Q2", "=" + I["fade"], "lk", '0')
    put(so, "D3", "Year", "bold")
    for k in range(1, 11):
        put(so, f"{get_column_letter(4 + k)}3", k, "bold", '0')
    put(so, "A4", "Each row tries the midpoint of the current range. If the value per share is above the price, the answer is lower, so the top of the range moves down; otherwise the bottom moves up.", "note")

    def solver_block(top, w_ref, tg_ref, iters, title):
        put(so, f"A{top}", title, "bold")
        put(so, f"E{top}", "WACC", "lb")
        put(so, f"F{top}", "=" + w_ref, "lk", PCT2)
        put(so, f"G{top}", "Terminal growth", "lb")
        put(so, f"I{top}", "=" + tg_ref, "lk", PCT2)
        hr = top + 1
        header_row(so, hr, ["Low", "High", "Mid"] + [f"Rev Y{k}" for k in range(1, 11)] +
                   ["PV of FCF", "PV of TV", "EV", "Equity", "Per share", "Value - price"], start_col=2)
        so.cell(row=hr, column=1, value="Step").font = F_BOLD
        W_, G_ = f"$F${top}", f"$I${top}"
        first = hr + 1
        for k in range(iters):
            rr = first + k
            so.cell(row=rr, column=1, value=k + 1).font = F_FX
            if k == 0:
                put(so, f"B{rr}", -0.5, "in", PCT2)
                put(so, f"C{rr}", 1.0, "in", PCT2)
            else:
                put(so, f"B{rr}", f"=IF(T{rr-1}>0,B{rr-1},D{rr-1})", "fx", PCT2)
                put(so, f"C{rr}", f"=IF(T{rr-1}>0,D{rr-1},C{rr-1})", "fx", PCT2)
            put(so, f"D{rr}", f"=(B{rr}+C{rr})/2", "fx", '0.0000%')
            for yr in range(1, 11):
                L = get_column_letter(4 + yr)
                prev = "$C$2" if yr == 1 else f"{get_column_letter(3 + yr)}{rr}"
                g = f"IF({L}$3<=$O$2,$D{rr},$D{rr}-($D{rr}-{G_})*MIN({L}$3-$O$2,$Q$2)/$Q$2)"
                put(so, f"{L}{rr}", f"={prev}*(1+{g})", "fx", MM)
            put(so, f"O{rr}", f"=SUMPRODUCT(E{rr}:N{rr},1/(1+{W_})^$E$3:$N$3)*$E$2", "fx", MM)
            put(so, f"P{rr}", f"=N{rr}*$E$2*(1+{G_})/({W_}-{G_})/(1+{W_})^$N$3", "fx", MM)
            put(so, f"Q{rr}", f"=O{rr}+P{rr}", "fx", MM)
            put(so, f"R{rr}", f"=Q{rr}-$G$2+$I$2", "fx", MM)
            put(so, f"S{rr}", f"=R{rr}/$K$2", "fx", ps_fmt)
            put(so, f"T{rr}", f"=S{rr}-$M$2", "fx", '#,##0.0000;(#,##0.0000);"-"')
        return f"Solver!$D${first + iters - 1}", first + iters

    base_ref, nxt = solver_block(6, W["wacc"], I["tg"], 40, "Base case: model WACC and terminal growth (40 steps)")
    put(so, "W6", "Implied growth", "bold")
    put(so, "W7", "=" + base_ref.split("!")[1], "fx", PCT2)
    so["W7"].fill = FILL_KEY
    put(so, "W8", '=IF(OR(ABS(W7+0.5)<0.000001,ABS(W7-1)<0.000001),"Out of range","Solved")', "fx")
    IMPLIED = "Solver!$W$7"

    # Sensitivity axes (live) on the Sensitivity tab
    widths(se, {"A": 2, "B": 26, "C": 13, "D": 13, "E": 13, "F": 13, "G": 13, "H": 4, "I": 60})
    put(se, "B2", f"{c['name']} ({t}): sensitivity", "title")
    put(se, "B3", "Table A re-solves implied growth for each pair of inputs (Solver tab, blocks 2 to 26). Table B values the stock at a growth view.", "sub")
    put(se, "B5", "WACC step", "lb"); put(se, "C5", 0.005, "in", PCT2)
    put(se, "D5", "Terminal-growth step", "lb"); put(se, "F5", 0.005, "in", PCT2)
    put(se, "B6", "Growth-view step", "lb"); put(se, "C6", 0.02, "in", PCT2)
    put(se, "B8", "A. Implied 5-year growth: WACC (rows) by terminal growth (columns)", "sec")
    for j in range(5):
        L = get_column_letter(3 + j)
        put(se, f"{L}9", f"={I['tg']}+({j}-2)*$F$5", "fx", PCT2, bold=True)
    for i in range(5):
        put(se, f"B{10 + i}", f"={W['wacc']}+({i}-2)*$C$5", "fx", PCT2, bold=True)
    blocks = {}
    top = nxt + 1
    for i in range(5):
        for j in range(5):
            L = get_column_letter(3 + j)
            ref, nxt2 = solver_block(top, f"Sensitivity!$B${10 + i}", f"Sensitivity!${L}$9", 24,
                                     f"Grid block {i*5 + j + 2}: row {i + 1}, column {j + 1} of table A (24 steps)")
            blocks[(i, j)] = ref
            put(se, f"{L}{10 + i}", "=" + ref, "lk", PCT)
            top = nxt2 + 1
    se["E12"].fill = FILL_KEY
    put(se, "I10", "Centre cell = the base case. Each step changes one input by the step size above.", "note")

    put(se, "B17", "B. Value per share: WACC (rows) by your growth view (columns)", "sec")
    for j in range(5):
        L = get_column_letter(3 + j)
        put(se, f"{L}18", f"={I['view']}+({j}-2)*$C$6", "fx", PCT, bold=True)
    for i in range(5):
        put(se, f"B{19 + i}", f"={W['wacc']}+({i}-2)*$C$5", "fx", PCT2, bold=True)
    # helper revenue paths for table B
    put(se, "B26", "Helper: revenue paths for each growth view (years 1 to 10)", "note")
    for k in range(1, 11):
        put(se, f"{get_column_letter(2 + k)}27", k, "bold", '0')
    for j in range(5):
        rr = 28 + j
        V = f"{get_column_letter(3 + j)}$18"
        put(se, f"B{rr}", f"={V}", "fx", PCT)
        for yr in range(1, 11):
            L = get_column_letter(2 + yr)
            prev = I["rev"] if yr == 1 else f"{get_column_letter(1 + yr)}{rr}"
            g = f"IF({L}$27<={I['yrs']},$B{rr},$B{rr}-($B{rr}-{I['tg']})*MIN({L}$27-{I['yrs']},{I['fade']})/{I['fade']})"
            put(se, f"{L}{rr}", f"={prev}*(1+{g})", "fx", MM)
    for i in range(5):
        for j in range(5):
            L = get_column_letter(3 + j)
            rr = 28 + j
            w = f"$B{19 + i}"
            f = (f"=(SUMPRODUCT($C{rr}:$L{rr},1/(1+{w})^$C$27:$L$27)*{I['margin']}"
                 f"+$L{rr}*{I['margin']}*(1+{I['tg']})/({w}-{I['tg']})/(1+{w})^$L$27"
                 f"-{I['debt']}+{I['cash']})/{I['shares']}")
            put(se, f"{L}{19 + i}", f, "fx", ps_fmt)
    se["E21"].fill = FILL_KEY
    put(se, "I19", f"Compare with the price at the lock: {ccy}{c['lock']['price']:,.2f}.", "note")

    # ------------------------------------------------------------------ DCF
    widths(dc, {"A": 2, "B": 36})
    for i in range(3, 14):
        dc.column_dimensions[get_column_letter(i)].width = 12
    put(dc, "B2", f"{c['name']} ({t}): discounted cash flow", "title")
    put(dc, "B3", "Panel A runs the model at the solved growth rate, so it should land on the price. Panel B runs it at your view.", "sub")

    def dcf_panel(top, g_ref, title):
        put(dc, f"B{top}", title, "sec")
        header_row(dc, top + 1, ["Year"] + [str(k) for k in range(1, 11)])
        rows = {"g": top + 2, "rev": top + 3, "fcf": top + 4, "df": top + 5, "pv": top + 6}
        put(dc, f"B{rows['g']}", "Revenue growth", "lb")
        put(dc, f"B{rows['rev']}", f"Revenue {mm}", "lb")
        put(dc, f"B{rows['fcf']}", f"Unlevered free cash flow {mm}", "lb")
        put(dc, f"B{rows['df']}", "Discount factor", "lb")
        put(dc, f"B{rows['pv']}", f"Present value {mm}", "lb")
        for k in range(1, 11):
            L = get_column_letter(2 + k)
            put(dc, f"{L}{top+1}", k, "bold", '0')
            dc[f"{L}{top+1}"].font = F_HEAD
            dc[f"{L}{top+1}"].fill = FILL_HEAD
            put(dc, f"{L}{rows['g']}",
                f"=IF({L}${top+1}<={I['yrs']},{g_ref},{g_ref}-({g_ref}-{I['tg']})*MIN({L}${top+1}-{I['yrs']},{I['fade']})/{I['fade']})",
                "fx", PCT)
            prev = I["rev"] if k == 1 else f"{get_column_letter(1 + k)}{rows['rev']}"
            put(dc, f"{L}{rows['rev']}", f"={prev}*(1+{L}{rows['g']})", "fx", MM)
            put(dc, f"{L}{rows['fcf']}", f"={L}{rows['rev']}*{I['margin']}", "fx", MM)
            put(dc, f"{L}{rows['df']}", f"=1/(1+{W['wacc']})^{L}${top+1}", "fx", '0.0000')
            put(dc, f"{L}{rows['pv']}", f"={L}{rows['fcf']}*{L}{rows['df']}", "fx", MM)
        b = top + 8
        items = [
            ("Sum of present values, years 1 to 10", f"=SUM(C{rows['pv']}:L{rows['pv']})", MM),
            ("Terminal value at year 10", f"=L{rows['fcf']}*(1+{I['tg']})/({W['wacc']}-{I['tg']})", MM),
            ("Present value of terminal value", f"=C{b+1}*L{rows['df']}", MM),
            ("Enterprise value", f"=C{b}+C{b+2}", MM),
            ("Less: debt", f"=-{I['debt']}", MM),
            ("Plus: cash", f"={I['cash']}", MM),
            ("Equity value", f"=SUM(C{b+3}:C{b+5})", MM),
            ("Shares (mm)", f"={I['shares']}", MM1),
            (f"Value per share ({ccy})", f"=C{b+6}/C{b+7}", ps_fmt),
            (f"Price at the lock ({ccy})", f"={I['price']}", ps_fmt),
            ("Value / price - 1", f"=C{b+8}/C{b+9}-1", PCT),
            ("Terminal value share of enterprise value", f"=C{b+2}/C{b+3}", PCT),
        ]
        for k, (lab, fml, fmt) in enumerate(items):
            put(dc, f"B{b+k}", lab, "lb", bold=lab.startswith("Value per share") or lab == "Enterprise value")
            kind = "lk" if fml.startswith("=Inputs!") or fml.startswith("=-Inputs!") else "fx"
            put(dc, f"C{b+k}", fml, kind, fmt)
        return b

    pa = dcf_panel(5, IMPLIED, "A. At the solved (implied) growth rate")
    pb = dcf_panel(25, I["view"], "B. At your view of growth (Inputs tab, yellow cell)")
    dc[f"C{pa+8}"].fill = FILL_KEY
    dc[f"C{pb+8}"].fill = FILL_KEY

    # ------------------------------------------------------------------ Cover
    widths(cov, {"A": 2, "B": 44, "C": 18, "D": 4, "E": 70})
    put(cov, "B2", f"Priced In: {c['name']} ({t})", "title")
    put(cov, "B3", f"Reverse DCF, model v{meta['model_version']}. Inputs as of the Oct 13, 2026 close; model locked Oct 14, 2026 (commit {meta['lock_commit']}).", "sub")
    put(cov, "B4", f"{c['group']} | {c['country']} | reports in {c['currency']}", "sub")
    put(cov, "B6", "The question", "sec")
    put(cov, "B7", "What revenue growth over the next five years does today's price imply, and is that more or less than the company has delivered and analysts expect?", "lb")
    put(cov, "B9", "Answer", "sec")
    out = [
        (f"Price at the lock ({ccy})", "=" + I["price"], ps_fmt, "lk"),
        ("Implied 5-year revenue growth", "=" + IMPLIED, PCT, "lk"),
        ("Anchor (history and analysts)", "=" + I["anchor"], PCT, "lk"),
        ("Gap (implied - anchor)", "=C11-C12", PCT, "fx"),
        ("Verdict", None, None, "fx"),
        ("WACC", "=" + W["wacc"], PCT2, "lk"),
        ("Terminal growth", "=" + I["tg"], PCT2, "lk"),
        ("Unlevered free-cash-flow margin", "=" + I["margin"], PCT, "lk"),
        ("Your view of growth (Inputs, yellow)", "=" + I["view"], PCT, "lk"),
        (f"Value per share at your view ({ccy})", f"=DCF!$C${pb+8}", ps_fmt, "lk"),
        ("Upside or downside at your view", f"=DCF!$C${pb+10}", PCT, "lk"),
    ]
    for k, (lab, fml, fmt, kind) in enumerate(out):
        rr = 10 + k
        put(cov, f"B{rr}", lab, "lb", bold=k in (1, 3, 4))
        if lab == "Verdict":
            if c.get("flag") and c["flag"]["label"] == "Deal price":
                put(cov, f"C{rr}", "Deal price", "fx", bold=True)
            else:
                put(cov, f"C{rr}", f'=IF(C13>={I["band"]},"Expectations too high",IF(C13<=-{I["band"]},"Expectations too low","About right"))', "fx", bold=True)
        else:
            put(cov, f"C{rr}", fml, kind, fmt)
    for rr in (11, 13, 14):
        cov[f"C{rr}"].fill = FILL_KEY
    if c.get("flag"):
        put(cov, "B22", f"Fit flag: {c['flag']['label']}", "sec")
        put(cov, "B23", c["flag"]["note"], "lb")
    put(cov, "B25", "How to use this file", "sec")
    tips = [
        "Change any blue cell on Inputs, History or WACC; everything recalculates, including the solver.",
        "The Solver tab finds implied growth by bisection with formulas, so you never need Goal Seek. 40 steps narrow a 150-point range to well under 0.0001%.",
        "Type your own growth view in the yellow cell on Inputs; DCF panel B and this page show what the stock is worth if you're right.",
        "Check confirms this workbook matches the Python pipeline that runs the site.",
    ]
    for k, tip in enumerate(tips):
        put(cov, f"B{26 + k}", f"{k + 1}. {tip}", "lb")
    put(cov, "B31", "Colour key", "sec")
    put(cov, "B32", "Typed input with a source", "lb"); put(cov, "C32", 1234, "in", MM)
    put(cov, "B33", "Formula", "lb"); put(cov, "C33", "=C32*2", "fx", MM)
    put(cov, "B34", "Link to another tab", "lb"); put(cov, "C34", "=" + I["rev"], "lk", MM)
    put(cov, "B35", "Your view (edit this one)", "lb"); cc = put(cov, "C35", "=" + I["view"], "lk", PCT); cc.fill = FILL_YEL
    if SITE_URL:
        put(cov, "B37", "Live site", "sec")
        cl = put(cov, "B38", SITE_URL, "lb")
        cl.hyperlink = SITE_URL
        cl.font = Font(name=ARIAL, size=10, color=BLUE, underline="single")
    put(cov, "B40", "Built by Rohan Jayapalan. Not investment advice.", "note")
    for rr in range(7, 8):
        cov[f"B{rr}"].alignment = Alignment(wrap_text=True)
    cov.merge_cells("B7:E7")
    cov.row_dimensions[7].height = 30
    cov.merge_cells("B23:E23")
    cov["B23"].alignment = Alignment(wrap_text=True, vertical="top")
    cov.row_dimensions[23].height = 30

    # ------------------------------------------------------------------ Check
    widths(ck, {"A": 2, "B": 46, "C": 16, "D": 16, "E": 14, "F": 10, "G": 50})
    put(ck, "B2", f"{c['name']} ({t}): check against the Python pipeline", "title")
    put(ck, "B3", "Python values are typed in (blue) from the pipeline that runs the site. Each row passes if the two agree within the tolerance.", "sub")
    header_row(ck, 5, ["Item", "This workbook", "Python pipeline", "Difference", "Result"])
    lp = c["lock"]["price"]
    base = dict(inp)
    py_g = R.implied_growth(base, lp)
    up = dict(base); up["wacc"] += 0.01
    py_up = R.implied_growth(up, lp)
    py_view = R.value_per_share(base, an["anchor"])
    checks = [
        ("Unlevered free-cash-flow margin", "=" + I["margin"], inp["fcf_margin"], PCT2, 0.00005),
        ("Group median unlevered beta", "=" + W["bu"], wb_["beta_group_unlevered"], '0.0000', 0.0005),
        ("WACC", "=" + W["wacc"], inp["wacc"], PCT2, 0.00005),
        ("Terminal growth", "=" + I["tg"], inp["terminal_growth"], PCT2, 0.00005),
        ("Anchor", "=" + I["anchor"], an["anchor"], PCT2, 0.00005),
        ("Implied growth, base case", "=" + IMPLIED, py_g, PCT2, 0.00005),
        ("Implied growth, WACC one point higher", "=Sensitivity!$E$14", py_up, PCT2, 0.0002),
        (f"Value per share at the anchor ({ccy})", f"=DCF!$C${pb+8}", py_view, ps_fmt, max(0.02, abs(py_view) * 1e-4)),
        (f"Panel A value minus price ({ccy})", f"=DCF!$C${pa+8}-DCF!$C${pa+9}", 0.0, ps_fmt, 0.01),
    ]
    for k, (lab, fml, pyv, fmt, tol) in enumerate(checks):
        rr = 6 + k
        put(ck, f"B{rr}", lab, "lb")
        put(ck, f"C{rr}", fml, "lk", fmt)
        put(ck, f"D{rr}", round(pyv, 8), "in", fmt)
        put(ck, f"E{rr}", f"=C{rr}-D{rr}", "fx", '0.000000')
        put(ck, f"F{rr}", f'=IF(ABS(E{rr})<={tol},"Pass","Check")', "fx")
    last = 6 + len(checks) - 1
    put(ck, f"B{last + 2}", "Overall", "bold")
    put(ck, f"C{last + 2}", f'=IF(COUNTIF(F6:F{last},"Pass")={len(checks)},"All checks pass","Review")', "fx", bold=True)
    put(ck, f"G{6 + 8}", "Panel B on the DCF tab uses your view; with the yellow cell at the anchor it matches the pipeline.", "note")

    # freeze panes and print setup
    cov.sheet_properties.tabColor = NAVY
    so.freeze_panes = "B4"
    path = os.path.join(OUTDIR, f"PricedIn_{t}.xlsx")
    wb.save(path)
    return path


def main(only=None):
    state = json.load(open(os.path.join(ROOT, "site", "data", "live.json")))
    stats = load_csv(os.path.join(ROOT, "data", "raw", "fund", "stats_batch1.csv"))
    revhist = load_csv(os.path.join(ROOT, "data", "raw", "fund", "revenue_history.csv"))
    out = []
    for t in state["companies"]:
        if only and t not in only:
            continue
        out.append(build(t, state, stats, revhist))
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
