"""Dated events for In play: 8-K filings from SEC EDGAR and bursts of news coverage.

Usage:
    python pipeline/fetch_events.py site/data/live.json events_new.json

8-K items that count: 1.01 (signed a material agreement), 2.01 (completed an acquisition or
disposal), 2.02 (reported results) and 5.02 (leadership change). The SEC asks every program
that reads EDGAR to identify itself, so this reads SEC_USER_AGENT from the environment
(for example "Priced In your.name@example.com") and skips EDGAR when it's missing.

News: the number of Google News articles about each company in the past day. A count at
least 3 times its usual level (the median of the previous 20 checks, minimum 10 articles)
is a news burst. Daily counts are kept in live.json["news_history"].

Writes a JSON list of events for refresh.py; anything that fails is skipped, never fatal.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ITEMS = {
    "1.01": ("Deal", "signed a material agreement"),
    "2.01": ("Deal", "completed an acquisition or disposal"),
    "2.02": ("Results", "reported results"),
    "5.02": ("Management", "announced a leadership change"),
}
LOOKBACK_DAYS = 7
NEWS_QUERY = {
    "ICE": "Intercontinental Exchange", "CME": "CME Group", "NDAQ": "Nasdaq Inc", "CBOE": "Cboe Global Markets",
    "X": "TMX Group", "TW": "Tradeweb", "MKTX": "MarketAxess", "SPGI": "S&P Global", "MCO": "Moody's",
    "MSCI": "MSCI Inc", "MORN": "Morningstar Inc", "FDS": "FactSet", "TRI": "Thomson Reuters",
    "BR": "Broadridge", "SSNC": "SS&C Technologies", "VRSK": "Verisk", "FICO": "Fair Isaac",
    "EFX": "Equifax", "TRU": "TransUnion",
}
KEEP_DAYS = 40


def fetch(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


def sec_events(state: dict, user_agent: str, today: dt.date) -> list:
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    listing = json.loads(fetch("https://www.sec.gov/files/company_tickers.json", headers))
    cik = {v["ticker"].upper(): int(v["cik_str"]) for v in listing.values()}
    since = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    out = []
    for t, c in state["companies"].items():
        if t not in cik:          # TMX files in Canada, not with the SEC
            continue
        try:
            sub = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{cik[t]:010d}.json", headers))
            rec = sub["filings"]["recent"]
            rows = zip(rec["form"], rec["filingDate"], rec["items"], rec["accessionNumber"], rec["primaryDocument"])
            for form, filed, items, acc, doc in rows:
                if filed < since or form not in ("8-K", "8-K/A"):
                    continue
                for item in [x.strip() for x in (items or "").split(",") if x.strip()]:
                    if item not in ITEMS:
                        continue
                    kind, what = ITEMS[item]
                    out.append({
                        "ticker": t, "date": filed, "kind": kind,
                        "label": f"{c['name']} {what} (8-K item {item})",
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik[t]}/{acc.replace('-', '')}/{doc}",
                    })
        except Exception as err:
            print(f"EDGAR: skipped {t}: {err}")
        time.sleep(0.2)   # well under the SEC's 10 requests a second
    return out


def news_count(query: str) -> int:
    q = urllib.parse.urlencode({"q": f'"{query}" when:1d', "hl": "en-US", "gl": "US", "ceid": "US:en"})
    xml = fetch(f"https://news.google.com/rss/search?{q}", {"User-Agent": "Mozilla/5.0 (Priced In daily refresh)"})
    return len(ET.fromstring(xml).findall("./channel/item"))


def news_events(state: dict, today: dt.date) -> list:
    hist = state.setdefault("news_history", {})
    day = today.isoformat()
    out = []
    for t, c in state["companies"].items():
        query = NEWS_QUERY.get(t, c["name"])
        try:
            n = news_count(query)
        except Exception as err:
            print(f"News: skipped {t}: {err}")
            continue
        rows = [r for r in hist.get(t, []) if r[0] != day]
        usual = statistics.median([r[1] for r in rows[-20:]]) if len(rows) >= 10 else None
        if usual is not None and n >= 10 and n >= 3 * max(usual, 1):
            link = "https://news.google.com/search?" + urllib.parse.urlencode({"q": f'"{query}" when:1d'})
            out.append({"ticker": t, "date": day, "kind": "News burst",
                        "label": f"News burst: {n} articles about {c['name']} in a day, {n / max(usual, 1):.1f} times usual",
                        "url": link})
        hist[t] = (rows + [[day, n]])[-KEEP_DAYS:]
        time.sleep(0.5)
    return out


def main(live_path: str, out_path: str) -> None:
    state = json.load(open(live_path))
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    events = []
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if ua:
        try:
            events += sec_events(state, ua, today)
        except Exception as err:
            print(f"EDGAR failed: {err}")
    else:
        print("SEC_USER_AGENT isn't set, so 8-K filings were skipped.")
    try:
        events += news_events(state, today)
    except Exception as err:
        print(f"News failed: {err}")
    json.dump(state, open(live_path, "w"), separators=(",", ":"))   # keeps the news history
    json.dump(events, open(out_path, "w"))
    print(f"{len(events)} events: " + "; ".join(f"{e['ticker']} {e['kind']}" for e in events))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
