import csv
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
    """Write a tiny raw folder.
    invoices: (centre, product, period, qty, unit_cents)
    events:   (date, centre, product, seat, type, user, from_user)
    usage:    (centre, period, product, user, active_days)"""
    for sub in ("invoices", "events", "usage"):
        (tmp / sub).mkdir(parents=True, exist_ok=True)
    manifest = []
    for centre, product, period, qty, unit in invoices:
        name = f"invoices/inv_{product}_{centre}_{period}.csv"
        with (tmp / name).open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["invoice_id", "centre", "period", "product", "description", "quantity", "unit_price", "amount", "currency"])
            w.writerow([f"INV-{product}-{centre}-{period}", centre, period, product, "seats", qty,
                        f"{unit / 100:.2f}", f"{qty * unit / 100:.2f}", "USD"])
        manifest.append([name, "invoice", "ALL", product, period, received])
    name = "events/events.csv"
    with (tmp / name).open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["event_id", "event_date", "centre", "product", "seat_id", "event_type", "user_id", "from_user_id"])
        for i, ev in enumerate(events, start=1):
            w.writerow([f"E{i:03d}", *ev])
    manifest.append([name, "events", "ZAH", "ALL", "all", received])
    by = {}
    for centre, period, product, user, days in usage:
        by.setdefault((centre, period), []).append((product, user, days))
    for (centre, period), rows in by.items():
        name = f"usage/usage_{centre}_{period}.csv"
        with (tmp / name).open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["centre", "report_month", "product", "user_id", "department", "active_days", "actions", "last_activity_date"])
            for product, user, days in rows:
                w.writerow([centre, period, product, user, "Social", days, days * 5, ""])
        manifest.append([name, "usage", centre, "ALL", period, received])
    with (tmp / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["file_name", "kind", "centre", "product", "period", "received_date"])
        w.writerows(manifest)
    return tmp
