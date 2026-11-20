"""Constants shared by the generator, the runner and the report."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
BUILD_DIR = ROOT / "build"
SQL_DIR = Path(__file__).resolve().parent / "sql"
DB_PATH = BUILD_DIR / "warehouse.duckdb"
REPORT_PATH = BUILD_DIR / "report.html"
PORT = 8106

SEED = 20260920
ORG = "Northbridge Relief"
SKU = "M365-COPILOT"

# office code -> (name, unit price in cents per seat per month)
OFFICES = {
    "LB": ("Lebanon", 3000),
    "KE": ("Kenya", 3000),
    "CO": ("Colombia", 2760),
}
FIRST_MONTH = (2026, 3)
N_MONTHS = 6  # 2026-03 .. 2026-08

# Next quarter and what each office asked for (synthetic).
FORECAST_MONTHS = 3
FORECAST_LABEL = "Q4 2026 (Oct to Dec)"
REQUESTS = {"LB": 8, "KE": 10, "CO": 6}

# Decision date: files received after this are not yet in the pipeline.
DEFAULT_AS_OF = "2026-09-20"

# Rules (also written to the params table so SQL can read them).
PARAMS = {
    "active_days_threshold": 3,   # active_days >= this: seat-month is active
    "min_days_held": 14,          # held fewer days than this: low usage proves nothing
    "min_tenure_days": 60,        # seat holder must have held the seat this long
    "onboarding_share": 0.20,     # office "has started" when this share of seats is active
    "grace_months": 2,            # months after the start still treated as ramp-up
}
