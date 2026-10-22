Priced In: code and data (model v1.0, locked Oct 14, 2026 at 11:57 a.m. Eastern)

Built by Rohan Jayapalan. Python 3.11+ with pandas, numpy and openpyxl (plus yfinance for the nightly prices); Node 18+ for the parity test.
Full repository: https://github.com/rohanjayapalan/priced-in

Layout when rebuilt locally
  pipeline/engine.py            the reverse DCF (value per share, implied growth by bisection, WACC, verdict)
  pipeline/build_live.py        today's valuations for the 19 companies -> data/out/live_v1.csv
  pipeline/backtest.py          point-in-time monthly backtest, three COVID treatments -> data/out/backtest_results.json
  pipeline/backtest_nofilter.py the same backtest with acquisitions counted as growth (disclosure run)
  pipeline/build_site.py        assembles site/data/live.json for the site
  pipeline/build_excel.py       19 live-formula Excel models (recalculate with LibreOffice before reading values)
  pipeline/refresh.py           the daily refresh: new closes in, implied growth, In play and the season out
  pipeline/fetch_prices.py      nightly closing prices from Yahoo Finance, with Stooq as a backup
  pipeline/fetch_events.py      nightly 8-K filings from SEC EDGAR and Google News bursts, for In play
  .github/workflows/daily-refresh.yml   runs the three nightly steps after each US close, commits the data and publishes the site
  site/engine.js                the same engine in JavaScript for the site's sliders
  tests/parity.cjs              checks the JavaScript engine against the Python numbers

data.json maps each original file path (data/raw/... and data/out/...) to its contents. Write each entry
back to its path to rebuild.

Rebuild everything
  python3 pipeline/build_live.py
  python3 pipeline/backtest.py
  python3 pipeline/backtest_nofilter.py
  python3 pipeline/build_site.py
  python3 pipeline/build_excel.py
  node tests/parity.cjs

Daily refresh (what the GitHub Actions workflow runs after each US close)
  python3 pipeline/fetch_prices.py site/data/live.json prices_new.json
  python3 pipeline/fetch_events.py site/data/live.json events_new.json   (set SEC_USER_AGENT to "Your Name you@example.com" first)
  python3 pipeline/refresh.py site/data/live.json prices_new.json events_new.json

Sources: Stock Analysis (statistics, financials, price history), Yahoo Finance and Stooq (price history), SEC EDGAR XBRL
company concepts and 8-K filings, Google News, US Treasury par and real yield curves, Bank of Canada Valet, Damodaran's implied equity risk
premiums, Kroll's normalized risk-free rate. See the Method page for links.
