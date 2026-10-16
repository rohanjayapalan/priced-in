"""Robustness check: the as-reported backtest without the acquisition filter.

Same settings as backtest.py, except every year of revenue growth counts in the
anchor (no +25% / -20% cut). Written to data/out/backtest_nofilter.json.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import backtest as B

B.MA_UP, B.MA_DOWN = 10.0, -10.0
panel = B.build_panel()
res = B.run_portfolio(panel)
out = {
    "all_months": B.stats(res, "All months"),
    "ex_covid": B.stats(res[~res["held"].map(B.in_covid)], "Excluding Feb 2020 to Mar 2021"),
    "covid_only": B.stats(res[res["held"].map(B.in_covid)], "Feb 2020 to Mar 2021 only"),
    "train": B.stats(res[res["held"] <= "2024-12"], "2015 to 2024 (design period)"),
    "holdout": B.stats(res[res["held"] >= "2025-01"], "2025 to 2026 (held out)"),
}
res.to_csv(os.path.join(B.OUT, "bt_months_no_filter.csv"), index=False)
json.dump(out, open(os.path.join(B.OUT, "backtest_nofilter.json"), "w"), indent=2)
for k, v in out.items():
    print(f"{v['label']:<34} n={v['months']:>3} excess/yr {v['excess_ann']*100:6.2f}% 90% [{v['excess_ann_lo90']*100:6.2f}, {v['excess_ann_hi90']*100:6.2f}] hit {v['hit_rate']*100:4.1f}%")
