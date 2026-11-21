# software-seat-reconciler

Python + DuckDB + SQL. Rebuilds which paid software seats of a humanitarian organization in Lebanon are
assigned and used, per product and centre, and forecasts next quarter for one decision: three centres ask
for more AI assistant seats, buy or move idle ones first. All data is synthetic and seeded; vendors,
products and prices are invented. No API key, no network.

## Run
- `pip install -e ".[dev]"`
- `python -m reconciler build` rebuilds the DuckDB warehouse and `build/report.html`
  (`--as-of YYYY-MM-DD` sets the decision date, `--fresh` deletes the warehouse first)
- `python -m reconciler serve` serves the report on port 8106
- `python -m reconciler generate` rewrites `data/raw` (same seed, same bytes)
- `python -m reconciler sensitivity` prints how candidates move with threshold and date
- `python -m pytest -q`

## Layout
- `reconciler/sql/NN_*.sql` the pipeline, run in order by `pipeline.py`
  (raw, staging, intervals, spend, classify, candidates, forecast, evidence, summary)
- `reconciler/config.py` centres, products, prices, requests, rules
- `reconciler/generate.py` seeded fixtures; the list of deliberate mess is in `MESSES`
- `reconciler/report.py` + `report_style.py` the single self-contained HTML page (inline SVG, no CDN)
- `data/raw` committed fixtures; `manifest.csv` holds received dates
- `tests/` pytest over the SQL; `docs/` screenshots and notes on the data mess

## Quirks
- Product is part of every key (centre, product, month). Seat ids belong to one product.
- Raw load is idempotent by file name and sha256; a changed file under an old name is refused.
- Files received after `--as-of` are loaded but ignored by staging (that is the late report).
- Money is integer cents; seat-months are split by day with cumulative rounding.
- The forecast covers `FORECAST_PRODUCT` only. If fixtures change, regenerate and update the numbers
  asserted in `tests/test_pipeline.py`.
- Everything pushed is public: nothing real, no organization name.
