"""Seeded generator for the three synthetic inputs of a humanitarian organization in Lebanon.

Everything here is synthetic and every vendor, product and price is invented. Run
`python -m reconciler generate` to rewrite data/raw; the same seed always gives the same bytes.
The deliberate mess is listed in MESSES and documented in docs/data-mess.md.
"""
from __future__ import annotations

import calendar
import csv
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

from .config import (CENTRES, DEPARTMENTS, FIRST_MONTH, N_MONTHS, PRODUCTS, RAW_DIR, SEED, UNIT_CENTS)

MESSES = [
    "Staff moved between centres: JBE-007 moves from Jbeil to Saida on 2026-05-12. Their Jbeil office-suite seat is "
    "reassigned to a replacement that day and a new Saida seat opens. They appear in two centre reports in May.",
    "Seat reassigned mid-month inside one centre: the AI add-on seat S-HQ-ASSIST-05 changes hands on 2026-04-17, "
    "so two people touch one seat in the same month.",
    "Duplicate invoice file: invoice_ASSIST_2026-04.csv arrives a second time as 'invoice_ASSIST_2026-04 (1).csv' "
    "with identical content.",
    "Late usage report: the Tripoli report for 2026-08 is due 2026-09-05 and arrives 2026-10-06, after "
    "the default decision date, so those seat-months are unknown, not inactive.",
    "Late report changes the answer: TRI-002 is silent May to July and active again in August, which only the late "
    "Tripoli report shows.",
    "Late onboarding: Saida's 12 AI add-on seats are all assigned on 2026-03-04, but training was delayed. "
    "Use is near zero until July, then matches the other centres. Saida's other products are healthy throughout.",
    "Seats billed that nobody holds: invoices bill more seats than the assignment log mentions "
    "(2 AI and 2 office-suite seats at head office, 1 AI at Jbeil, 1 survey at Zahle).",
    "Missing row: ZAH-004 is absent from the Zahle July report for the AI add-on.",
    "Dirty ids: the Jbeil June report has lower case ids with trailing spaces.",
    "Repeated row: HQ-002 appears twice in the head office July report for the office suite.",
    "Event log is exported in no particular order.",
]

# (product, centre) -> number of staff holding a seat from the start, start date, spare billed seats
PLAN = {
    ("OFFICE", "ZAH"): (20, "2026-03-02", 0), ("OFFICE", "JBE"): (24, "2026-03-02", 0),
    ("OFFICE", "SAI"): (18, "2026-03-02", 0), ("OFFICE", "TRI"): (16, "2026-03-02", 0),
    ("OFFICE", "HQ"): (40, "2026-03-02", 2),
    ("ASSIST", "ZAH"): (8, "2026-03-02", 0), ("ASSIST", "JBE"): (12, "2026-03-02", 1),
    ("ASSIST", "SAI"): (12, "2026-03-04", 0), ("ASSIST", "TRI"): (6, "2026-03-02", 0),
    ("ASSIST", "HQ"): (18, "2026-03-02", 2),
    ("SURVEY", "ZAH"): (6, "2026-03-02", 1), ("SURVEY", "JBE"): (6, "2026-03-02", 0),
    ("SURVEY", "SAI"): (5, "2026-03-02", 0), ("SURVEY", "TRI"): (4, "2026-03-02", 0),
    ("SURVEY", "HQ"): (3, "2026-03-02", 0),
    ("FLOW", "HQ"): (4, "2026-03-02", 0), ("FLOW", "JBE"): (2, "2026-03-02", 0),
}
# later seats: (product, centre) -> (staff numbers, first date)
EXTRA = {
    ("ASSIST", "TRI"): ([7, 8, 9, 10], "2026-05-04"),
    ("ASSIST", "SAI"): ([13, 14], "2026-07-06"),
}


