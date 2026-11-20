# copilot-license-reconciler

Python + DuckDB + SQL. Rebuilds which Copilot licences are paid for, assigned and used
for a synthetic NGO (Northbridge Relief: Lebanon, Kenya, Colombia) and forecasts next
quarter under two options. All data is synthetic and seeded. No API key, no network.

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
- `reconciler/generate.py` seeded fixtures; the list of deliberate mess is in `MESSES`
- `reconciler/report.py` the single self-contained HTML page (inline SVG, no CDN)
- `data/raw` committed fixtures; `data/raw/manifest.csv` holds received dates
- `tests/` pytest over the SQL; `docs/` screenshots and notes on the data mess

## Quirks
- Raw load is idempotent by file name and sha256; a changed file under an old name is refused.
- Files received after `--as-of` are loaded but ignored by staging (that is the late report).
- Money is integer cents everywhere; seat-months are split by day with cumulative rounding.
- If fixtures change, regenerate and update the numbers asserted in `tests/test_pipeline.py`.
