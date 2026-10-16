/* Priced In valuation engine, model v1.0 (JavaScript port of pipeline/engine.py).
   Years 1-5 grow at g; years 6-10 fade in a straight line to terminal growth;
   free cash flow = revenue x margin; terminal value after year 10; end-of-year
   discounting at WACC; equity = EV - debt + cash. tests/parity.mjs checks it
   against the Python pipeline. */
(function (root) {
  "use strict";
  var EXPLICIT = 5, FADE = 5, BAND = 0.03;

  function revenuePath(r0, g, gT) {
    var rev = r0, out = [];
    for (var t = 1; t <= EXPLICIT + FADE; t++) {
      var gt = t <= EXPLICIT ? g : g - (g - gT) * (t - EXPLICIT) / FADE;
      rev *= 1 + gt;
      out.push(rev);
    }
    return out;
  }

  function growthPath(g, gT) {
    var out = [];
    for (var t = 1; t <= EXPLICIT + FADE; t++) {
      out.push(t <= EXPLICIT ? g : g - (g - gT) * (t - EXPLICIT) / FADE);
    }
    return out;
  }

  function enterpriseValue(inp, g) {
    var revs = revenuePath(inp.revenue, g, inp.terminal_growth);
    var w = inp.wacc, pv = 0;
    for (var t = 1; t <= revs.length; t++) pv += revs[t - 1] * inp.fcf_margin / Math.pow(1 + w, t);
    var fcf10 = revs[revs.length - 1] * inp.fcf_margin;
    var tv = fcf10 * (1 + inp.terminal_growth) / (w - inp.terminal_growth);
    return pv + tv / Math.pow(1 + w, revs.length);
  }

  function valuePerShare(inp, g) {
    var equity = enterpriseValue(inp, g) - inp.debt + inp.cash - (inp.minority || 0);
    return equity / inp.shares;
  }

  function impliedGrowth(inp, price, lo, hi, tol) {
    lo = lo === undefined ? -0.5 : lo;
    hi = hi === undefined ? 1.0 : hi;
    tol = tol === undefined ? 1e-7 : tol;
    if (!(inp.wacc > inp.terminal_growth)) return null;
    var fLo = valuePerShare(inp, lo) - price, fHi = valuePerShare(inp, hi) - price;
    if (fLo > 0 || fHi < 0) return null;
    for (var i = 0; i < 200; i++) {
      var mid = (lo + hi) / 2;
      var fMid = valuePerShare(inp, mid) - price;
      if (Math.abs(fMid) < tol * Math.max(1, price) || (hi - lo) < 1e-9) return mid;
      if (fMid > 0) hi = mid; else lo = mid;
    }
    return (lo + hi) / 2;
  }

  /* The DCF table for one growth rate: what the company page shows step by step. */
  function schedule(inp, g) {
    var gs = growthPath(g, inp.terminal_growth), revs = revenuePath(inp.revenue, g, inp.terminal_growth);
    var rows = [], sum = 0;
    for (var t = 1; t <= revs.length; t++) {
      var fcf = revs[t - 1] * inp.fcf_margin, df = 1 / Math.pow(1 + inp.wacc, t), pv = fcf * df;
      sum += pv;
      rows.push({ year: t, growth: gs[t - 1], revenue: revs[t - 1], fcf: fcf, df: df, pv: pv });
    }
    var tv = rows[rows.length - 1].fcf * (1 + inp.terminal_growth) / (inp.wacc - inp.terminal_growth);
    var pvTv = tv * rows[rows.length - 1].df;
    var ev = sum + pvTv;
    var equity = ev - inp.debt + inp.cash - (inp.minority || 0);
    return { rows: rows, sumPv: sum, tv: tv, pvTv: pvTv, ev: ev, equity: equity, perShare: equity / inp.shares,
             tvShare: pvTv / ev };
  }

  function verdict(gap) {
    if (gap === null || gap === undefined || isNaN(gap)) return "n/a";
    if (gap >= BAND) return "Expectations too high";
    if (gap <= -BAND) return "Expectations too low";
    return "About right";
  }

  var api = { revenuePath: revenuePath, growthPath: growthPath, enterpriseValue: enterpriseValue,
              valuePerShare: valuePerShare, impliedGrowth: impliedGrowth, schedule: schedule, verdict: verdict,
              EXPLICIT: EXPLICIT, FADE: FADE, BAND: BAND, VERSION: "1.0" };
  root.PricedInEngine = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
