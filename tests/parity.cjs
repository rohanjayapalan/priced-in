// Parity check: the site's JavaScript engine against the Python pipeline's numbers in live.json.
const path = require("path");
const fs = require("fs");
const E = require(path.join(__dirname, "..", "site", "engine.js"));
const state = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "site", "data", "live.json"), "utf8"));

let worst = 0, n = 0, fails = [];
for (const [t, c] of Object.entries(state.companies)) {
  const inp = c.inputs;
  const g = E.impliedGrowth(inp, c.live.price);
  const d = Math.abs(g - c.live.implied);
  worst = Math.max(worst, d); n++;
  if (d > 1e-6) fails.push(`${t} implied js=${g} py=${c.live.implied}`);
  // sensitivity grid A
  const s = c.live.sens_wacc_tg;
  s.waccs.forEach((w, i) => s.tgs.forEach((tg, j) => {
    const v = E.impliedGrowth({ ...inp, wacc: w, terminal_growth: tg }, c.live.price);
    const py = s.grid[i][j];
    if (py === null || v === null) { if (py !== v) fails.push(`${t} grid A ${i},${j} js=${v} py=${py}`); return; }
    const dd = Math.abs(v - py); worst = Math.max(worst, dd); n++;
    if (dd > 1e-5) fails.push(`${t} grid A ${i},${j} js=${v} py=${py}`);
  }));
  // sensitivity grid B (value per share)
  const b = c.live.sens_view_wacc;
  b.waccs.forEach((w, i) => b.views.forEach((v, j) => {
    const js = E.valuePerShare({ ...inp, wacc: w }, v);
    const dd = Math.abs(js - b.grid[i][j]); n++;
    if (dd > 0.006) fails.push(`${t} grid B ${i},${j} js=${js} py=${b.grid[i][j]}`);
  }));
  // schedule per-share equals valuePerShare
  const sc = E.schedule(inp, c.anchor.anchor);
  if (Math.abs(sc.perShare - E.valuePerShare(inp, c.anchor.anchor)) > 1e-9) fails.push(`${t} schedule mismatch`);
}
console.log(`compared ${n} numbers across ${Object.keys(state.companies).length} companies; worst implied-growth difference ${worst.toExponential(2)}`);
if (fails.length) { console.log("FAIL\n" + fails.join("\n")); process.exit(1); }
console.log("PASS");
