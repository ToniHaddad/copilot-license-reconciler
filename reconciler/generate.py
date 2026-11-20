"""Seeded generator for the three synthetic inputs (Northbridge Relief).

Everything here is synthetic. Run `python -m reconciler generate` to rewrite
data/raw; the same seed always gives the same bytes. The deliberate mess is
listed in MESSES and documented in docs/data-mess.md.
"""
from __future__ import annotations

import calendar
import csv
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

from .config import FIRST_MONTH, N_MONTHS, OFFICES, RAW_DIR, SEED, SKU

MESSES = [
    "Reassignment mid-month: seat S-LB-12 moves between users on 2026-04-17 and S-CO-17 on 2026-05-12, "
    "so two users touch one seat in the same month. Counting users instead of seat-days double counts.",
    "Duplicate invoice file: invoice_LB_2026-04.csv arrives a second time as 'invoice_LB_2026-04 (1).csv' "
    "with identical content.",
    "Late usage report: the Colombia report for 2026-08 is due 2026-09-05 and arrives 2026-10-06, after "
    "the default decision date, so those seat-months are unknown, not inactive.",
    "Late onboarding: Kenya assigns 30 seats on one day in March, but training starts in late June. "
    "Usage is near zero until July, then matches the other offices.",
    "Spare seats: invoices bill more seats than the assignment log ever mentions (2 in Lebanon, 3 in Colombia).",
    "Late report changes the answer: CO-033 is silent May to July and active again in August, which only the late Colombia report shows.",
    "Missing row: user CO-015 is absent from the Colombia July report.",
    "Dirty ids: the Colombia June report has lower case ids with trailing spaces.",
    "Repeated row: user KE-005 appears twice in the Kenya July report.",
    "Event log is exported in no particular order.",
]


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


class Office:
    def __init__(self, code: str):
        self.code = code
        self.events: list[dict] = []
        self.counter = 0

    def ev(self, kind: str, seat: str, user: str, when: date, from_user: str = ""):
        self.counter += 1
        self.events.append(
            {
                "event_id": f"E-{self.code}-{self.counter:04d}",
                "event_date": when.isoformat(),
                "office": self.code,
                "seat_id": seat,
                "event_type": kind,
                "user_id": user,
                "from_user_id": from_user,
            }
        )


def uid(code: str, n: int) -> str:
    return f"{code}-{n:03d}"


def build_events(rng: random.Random) -> dict[str, Office]:
    offs = {c: Office(c) for c in OFFICES}

    # Lebanon: 30 seats in early March, 6 more in May, one reassign, two leavers.
    lb = offs["LB"]
    for i in range(1, 31):
        lb.ev("assign", f"S-LB-{i:02d}", uid("LB", i), d("2026-03-02") + timedelta(days=rng.randint(0, 3)))
    for i in range(31, 37):
        lb.ev("assign", f"S-LB-{i:02d}", uid("LB", i), d("2026-05-04") + timedelta(days=rng.randint(0, 4)))
    lb.ev("reassign", "S-LB-12", uid("LB", 37), d("2026-04-17"), from_user=uid("LB", 12))
    lb.ev("unassign", "S-LB-07", uid("LB", 7), d("2026-06-09"))
    lb.ev("unassign", "S-LB-19", uid("LB", 19), d("2026-06-24"))

    # Kenya: one bulk assignment of 30 seats on a single day, 8 more in July.
    ke = offs["KE"]
    for i in range(1, 31):
        ke.ev("assign", f"S-KE-{i:02d}", uid("KE", i), d("2026-03-04"))
    for i in range(31, 39):
        ke.ev("assign", f"S-KE-{i:02d}", uid("KE", i), d("2026-07-06") + timedelta(days=rng.randint(0, 4)))

    # Colombia: 42 seats in early March, one reassign, one leaver.
    co = offs["CO"]
    for i in range(1, 43):
        co.ev("assign", f"S-CO-{i:02d}", uid("CO", i), d("2026-03-02") + timedelta(days=rng.randint(0, 4)))
    co.ev("reassign", "S-CO-17", uid("CO", 43), d("2026-05-12"), from_user=uid("CO", 17))
    co.ev("unassign", "S-CO-31", uid("CO", 31), d("2026-07-15"))
    return offs


# invoiced seats per month (index 0 = March) -- includes spare seats never assigned
INVOICED = {
    "LB": [32, 32, 38, 38, 38, 38],
    "KE": [30, 30, 30, 30, 38, 38],
    "CO": [45, 45, 45, 45, 45, 45],
}


def intervals(events: list[dict]):
    """Replay events into (seat, user, start, end_exclusive_or_None). Mirrors the SQL rule."""
    by_seat: dict[str, list[dict]] = {}
    for e in events:
        by_seat.setdefault(e["seat_id"], []).append(e)
    out = []
    for seat, evs in by_seat.items():
        evs = sorted(evs, key=lambda e: (e["event_date"], e["event_id"]))
        for i, e in enumerate(evs):
            holder = None if e["event_type"] == "unassign" else e["user_id"]
            if holder is None:
                continue
            end = d(evs[i + 1]["event_date"]) if i + 1 < len(evs) else None
            out.append((seat, holder, d(e["event_date"]), end))
    return out


def days_held(ivs, user: str, y: int, m: int) -> int:
    ms, me = date(y, m, 1), date(y, m, dim(y, m)) + timedelta(days=1)
    n = 0
    for _, u, s, e in ivs:
        if u != user:
            continue
        e = e or me
        lo, hi = max(s, ms), min(e, me)
        if hi > lo:
            n += (hi - lo).days
    return n


