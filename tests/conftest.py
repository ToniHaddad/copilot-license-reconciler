import csv
import shutil
from pathlib import Path

import pytest

from reconciler import pipeline
from reconciler.config import DEFAULT_AS_OF, RAW_DIR


@pytest.fixture(scope="session")
def wh():
    """The warehouse built from the committed raw fixtures at the default decision date."""
    con = pipeline.connect(":memory:")
    pipeline.build_warehouse(con, RAW_DIR, DEFAULT_AS_OF)
    yield con
    con.close()


@pytest.fixture()
def fresh():
    con = pipeline.connect(":memory:")
    yield con
    con.close()


def build_at(as_of, raw=RAW_DIR, **kw):
    con = pipeline.connect(":memory:")
    pipeline.build_warehouse(con, raw, as_of, **kw)
    return con


def make_raw(tmp: Path, invoices, events, usage=(), received="2026-04-05"):
    """Write a tiny raw folder. invoices: (office, period, qty, unit); events: tuples; usage: (office, period, user, days)."""
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "invoices").mkdir(exist_ok=True)
    (tmp / "events").mkdir(exist_ok=True)
    (tmp / "usage").mkdir(exist_ok=True)
    manifest = []
    for office, period, qty, unit in invoices:
        name = f"invoices/inv_{office}_{period}.csv"
        with (tmp / name).open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["invoice_id", "office", "period", "sku", "description", "quantity", "unit_price", "amount", "currency"])
            w.writerow([f"INV-{office}-{period}", office, period, "M365-COPILOT", "seats", qty, f"{unit / 100:.2f}", f"{qty * unit / 100:.2f}", "USD"])
        manifest.append([name, "invoice", office, period, received])
    name = "events/events.csv"
    with (tmp / name).open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["event_id", "event_date", "office", "seat_id", "event_type", "user_id", "from_user_id"])
        for i, ev in enumerate(events, start=1):
            w.writerow([f"E{i:03d}", *ev])
    manifest.append([name, "events", "LB", "all", received])
    by = {}
    for office, period, user, days in usage:
        by.setdefault((office, period), []).append((user, days))
    for (office, period), rows in by.items():
        name = f"usage/usage_{office}_{period}.csv"
        with (tmp / name).open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["office", "report_month", "user_id", "active_days", "copilot_actions", "last_activity_date"])
            for user, days in rows:
                w.writerow([office, period, user, days, days * 5, ""])
        manifest.append([name, "usage", office, period, received])
    with (tmp / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["file_name", "kind", "office", "period", "received_date"])
        w.writerows(manifest)
    return tmp
