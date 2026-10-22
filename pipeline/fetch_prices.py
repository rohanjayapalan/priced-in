"""Fetch the daily closes the site doesn't have yet.

Usage:
    python pipeline/fetch_prices.py site/data/live.json prices_new.json

Writes {"TICKER": [["YYYY-MM-DD", close, volume], ...]} holding only completed sessions newer
than what live.json already stores. Yahoo Finance (through yfinance) is the main source and
Stooq is the backup for US listings. A ticker no source can price is left out: refresh.py
carries its last close forward and the site shows that close's date.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import urllib.request
from zoneinfo import ZoneInfo

YAHOO_SYMBOL = {"X": "X.TO"}   # TMX trades in Toronto; every other ticker is its own Yahoo symbol
NO_STOOQ = {"X"}               # Stooq's free files don't cover the TSX


def last_stored(state: dict) -> dict:
    return {t: (rows[-1][0] if rows else "2026-01-01") for t, rows in state["prices"].items()}


def last_complete_session(now: dt.datetime | None = None) -> str:
    """Latest date whose close is final: today once it's 4:30 pm in New York, else yesterday."""
    now = now or dt.datetime.now(ZoneInfo("America/New_York"))
    if now.time() >= dt.time(16, 30):
        return now.date().isoformat()
    return (now.date() - dt.timedelta(days=1)).isoformat()


def clean(rows: list) -> list:
    out = []
    for d, c, v in rows:
        if c is None or (isinstance(c, float) and math.isnan(c)) or c <= 0:
            continue
        vol = None if v is None or (isinstance(v, float) and math.isnan(v)) else int(v)
        out.append([d, round(float(c), 4), vol])
    return out


def from_yahoo(tickers: list[str], start: str) -> dict:
    import pandas as pd
    import yfinance as yf

    symbols = [YAHOO_SYMBOL.get(t, t) for t in tickers]
    df = yf.download(symbols, start=start, interval="1d", auto_adjust=False, group_by="ticker",
                     progress=False, threads=True)
    out = {}
    if df is None or df.empty:
        return out
    for t, s in zip(tickers, symbols):
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if s not in df.columns.get_level_values(0):
                    continue
                sub = df[s]
            else:
                sub = df
            sub = sub.dropna(subset=["Close"])
            rows = [[d.strftime("%Y-%m-%d"), float(r["Close"]), r.get("Volume")] for d, r in sub.iterrows()]
            out[t] = clean([[d, c, (None if pd.isna(v) else float(v))] for d, c, v in rows])
        except Exception as err:  # one bad ticker shouldn't stop the rest
            print(f"Yahoo: skipped {t}: {err}")
    return out


def from_stooq(ticker: str, start: str) -> list:
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Priced In daily refresh)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    rows = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 6 or parts[0] < start:
            continue
        rows.append([parts[0], float(parts[4]), float(parts[5]) if parts[5] else None])
    return clean(rows)


def main(live_path: str, out_path: str) -> None:
    state = json.load(open(live_path))
    since = last_stored(state)
    through = last_complete_session()
    start = min(since.values())
    got = {}
    try:
        got = from_yahoo(list(since), start)
    except Exception as err:
        print(f"Yahoo failed: {err}")
    new = {}
    for t, last in since.items():
        rows = [r for r in got.get(t, []) if last < r[0] <= through]
        if not rows and t not in NO_STOOQ:
            try:
                rows = [r for r in from_stooq(t, last) if last < r[0] <= through]
            except Exception as err:
                print(f"Stooq failed for {t}: {err}")
        if rows:
            new[t] = rows
    json.dump(new, open(out_path, "w"))
    missing = [t for t in since if t not in new]
    print(f"New closes for {len(new)} of {len(since)} tickers, through {through}.")
    if missing:
        print("Nothing new for: " + ", ".join(missing))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