LB_LAPSED = {"LB-022", "LB-026"}          # active Mar-Apr, silent from May
LB_ONE_OFF = {"LB-030": 5}                # silent in Aug only (index of month)
CO_LAPSED = {"CO-004", "CO-008", "CO-011", "CO-023", "CO-029", "CO-033"}
CO_NEVER = {"CO-036", "CO-038"}
CO_RESUME = {"CO-033"}                   # silent May-Jul, back in Aug (only the late report shows it)
CO_ONE_OFF = {"CO-040": 4}                # silent in Jul only
KE_NEVER = {"KE-009", "KE-021", "KE-027"}  # still not started in Aug
KE_JULY_IDLE = {"KE-036", "KE-037"}        # assigned in July, not started yet


def active_days(rng: random.Random, office: str, user: str, mi: int, held: int, base: dict) -> int:
    if office == "KE":
        if user in KE_NEVER or user in KE_JULY_IDLE:
            n = rng.choice([0, 0, 0, 1])
        elif mi <= 1:
            n = rng.choice([0] * 9 + [1])
        elif mi == 2:
            n = rng.choice([0, 0, 0, 1, 1, 2])
        elif mi == 3:  # June: first trained cohort starts at the very end
            n = rng.randint(3, 5) if int(user[-3:]) % 7 == 0 else rng.choice([0, 0, 1, 2])
        elif mi == 4:  # July: training in full swing
            n = rng.randint(5, 13)
        else:
            n = rng.randint(7, 16)
    else:
        n = max(0, int(rng.gauss(base[user], 2.5)))
        if office == "LB":
            if user in LB_LAPSED and mi >= 2:
                n = rng.choice([0, 0, 1])
            if user in LB_ONE_OFF and mi == LB_ONE_OFF[user]:
                n = rng.choice([0, 1])
        if office == "CO":
            if user in CO_LAPSED and mi >= 2:
                n = rng.choice([0, 0, 1])
            if user in CO_RESUME and mi == 5:
                n = rng.randint(6, 10)
            if user in CO_NEVER:
                n = rng.choice([0, 0, 1])
            if user in CO_ONE_OFF and mi == CO_ONE_OFF[user]:
                n = rng.choice([0, 1])
        n = max(n, 4) if n > 1 else n
    return min(n, held, 22)


def write_csv(path: Path, header: list[str], rows: list[list]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def generate(out: Path = RAW_DIR) -> Path:
    rng = random.Random(SEED)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    offs = build_events(rng)
    manifest: list[list] = []
    mlist = months()

    # events: one file per office, shuffled
    for code, o in offs.items():
        rows = [list(e.values()) for e in o.events]
        rng.shuffle(rows)
        name = f"assignment_events_{code}.csv"
        write_csv(out / "events" / name, list(o.events[0].keys()), rows)
        manifest.append([f"events/{name}", "events", code, "2026-03..2026-08", "2026-09-14"])

    # invoices: one file per office-month, plus the duplicated April file for Lebanon
    for code, (_, unit) in OFFICES.items():
        for mi, (y, m) in enumerate(mlist):
            qty = INVOICED[code][mi]
            amount = qty * unit
            period = f"{y}-{m:02d}"
            name = f"invoice_{code}_{period}.csv"
            row = [f"INV-{code}-{period}", code, period, SKU, "Microsoft 365 Copilot, per seat per month",
                   qty, f"{unit / 100:.2f}", f"{amount / 100:.2f}", "USD"]
            hdr = ["invoice_id", "office", "period", "sku", "description", "quantity", "unit_price", "amount", "currency"]
            write_csv(out / "invoices" / name, hdr, [row])
            nm, nd = (y, m + 1) if m < 12 else (y + 1, 1)
            manifest.append([f"invoices/{name}", "invoice", code, period, f"{nm}-{nd:02d}-03"])
            if code == "LB" and period == "2026-04":
                dup = f"invoice_LB_2026-04 (1).csv"
                shutil.copyfile(out / "invoices" / name, out / "invoices" / dup)
                manifest.append([f"invoices/{dup}", "invoice", code, period, "2026-05-06"])

    # usage: one file per office-month
    base = {u: rng.randint(7, 15) for c in OFFICES for u in [uid(c, i) for i in range(1, 60)]}
    for code, o in offs.items():
        ivs = intervals(o.events)
        users = sorted({u for _, u, _, _ in ivs})
        for mi, (y, m) in enumerate(mlist):
            rows = []
            for u in users:
                held = days_held(ivs, u, y, m)
                if held == 0:
                    continue
                if code == "CO" and u == "CO-015" and mi == 4:
                    continue  # missing row
                n = active_days(rng, code, u, mi, held, base)
                actions = n * rng.randint(6, 18)
                last = ""
                if n > 0:
                    last = date(y, m, min(dim(y, m), max(1, held if held < 10 else rng.randint(20, dim(y, m))))).isoformat()
                shown = u
                if code == "CO" and mi == 3:
                    shown = f"{u.lower()} "
                rows.append([code, f"{y}-{m:02d}", shown, n, actions, last])
                if code == "KE" and u == "KE-005" and mi == 4:
                    rows.append([code, f"{y}-{m:02d}", shown, n, actions, last])
            name = f"usage_{code}_{y}-{m:02d}.csv"
            write_csv(out / "usage" / name, ["office", "report_month", "user_id", "active_days", "copilot_actions", "last_activity_date"], rows)
            nm, nd = (y, m + 1) if m < 12 else (y + 1, 1)
            received = f"{nm}-{nd:02d}-0{rng.randint(5, 8)}"
            if code == "CO" and (y, m) == (2026, 8):
                received = "2026-10-06"
            manifest.append([f"usage/{name}", "usage", code, f"{y}-{m:02d}", received])

    write_csv(out / "manifest.csv", ["file_name", "kind", "office", "period", "received_date"], manifest)
    return out


if __name__ == "__main__":
    print(generate())