def months() -> list[tuple[int, int]]:
    y, m = FIRST_MONTH
    out = []
    for _ in range(N_MONTHS):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def dim(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def d(s: str) -> date:
    return date.fromisoformat(s)


def uid(centre: str, n: int) -> str:
    return f"{centre}-{n:03d}"


def dept(user: str) -> str:
    return DEPARTMENTS[int(user[-3:]) % 3]


class Log:
    def __init__(self, centre: str):
        self.centre = centre
        self.events: list[dict] = []

    def ev(self, kind, product, seat, user, when: date, from_user=""):
        self.events.append({
            "event_id": f"E-{self.centre}-{len(self.events) + 1:04d}",
            "event_date": when.isoformat(), "centre": self.centre, "product": product,
            "seat_id": seat, "event_type": kind, "user_id": user, "from_user_id": from_user,
        })


def seat_id(product: str, centre: str, n: int) -> str:
    return f"S-{centre}-{product}-{n:02d}"


def build_events(rng: random.Random) -> dict[str, Log]:
    logs = {c: Log(c) for c in CENTRES}
    for (product, centre), (n, start, _) in PLAN.items():
        for i in range(1, n + 1):
            jitter = 0 if (product, centre) == ("ASSIST", "SAI") else rng.randint(0, 3)
            logs[centre].ev("assign", product, seat_id(product, centre, i), uid(centre, i), d(start) + timedelta(days=jitter))
    for (product, centre), (nums, start) in EXTRA.items():
        for i in nums:
            logs[centre].ev("assign", product, seat_id(product, centre, i), uid(centre, i), d(start) + timedelta(days=rng.randint(0, 4)))

    # a staff member moves from Jbeil to Saida: Jbeil seat goes to a replacement, Saida opens a seat
    logs["JBE"].ev("reassign", "OFFICE", seat_id("OFFICE", "JBE", 7), uid("JBE", 31), d("2026-05-12"), from_user=uid("JBE", 7))
    logs["SAI"].ev("assign", "OFFICE", seat_id("OFFICE", "SAI", 19), uid("JBE", 7), d("2026-05-12"))
    # an AI seat changes hands inside head office
    logs["HQ"].ev("reassign", "ASSIST", seat_id("ASSIST", "HQ", 5), uid("HQ", 41), d("2026-04-17"), from_user=uid("HQ", 5))
    # leavers
    logs["HQ"].ev("unassign", "OFFICE", seat_id("OFFICE", "HQ", 33), uid("HQ", 33), d("2026-06-09"))
    logs["ZAH"].ev("unassign", "OFFICE", seat_id("OFFICE", "ZAH", 15), uid("ZAH", 15), d("2026-06-24"))
    logs["HQ"].ev("unassign", "ASSIST", seat_id("ASSIST", "HQ", 8), uid("HQ", 8), d("2026-06-20"))
    return logs


def intervals(events: list[dict]):
    """Replay events into (seat, user, start, end_exclusive_or_None). Mirrors the SQL rule."""
    by_seat: dict[str, list[dict]] = {}
    for e in events:
        by_seat.setdefault(e["seat_id"], []).append(e)
    out = []
    for seat, evs in by_seat.items():
        evs = sorted(evs, key=lambda e: (e["event_date"], e["event_id"]))
        for i, e in enumerate(evs):
            if e["event_type"] == "unassign":
                continue
            end = d(evs[i + 1]["event_date"]) if i + 1 < len(evs) else None
            out.append((seat, e["user_id"], d(e["event_date"]), end))
    return out


def days_held(ivs, user: str, y: int, m: int) -> int:
    ms, me = date(y, m, 1), date(y, m, dim(y, m)) + timedelta(days=1)
    n = 0
    for _, u, s, e in ivs:
        if u != user:
            continue
        lo, hi = max(s, ms), min(e or me, me)
        if hi > lo:
            n += (hi - lo).days
    return n


LAPSED = {("ASSIST", "JBE"): {"JBE-004", "JBE-009"}, ("ASSIST", "TRI"): {"TRI-002", "TRI-005"},
          ("ASSIST", "HQ"): {"HQ-011", "HQ-014", "HQ-016"}, ("SURVEY", "JBE"): {"JBE-005"},
          ("SURVEY", "ZAH"): {"ZAH-006"}}                       # active Mar-Apr, silent from May
NEVER = {("FLOW", "HQ"): {"HQ-004"}, ("ASSIST", "HQ"): {"HQ-018"}}
ONE_OFF = {("ASSIST", "HQ"): {"HQ-012": 5, "HQ-013": 4}}         # silent in one month only
RESUME = {("ASSIST", "TRI"): {"TRI-002"}}                         # back in August
SAI_NEVER = {"SAI-005", "SAI-010"}                               # still not started in August
SAI_JULY_IDLE = {"SAI-013", "SAI-014"}                           # assigned in July, not started


def active_days(rng, product, centre, user, mi, held, base) -> int:
    key = (product, centre)
    if key == ("ASSIST", "SAI"):
        if user in SAI_NEVER or user in SAI_JULY_IDLE:
            n = rng.choice([0, 0, 0, 1])
        elif mi <= 1:
            n = rng.choice([0] * 9 + [1])
        elif mi == 2:
            n = rng.choice([0, 0, 0, 1, 1, 2])
        elif mi == 3:  # June: the first trained cohort starts at the very end
            n = rng.randint(3, 5) if int(user[-3:]) % 7 == 0 else rng.choice([0, 0, 1, 2])
        elif mi == 4:
            n = rng.randint(5, 13)
        else:
            n = rng.randint(7, 16)
    else:
        n = max(0, int(rng.gauss(base[(product, user)], 2.5)))
        if user in LAPSED.get(key, ()) and mi >= 2:
            n = rng.choice([0, 0, 1])
        if user in RESUME.get(key, ()) and mi == 5:
            n = rng.randint(6, 10)
        if user in NEVER.get(key, ()):
            n = rng.choice([0, 0, 1])
        if user in ONE_OFF.get(key, {}) and mi == ONE_OFF[key][user]:
            n = rng.choice([0, 1])
        n = max(n, 4) if n > 1 else n
    return min(n, held, 22)


def write_csv(path: Path, header: list[str], rows: list[list]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def next_month(y, m):
    return (y, m + 1) if m < 12 else (y + 1, 1)


def generate(out: Path = RAW_DIR) -> Path:
    rng = random.Random(SEED)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    logs = build_events(rng)
    manifest: list[list] = []
    mlist = months()

    # events: one file per centre (all products), shuffled
    for code, log in logs.items():
        rows = [list(e.values()) for e in log.events]
        rng.shuffle(rows)
        name = f"assignment_events_{code}.csv"
        write_csv(out / "events" / name, list(log.events[0].keys()), rows)
        manifest.append([f"events/{name}", "events", code, "ALL", "2026-03..2026-08", "2026-09-14"])

    # seats billed per product, centre and month: every seat that exists, plus spare seats nobody holds
    all_events = [e for log in logs.values() for e in log.events]
    first = {}
    for e in all_events:
        first.setdefault((e["product"], e["centre"], e["seat_id"]), e["event_date"][:7])
        first[(e["product"], e["centre"], e["seat_id"])] = min(first[(e["product"], e["centre"], e["seat_id"])], e["event_date"][:7])

    def qty(product, centre, period):
        spare = PLAN.get((product, centre), (0, "", 0))[2]
        return spare + sum(1 for (p, c, _), fm in first.items() if p == product and c == centre and fm <= period)

    # invoices: one file per product and month, one line per centre
    hdr = ["invoice_id", "centre", "period", "product", "description", "quantity", "unit_price", "amount", "currency"]
    for product, (pname, kind, vendor, unit) in PRODUCTS.items():
        for y, m in mlist:
            period = f"{y}-{m:02d}"
            rows = []
            for centre in CENTRES:
                q = qty(product, centre, period)
                if q:
                    rows.append([f"INV-{product}-{period}", centre, period, product, f"{pname} ({vendor}), per seat per month",
                                 q, f"{unit / 100:.2f}", f"{q * unit / 100:.2f}", "USD"])
            name = f"invoice_{product}_{period}.csv"
            write_csv(out / "invoices" / name, hdr, rows)
            ny, nm = next_month(y, m)
            manifest.append([f"invoices/{name}", "invoice", "ALL", product, period, f"{ny}-{nm:02d}-03"])
            if product == "ASSIST" and period == "2026-04":
                dup = "invoice_ASSIST_2026-04 (1).csv"
                shutil.copyfile(out / "invoices" / name, out / "invoices" / dup)
                manifest.append([f"invoices/{dup}", "invoice", "ALL", product, period, "2026-05-06"])

    # usage: one file per centre and month, covering every product the centre has
    base = {(p, uid(c, i)): rng.randint(7, 15) for p in PRODUCTS for c in CENTRES for i in range(1, 60)}
    for code, log in logs.items():
        for mi, (y, m) in enumerate(mlist):
            rows = []
            for product in PRODUCTS:
                evs = [e for e in log.events if e["product"] == product]
                if not evs:
                    continue
                ivs = intervals(evs)
                for u in sorted({u for _, u, _, _ in ivs}):
                    held = days_held(ivs, u, y, m)
                    if held == 0:
                        continue
                    if (product, code, u, mi) == ("ASSIST", "ZAH", "ZAH-004", 4):
                        continue  # missing row
                    n = active_days(rng, product, code, u, mi, held, base)
                    actions = n * rng.randint(6, 18)
                    last = ""
                    if n > 0:
                        last = date(y, m, min(dim(y, m), max(1, held if held < 10 else rng.randint(20, dim(y, m))))).isoformat()
                    shown = f"{u.lower()} " if (code == "JBE" and mi == 3) else u
                    row = [code, f"{y}-{m:02d}", product, shown, dept(u), n, actions, last]
                    rows.append(row)
                    if (product, code, u, mi) == ("OFFICE", "HQ", "HQ-002", 4):
                        rows.append(row)  # repeated row
            name = f"usage_{code}_{y}-{m:02d}.csv"
            write_csv(out / "usage" / name,
                      ["centre", "report_month", "product", "user_id", "department", "active_days", "actions", "last_activity_date"], rows)
            ny, nm = next_month(y, m)
            received = f"{ny}-{nm:02d}-0{rng.randint(5, 8)}"
            if code == "TRI" and (y, m) == (2026, 8):
                received = "2026-10-06"
            manifest.append([f"usage/{name}", "usage", code, "ALL", f"{y}-{m:02d}", received])

    write_csv(out / "manifest.csv", ["file_name", "kind", "centre", "product", "period", "received_date"], manifest)
    return out


if __name__ == "__main__":
    print(generate())
