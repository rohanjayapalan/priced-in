# Priced In

What growth is already in the price? Priced In runs discounted cash flow models backwards for 19 exchanges and financial-data companies in Canada and the US. It takes each share price as given, solves for the five-year revenue growth that price implies, and compares that with an anchor built from past growth and analysts' forecasts.

**Live site:** https://rohanjayapalan.github.io/priced-in/, updated after every US close.

## What's in this repo

| Folder | What it holds |
| --- | --- |
| `pipeline/` | Python: the valuation engine, live valuations, the backtest, the daily refresh, and the builders for the site's data and the Excel models |
| `site/` | The website: one HTML page, the JavaScript engine behind its sliders, and its data file |
| `site/models/` | 19 Excel models, one per company, built with live formulas |
| `data/raw/` | The prices, filings and rates everything starts from |
| `data/out/` | Outputs: valuations at the lock, the locked Season 1 picks, backtest results |
| `tests/` | A check that the JavaScript engine matches the Python one |

## How it works (model v1.0, locked Oct 14, 2026)

1. Revenue grows at g for five years, then fades in a straight line to terminal growth by year 10.
2. Free cash flow each year is revenue times today's unlevered free-cash-flow margin (cash from operations minus capex, plus after-tax interest).
3. Terminal value is year-10 cash flow × (1 + terminal growth) ÷ (WACC − terminal growth).
4. Everything is discounted at WACC: CAPM with the 10-year government yield, Damodaran's implied equity risk premium, and a bottom-up beta (the median unlevered beta of the company's group, relevered for its own debt).
5. Enterprise value minus debt plus cash, divided by diluted shares, gives value per share.
6. Bisection finds the g where value per share equals the price. That is the implied growth.

Implied growth minus the anchor is the gap. Beyond 3 points either way, expectations look too high or too low. I set that band before running any backtest.

Each Excel model solves for implied growth with 40 rows of formulas, so it re-solves whenever an input changes, with no Goal Seek. A Check tab compares every result with the Python pipeline.

## Results

### Backtest

Monthly from Jan 2015 to Sep 2026 on 13 companies, using only filings public at each month-end. Each month I hold the five most negative gaps against an equal-weight portfolio of all 13, with a 0.10% cost per unit of turnover. The 90% ranges come from a circular block bootstrap.

| Treatment | All months | Outside COVID | Feb 2020 to Mar 2021 |
| --- | --- | --- | --- |
| As reported | −0.45%/yr (−4.1 to +3.3) | −1.38%/yr (−5.3 to +2.5) | +7.87%/yr |
| COVID-neutral fundamentals | +0.78%/yr | −0.22%/yr | +9.75%/yr |
| Plus a normalized risk-free rate | +0.92%/yr | −0.22%/yr | +11.13%/yr |

Outside COVID the screen didn't beat its group, and every range includes zero. I published this before the live season started.

### Season 1

Picks were locked on Oct 14, 2026 at 11:57 a.m. Eastern, before the close: TMX Group, Cboe, Tradeweb, SS&C and Fair Isaac. `data/out/season_v1_lock.json` records the picks and the time. The site scores them after every close against an equal-weight portfolio of the 18 names without a pending takeover.

## How it updates

A GitHub Actions workflow (`.github/workflows/daily-refresh.yml`) runs after every US close:

1. `pipeline/fetch_prices.py` gets the day's closing prices from Yahoo Finance, with Stooq as a backup.
2. `pipeline/fetch_events.py` checks SEC EDGAR for 8-K filings (results, deals, leadership changes) and Google News for bursts of coverage.
3. `pipeline/refresh.py` re-solves implied growth for every company, rescores In play, updates the Season 1 box score, and rebalances on the first trading day of each month.
4. The workflow commits `site/data/live.json` and publishes the `site/` folder to GitHub Pages.

Fundamentals stay fixed between quarterly updates, so day-to-day moves in implied growth come from the price alone.

## Run it

```bash
pip install -r requirements.txt
python3 pipeline/build_live.py          # valuations at the lock -> data/out/live_v1.csv
python3 pipeline/backtest.py            # backtest -> data/out/backtest_results.json
python3 pipeline/backtest_nofilter.py   # the same backtest with acquisitions counted as growth
python3 pipeline/build_site.py          # rebuilds site/data/live.json from data/raw
python3 pipeline/build_excel.py         # site/models/*.xlsx
node tests/parity.cjs                   # JavaScript engine vs Python

# the nightly refresh, by hand (the SEC asks for a contact: export SEC_USER_AGENT="Your Name you@example.com")
python3 pipeline/fetch_prices.py site/data/live.json prices_new.json
python3 pipeline/fetch_events.py site/data/live.json events_new.json
python3 pipeline/refresh.py site/data/live.json prices_new.json events_new.json
```

To view the site, serve the folder (`python3 -m http.server -d site`) and open http://localhost:8000. The data file in `site/data/` is the one the live site reads, so it includes every nightly update; `build_site.py` rebuilds it from the raw files as of the lock.

## Data sources

Stock Analysis (statistics, financials, price history), Yahoo Finance and Stooq (price history), SEC EDGAR (XBRL API and 8-K filings), Google News, US Treasury nominal and real yield curves, the Bank of Canada, Damodaran's implied equity risk premiums, and Kroll's normalized risk-free rate. Free pages sometimes lag; the site keeps the last close it has and shows its date.

## Limitations

- The free-cash-flow margin is held flat, and terminal value is often more than half of enterprise value.
- Some anchors include acquired revenue (TMX's analyst forecast, for example).
- The backtest covers 13 of the 19 companies and uses a simpler equity-level model.
- Nothing here is investment advice.

Built by Rohan Jayapalan.
