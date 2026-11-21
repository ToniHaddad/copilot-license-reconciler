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
ORG = "a humanitarian organization in Lebanon"
ORG_SHORT = "the Organization"

# Centre code -> name. The Organization runs its own centres; head office is one of them.
CENTRES = {
    "ZAH": "Zahle",
    "JBE": "Jbeil",
    "SAI": "Saida",
    "TRI": "Tripoli",
    "HQ": "Head office",
}
DEPARTMENTS = ["Social", "Medical", "Logistics"]

# Product code -> (name, what it is, vendor, unit price in cents per seat per month). All invented.
PRODUCTS = {
    "OFFICE": ("Cedar Suite", "Office suite", "Cedarline Software", 1250),
    "ASSIST": ("Cedar Assist", "AI assistant add-on", "Cedarline Software", 2000),
    "SURVEY": ("FieldForm Pro", "Survey and data collection", "Fieldform Labs", 1800),
    "FLOW": ("FlowLoop", "Automation platform", "Loopwork Ltd", 2400),
}
PRODUCT_NAME = {k: v[0] for k, v in PRODUCTS.items()}
PRODUCT_KIND = {k: v[1] for k, v in PRODUCTS.items()}
UNIT_CENTS = {k: v[3] for k, v in PRODUCTS.items()}

FIRST_MONTH = (2026, 3)
N_MONTHS = 6  # 2026-03 .. 2026-08

# The decision: three centres ask for more AI assistant seats next quarter (synthetic).
FORECAST_PRODUCT = "ASSIST"
FORECAST_MONTHS = 3
FORECAST_LABEL = "Q4 2026 (Oct to Dec)"
REQUESTS = {"ZAH": 6, "SAI": 8, "TRI": 5}

# Decision date: files received after this are not yet in the pipeline.
DEFAULT_AS_OF = "2026-09-20"

# Rules (also written to the params table so SQL can read them).
PARAMS = {
    "active_days_threshold": 3,   # active_days >= this: seat-month is active
    "min_days_held": 14,          # held fewer days than this: low usage proves nothing
    "min_tenure_days": 60,        # seat holder must have held the seat this long
    "onboarding_share": 0.20,     # a centre "has started" when this share of seats is active
    "grace_months": 2,            # months after the start still treated as ramp-up
}
