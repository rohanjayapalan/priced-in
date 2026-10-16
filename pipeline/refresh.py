"""Priced In daily refresh (model v1.0). Pure Python, no third-party packages.

Usage:
    python3 refresh.py live.json [prices_new.json] [events_new.json]

live.json        the site's data file (read, updated, and written back in place)
prices_new.json  optional {"TICKER": [["YYYY-MM-DD", close, volume], ...], ...}
events_new.json  optional [{"ticker", "date", "kind", "label", "url"}, ...]

What it does, in order:
  1. Merges new daily closes into live.json["prices"] (keeps the last 260 rows).
  2. Recomputes each company at its latest close: implied growth, gap to the
     anchor, verdict, the implied-growth path, and two sensitivity tables.
     Fundamentals stay at their locked values until the next quarterly update.
  3. Scores In play from price shocks, volume spikes, implied-growth swings and
     dated events, and picks the leader.
  4. Runs the season ledger: entry at the Oct 14, 2026 close, monthly
     rebalance on the first trading day of each month, equal-weight benchmark
     of every name except deal-price names, local-currency price returns.
  5. Scores the directional calls (too low / too high) against the benchmark.

The valuation functions below are a line-for-line copy of pipeline/engine.py;
tests/parity_check.py checks the two agree.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timezone

MODEL_VERSION = "1.0"
EXPLICIT_YEARS = 5
FADE_YEARS = 5
VERDICT_BAND = 0.03
KEEP_ROWS = 260
SEASON_START = "2026-10-14"


# ---------------------------------------------------------------- engine copy
def revenue_path(r0, g, gT):
    rev, out = r0, []
    for t in range(1, EXPLICIT_YEARS + FADE_YEARS + 1):
        if t <= EXPLICIT_YEARS:
            gt = g
        else:
            k = t - EXPLICIT_YEARS
            gt = g - (g - gT) * k / FADE_YEARS
        rev *= 1 + gt
        out.append(rev)
    return out


def enterprise_value(inp, g):
    revs = revenue_path(inp["revenue"], g, inp["terminal_growth"])
    w = inp["wacc"]
    pv = 0.0
    for t, r in enumerate(revs, start=1):
        pv += r * inp["fcf_margin"] / (1 + w) ** t
    fcf10 = revs[-1] * inp["fcf_margin"]
    tv = fcf10 * (1 + inp["terminal_growth"]) / (w - inp["terminal_growth"])
    pv += tv / (1 + w) ** len(revs)
    return pv


def value_per_share(inp, g):
    ev = enterprise_value(inp, g)
    equity = ev - inp["debt"] + inp["cash"] - inp.get("minority", 0.0)
    return equity / inp["shares"]


def implied_growth(inp, price, lo=-0.50, hi=1.00, tol=1e-7):
    if inp["wacc"] <= inp["terminal_growth"]:
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


def verdict(gap):
    if gap is None:
        return "n/a"
    if gap >= VERDICT_BAND:
        return "Expectations too high"
    if gap <= -VERDICT_BAND:
        return "Expectations too low"
    return "About right"


# ---------------------------------------------------------------- helpers
def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def r4(x, nd=6):
    return None if x is None else round(x, nd)


def fmt_date(d):
    dt = datetime.strptime(d, "%Y-%m-%d")
    return dt.strftime("%b %-d")


def with_inputs(base, **kw):
    out = dict(base)
    out.update(kw)
    return out


# ---------------------------------------------------------------- prices
def merge_prices(state, new):
    for t, rows in (new or {}).items():
        if t not in state["prices"]:
            continue
        have = {r[0]: r for r in state["prices"][t]}
        for d, c, v in rows:
            have[d] = [d, float(c), int(v) if v is not None else None]
        merged = sorted(have.values(), key=lambda r: r[0])
        state["prices"][t] = merged[-KEEP_ROWS:]


def latest(state, t):
    rows = state["prices"].get(t) or []
    return rows[-1] if rows else None


# ---------------------------------------------------------------- companies
def grid_points(lo, hi, n=5, step=0.005):
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step
    if hi - lo < step * (n - 1):
        hi = lo + step * (n - 1)
    raw = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    return [round(round(x / step) * step, 6) for x in raw]


def recompute_company(c, prices):
    inp = c["inputs"]
    row = prices[-1]
    price = row[1]
    g = implied_growth(inp, price)
    anchor = c["anchor"]["anchor"]
    gap = None if g is None else g - anchor
    deal = c.get("flag") and c["flag"]["label"] == "Deal price"
    live = {
        "date": row[0], "price": price, "implied": r4(g), "gap": r4(gap),
        "verdict": "Deal price" if deal else verdict(gap),
    }
    # implied-growth path over the last 30 closes, fundamentals held fixed
    live["implied_path"] = [[d, r4(implied_growth(inp, px), 5)] for d, px, _v in prices[-30:]]
    # sensitivity 1: implied growth by WACC x terminal growth
    w0, tg0 = inp["wacc"], inp["terminal_growth"]
    waccs = [round(w0 + d, 6) for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    tgs = [round(tg0 + d, 6) for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    grid = []
    for w in waccs:
        grid.append([r4(implied_growth(with_inputs(inp, wacc=w, terminal_growth=t), price), 5) for t in tgs])
    live["sens_wacc_tg"] = {"waccs": waccs, "tgs": tgs, "grid": grid}
    # sensitivity 2: value per share by growth view x WACC
    lo = min(x for x in (g, anchor) if x is not None) - 0.02
    hi = max(x for x in (g, anchor) if x is not None) + 0.02
    views = grid_points(lo, hi)
    vgrid = []
    for w in waccs:
        vgrid.append([round(value_per_share(with_inputs(inp, wacc=w), v), 2) for v in views])
    live["sens_view_wacc"] = {"views": views, "waccs": waccs, "grid": vgrid}
    live["value_at_anchor"] = round(value_per_share(inp, anchor), 2)
    live["upside_at_anchor"] = r4(value_per_share(inp, anchor) / price - 1)
    c["live"] = live


# ---------------------------------------------------------------- in play
def robust_sigma(rets):
    med = median(rets)
    mad = median([abs(r - med) for r in rets])
    return max(1.4826 * mad, 0.003)


def score_in_play(state):
    out = []
    events = state.get("events", [])
    for t, c in state["companies"].items():
        rows = state["prices"].get(t) or []
        if len(rows) < 26:
            continue
        closes = [r[1] for r in rows]
        vols = [r[2] for r in rows]
        dates = [r[0] for r in rows]
        n = len(rows)
        rets = [None] + [closes[i] / closes[i - 1] - 1 for i in range(1, n)]
        best, reasons = 0.0, []
        for age in range(5):
            i = n - 1 - age
            if i < 21:
                break
            prior = [x for x in rets[max(1, i - 49):i] if x is not None]
            sig = robust_sigma(prior)
            shock = abs(rets[i]) / sig
            vbase = [v for v in vols[max(0, i - 50):i] if v]
            vr = (vols[i] / (sum(vbase) / len(vbase))) if (vbase and vols[i]) else 0.0
            swing = 0.0
            if i - 5 >= 0:
                g_now = implied_growth(c["inputs"], closes[i])
                g_then = implied_growth(c["inputs"], closes[i - 5])
                if g_now is not None and g_then is not None:
                    swing = abs(g_now - g_then) * 100
            parts = {"shock": shock / 3, "volume": vr / 3, "swing": swing / 2}
            decay = 0.85 ** age
            raw = max(parts.values())
            if raw * decay > best:
                best = raw * decay
            d = fmt_date(dates[i])
            move = "Rose" if rets[i] > 0 else "Fell"
            # every signal is recorded; the page marks the ones at or over their threshold
            reasons.append({"date": dates[i], "kind": "Price shock", "weight": shock / 3 * decay, "hit": shock >= 3,
                            "text": f"{move} {abs(rets[i])*100:.1f}% on {d}, {shock:.1f} times its normal daily move"})
            reasons.append({"date": dates[i], "kind": "Volume spike", "weight": vr / 3 * decay, "hit": vr >= 3,
                            "text": f"Volume on {d} was {vr:.1f} times its 50-day average"})
            reasons.append({"date": dates[i], "kind": "Implied-growth swing", "weight": swing / 2 * decay,
                            "hit": swing >= 2,
                            "text": f"Implied growth moved {swing:.1f} points in the 5 trading days to {d}"})
        last_date = dates[-1]
        for ev in events:
            if ev.get("ticker") != t:
                continue
            # dated events count for 5 trading days after they happen
            if ev["date"] <= last_date and ev["date"] in dates[-5:]:
                age = len(dates) - 1 - dates.index(ev["date"])
                w = 1.2 * 0.85 ** age
                best = max(best, w)
                reasons.append({"date": ev["date"], "kind": ev.get("kind", "Event"), "weight": w, "hit": True,
                                "text": ev["label"], "url": ev.get("url")})
        reasons.sort(key=lambda r: -r["weight"])
        # one reason per kind, strongest first
        seen, uniq = set(), []
        for r in reasons:
            if r["kind"] in seen:
                continue
            seen.add(r["kind"])
            uniq.append(r)
        for r in uniq:
            r["weight"] = round(r["weight"], 3)
        out.append({"ticker": t, "score": round(best, 3), "triggered": best >= 1.0,
                    "reasons": uniq[:3], "last_date": last_date})
    out.sort(key=lambda r: -r["score"])
    leader = out[0]["ticker"] if out and out[0]["score"] > 0 else None
    upcoming = sorted([e for e in events if e["date"] > max(r["last_date"] for r in out)],
                      key=lambda e: e["date"]) if out else []
    state["inplay"] = {
        "as_of": max(r["last_date"] for r in out) if out else None,
        "leader": leader, "ranking": out, "upcoming": upcoming[:6],
        "rules": state.get("inplay", {}).get("rules", []),
    }


# ---------------------------------------------------------------- season
def trading_calendar(state, start):
    counts = {}
    names = list(state["companies"])
    for t in names:
        for d, _c, _v in state["prices"].get(t, []):
            if d >= start:
                counts[d] = counts.get(d, 0) + 1
    need = max(1, int(0.6 * len(names)))
    return sorted(d for d, k in counts.items() if k >= need)


def close_on_or_before(state, t, d):
    best = None
    for row in state["prices"].get(t, []):
        if row[0] <= d:
            best = row
        else:
            break
    return best


def gaps_at(state, d):
    out = {}
    for t, c in state["companies"].items():
        if c.get("flag") and c["flag"]["label"] == "Deal price":
            continue
        row = close_on_or_before(state, t, d)
        if not row:
            continue
        g = implied_growth(c["inputs"], row[1])
        if g is None:
            continue
        out[t] = g - c["anchor"]["anchor"]
    return out


def run_season(state):
    s = state["season"]
    members = [t for t, c in state["companies"].items()
               if not (c.get("flag") and c["flag"]["label"] == "Deal price")]
    s["bench_members"] = members
    cal = trading_calendar(state, SEASON_START)
    if not cal or cal[0] != SEASON_START:
        s["status"] = "waiting"
        s["ledger"], s["periods"] = [], []
        return
    s["status"] = "live"
    periods = []
    picks = [p["ticker"] for p in s["picks"]]
    port_level, bench_level = 100.0, 100.0
    entry_port = {t: close_on_or_before(state, t, cal[0])[1] for t in picks}
    entry_bench = {t: close_on_or_before(state, t, cal[0])[1] for t in members if close_on_or_before(state, t, cal[0])}
    periods.append({"start": cal[0], "picks": picks, "reason": "Locked picks, entry at the Oct 14 close"})
    ledger = [{"date": cal[0], "port": 100.0, "bench": 100.0, "stale": []}]
    base_p, base_b = port_level, bench_level
    for i in range(1, len(cal)):
        d = cal[i]
        stale = []
        pv = 0.0
        for t in picks:
            row = close_on_or_before(state, t, d)
            if row[0] != d:
                stale.append(t)
            pv += row[1] / entry_port[t]
        pv /= len(picks)
        bv = 0.0
        for t in entry_bench:
            row = close_on_or_before(state, t, d)
            bv += row[1] / entry_bench[t]
        bv /= len(entry_bench)
        port_level, bench_level = base_p * pv, base_b * bv
        ledger.append({"date": d, "port": round(port_level, 4), "bench": round(bench_level, 4), "stale": stale})
        # first trading day of a new month: rebalance at this close
        if d[:7] != cal[i - 1][:7]:
            gaps = gaps_at(state, d)
            new = [t for t, _g in sorted(gaps.items(), key=lambda kv: kv[1])[:5]]
            periods.append({"start": d, "picks": new, "reason": "Monthly rebalance: 5 most negative gaps at this close",
                            "gaps": {t: round(gaps[t], 4) for t in new}})
            picks = new
            base_p, base_b = port_level, bench_level
            entry_port = {t: close_on_or_before(state, t, d)[1] for t in picks}
            entry_bench = {t: close_on_or_before(state, t, d)[1] for t in members if close_on_or_before(state, t, d)}
    s["periods"] = periods
    s["ledger"] = ledger
    last = ledger[-1]
    s["summary"] = {
        "days": len(ledger) - 1, "as_of": last["date"],
        "port_return": round(last["port"] / 100 - 1, 6), "bench_return": round(last["bench"] / 100 - 1, 6),
        "excess": round(last["port"] / 100 - last["bench"] / 100, 6), "current_picks": picks,
    }
    # per-name returns since entry for the calls board
    first = cal[0]
    rets = {}
    for t in state["companies"]:
        a = close_on_or_before(state, t, first)
        b = close_on_or_before(state, t, cal[-1])
        if a and b and a[0] == first:
            rets[t] = b[1] / a[1] - 1
    bench_ret = last["bench"] / 100 - 1
    calls = []
    for t, c in state["companies"].items():
        v = c["lock"]["verdict"]
        if v not in ("Expectations too low", "Expectations too high") or t not in rets:
            continue
        rel = rets[t] - bench_ret
        right = rel > 0 if v == "Expectations too low" else rel < 0
        calls.append({"ticker": t, "call": "Too low" if v == "Expectations too low" else "Too high",
                      "ret": round(rets[t], 6), "rel": round(rel, 6), "right": right})
    calls.sort(key=lambda x: -abs(x["rel"]))
    s["calls"] = calls
    s["calls_right"] = sum(1 for x in calls if x["right"])
    s["name_returns"] = {t: round(r, 6) for t, r in rets.items()}


# ---------------------------------------------------------------- main
def recompute(state):
    for t, c in state["companies"].items():
        rows = state["prices"].get(t) or []
        if rows:
            recompute_company(c, rows)
    score_in_play(state)
    run_season(state)
    live_dates = [c["live"]["date"] for c in state["companies"].values() if c.get("live")]
    state["meta"]["last_close"] = max(live_dates) if live_dates else None
    state["meta"]["stale"] = sorted(t for t, c in state["companies"].items()
                                    if c.get("live") and c["live"]["date"] < state["meta"]["last_close"])
    state["meta"]["refreshed_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return state


def main(argv):
    path = argv[1]
    state = json.load(open(path))
    if len(argv) > 2 and argv[2] != "-":
        merge_prices(state, json.load(open(argv[2])))
    if len(argv) > 3:
        new_events = json.load(open(argv[3]))
        have = {(e["ticker"], e["date"], e["label"]) for e in state.get("events", [])}
        for e in new_events:
            if (e["ticker"], e["date"], e["label"]) not in have:
                state.setdefault("events", []).append(e)
    recompute(state)
    json.dump(state, open(path, "w"), separators=(",", ":"))
    ip = state["inplay"]
    s = state["season"]
    print(f"last close {state['meta']['last_close']}; stale: {', '.join(state['meta']['stale']) or 'none'}")
    print(f"In play: {ip['leader']} ({ip['ranking'][0]['score'] if ip['ranking'] else 0})")
    if s.get("status") == "live":
        sm = s["summary"]
        print(f"Season day {sm['days']}: picks {sm['port_return']*100:+.2f}% vs benchmark {sm['bench_return']*100:+.2f}% "
              f"(excess {sm['excess']*100:+.2f} pts); calls right {s['calls_right']} of {len(s['calls'])}")
    else:
        print("Season: waiting for the Oct 14 close")


if __name__ == "__main__":
    main(sys.argv)
