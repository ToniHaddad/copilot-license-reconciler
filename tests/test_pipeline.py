import csv
import hashlib
import shutil
from decimal import Decimal

import pytest

from reconciler import pipeline, report
from reconciler.config import DEFAULT_AS_OF, RAW_DIR
from reconciler.generate import generate

from .conftest import build_at, make_raw

TABLES = ["stg_invoice", "stg_events", "stg_usage", "seat_intervals", "seat_month_pieces",
          "reconciliation", "seat_month_class", "holder_status", "forecast_options", "evidence"]


def rows(con, sql, *a):
    return con.execute(sql, list(a)).fetchall()


# ---- 1. spend reconciles to the invoice to the cent ---------------------------------

def test_spend_reconciles_to_invoice_to_the_cent(wh):
    # independent total: read the raw invoice files with Decimal, skipping byte-identical copies
    seen, total = set(), Decimal("0")
    for p in sorted((RAW_DIR / "invoices").glob("*.csv")):
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        with p.open(newline="") as f:
            for r in csv.DictReader(f):
                total += Decimal(r["amount"])
    assert rows(wh, "SELECT sum(invoice_cents) FROM reconciliation")[0][0] == int(total * 100)
    assert rows(wh, "SELECT sum(reconciled_cents) FROM reconciliation")[0][0] == int(total * 100)
    assert rows(wh, "SELECT count(*) FROM reconciliation WHERE diff_cents <> 0")[0][0] == 0
    assert rows(wh, "SELECT count(*) FROM reconciliation WHERE status <> 'ok'")[0][0] == 0


def test_every_seat_month_adds_up_to_one_seat_price(wh):
    bad = rows(wh, """SELECT seat_id, month, sum(alloc_cents), max(unit_cents) FROM seat_month_pieces
                      GROUP BY seat_id, month HAVING sum(alloc_cents) <> max(unit_cents)""")
    assert bad == []
    assert rows(wh, "SELECT count(*) FROM seat_month_pieces WHERE alloc_cents < 0")[0][0] == 0


def test_proration_is_exact_on_a_hand_built_case(tmp_path, fresh):
    raw = make_raw(tmp_path / "raw",
                   invoices=[("LB", "2026-03", 1, 3000)],
                   events=[("2026-03-01", "LB", "S1", "assign", "U1", ""),
                           ("2026-03-11", "LB", "S1", "reassign", "U2", "U1")])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    got = rows(fresh, "SELECT holder, days, alloc_cents FROM seat_month_pieces ORDER BY holder")
    # 10 days of 31 at $30.00 = 967.74 -> 968 cents, the other holder gets the remaining 2032
    assert got == [("U1", 10, 968), ("U2", 21, 2032)]
    assert rows(fresh, "SELECT diff_cents, naive_overcount FROM reconciliation")[0] == (0, 1)


# ---- 2. a reassigned seat is never counted twice ------------------------------------

def test_reassigned_seat_is_one_seat_not_two(wh):
    got = rows(wh, """SELECT holder, days, alloc_cents FROM seat_month_pieces
                      WHERE seat_id = 'S-CO-17' AND month = DATE '2026-05-01' ORDER BY holder""")
    assert got == [("CO-017", 11, 979), ("CO-043", 20, 1781)]
    assert sum(r[1] for r in got) == 31
    assert sum(r[2] for r in got) == 2760
    # the naive count (distinct users) is one more than the seats held, in exactly that month
    assert rows(wh, "SELECT naive_overcount FROM reconciliation WHERE office='CO' AND month=DATE '2026-05-01'")[0][0] == 1
    # seats never exceed what the invoice bills
    assert rows(wh, "SELECT count(*) FROM reconciliation WHERE known_seats > invoice_qty")[0][0] == 0


def test_a_seat_has_one_holder_on_any_day(wh):
    assert rows(wh, """SELECT count(*) FROM seat_intervals a JOIN seat_intervals b
                       ON a.seat_id = b.seat_id AND a.start_date < b.start_date AND b.start_date < a.end_date""")[0][0] == 0
    assert rows(wh, "SELECT count(*) FROM (SELECT seat_id, day FROM seat_day GROUP BY 1,2 HAVING count(*) > 1)")[0][0] == 0


def test_history_is_kept_as_dated_intervals(wh):
    got = rows(wh, "SELECT user_id, start_date, end_date FROM seat_intervals WHERE seat_id='S-LB-12' ORDER BY start_date")
    assert [g[0] for g in got] == ["LB-012", "LB-037"]
    assert str(got[0][2]) == "2026-04-17" == str(got[1][1])


# ---- 3. a repeated import changes nothing -------------------------------------------

def test_repeated_import_gives_identical_totals():
    con = pipeline.connect(":memory:")
    first = pipeline.build_warehouse(con, RAW_DIR, DEFAULT_AS_OF)
    a = pipeline.table_fingerprint(con, TABLES + ["raw_invoice", "raw_events", "raw_usage", "raw_files"])
    second = pipeline.build_warehouse(con, RAW_DIR, DEFAULT_AS_OF)
    b = pipeline.table_fingerprint(con, TABLES + ["raw_invoice", "raw_events", "raw_usage", "raw_files"])
    assert first["loaded"] > 0 and second["loaded"] == 0 and second["duplicates"] == 0
    assert a == b
    con.close()


def test_duplicate_invoice_file_is_not_double_counted(tmp_path):
    clean = tmp_path / "clean"
    shutil.copytree(RAW_DIR, clean)
    (clean / "invoices" / "invoice_LB_2026-04 (1).csv").unlink()
    lines = [l for l in (clean / "manifest.csv").read_text().splitlines() if "(1)" not in l]
    (clean / "manifest.csv").write_text("\n".join(lines) + "\n")
    without = build_at(DEFAULT_AS_OF, clean)
    withdup = build_at(DEFAULT_AS_OF)
    q = "SELECT sum(amount_cents), count(*) FROM stg_invoice"
    assert rows(without, q) == rows(withdup, q)
    assert rows(withdup, "SELECT count(*) FROM raw_files WHERE duplicate_of IS NOT NULL")[0][0] == 1
    assert rows(withdup, "SELECT count(*) FROM raw_invoice WHERE file_name LIKE '%(1)%'")[0][0] == 0


def test_a_file_changed_after_import_is_refused(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(RAW_DIR, raw)
    con = pipeline.connect(":memory:")
    pipeline.load_raw(con, raw)
    p = raw / "invoices" / "invoice_KE_2026-03.csv"
    p.write_text(p.read_text().replace("900.00", "901.00"))
    with pytest.raises(ValueError):
        pipeline.load_raw(con, raw)


def test_generator_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a)
    generate(b)
    names = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    assert names == sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    assert all((a / n).read_bytes() == (b / n).read_bytes() for n in names)
    # and the committed fixtures are what the generator writes
    assert all((a / n).read_bytes() == (RAW_DIR / n).read_bytes() for n in names)


# ---- 4. missing usage never becomes inactive ----------------------------------------

def test_missing_report_is_unknown_never_inactive(wh):
    got = rows(wh, """SELECT class, reason, count(*) FROM seat_month_class
                      WHERE office = 'CO' AND month = DATE '2026-08-01' AND user_id IS NOT NULL GROUP BY 1, 2""")
    assert got == [("unknown", "usage report not received", 41)]


def test_inactive_always_rests_on_a_real_usage_row(wh):
    assert rows(wh, """SELECT count(*) FROM seat_month_class
                       WHERE class = 'confirmed_inactive' AND (usage_file IS NULL OR active_days IS NULL)""")[0][0] == 0
    # a user absent from a received report is unknown too
    got = rows(wh, "SELECT class, reason FROM seat_month_class WHERE user_id='CO-015' AND month=DATE '2026-07-01'")
    assert got == [("unknown", "user missing from the report")]


def test_no_usage_files_at_all_means_all_unknown(tmp_path, fresh):
    raw = make_raw(tmp_path / "raw",
                   invoices=[("LB", "2026-03", 2, 3000)],
                   events=[("2026-03-01", "LB", "S1", "assign", "U1", ""), ("2026-03-01", "LB", "S2", "assign", "U2", "")])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    assert rows(fresh, "SELECT DISTINCT class FROM seat_month_class") == [("unknown",)]


def test_zero_active_days_in_a_received_report_is_inactive(tmp_path, fresh):
    raw = make_raw(tmp_path / "raw",
                   invoices=[("LB", "2026-03", 2, 3000)],
                   events=[("2026-03-01", "LB", "S1", "assign", "U1", ""), ("2026-03-01", "LB", "S2", "assign", "U2", "")],
                   usage=[("LB", "2026-03", "U1", 0), ("LB", "2026-03", "U2", 9)])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    assert dict(rows(fresh, "SELECT user_id, class FROM seat_month_class")) == {"U1": "confirmed_inactive", "U2": "active"}


def test_late_report_arrival_changes_the_answer():
    early = build_at(DEFAULT_AS_OF)
    late = build_at("2026-10-10")
    c = "SELECT count(*) FROM holder_status WHERE office='CO' AND verdict='candidate'"
    assert rows(early, c)[0][0] == 8 and rows(late, c)[0][0] == 7
    # the seat that came back in August is a candidate only while that month is unknown
    q = "SELECT verdict FROM holder_status WHERE user_id = 'CO-033'"
    assert rows(early, q) == [("candidate",)] and rows(late, q) == [("needs_evidence",)]
    assert rows(late, "SELECT count(*) FROM seat_month_class WHERE month=DATE '2026-08-01' AND office='CO' AND class='unknown'")[0][0] == 0


# ---- the interpretation: Kenya, candidates and the forecast -------------------------

def test_kenya_late_onboarding_is_held_back_not_reclaimed(wh):
    assert str(rows(wh, "SELECT start_month FROM office_onboarding WHERE office='KE'")[0][0]) == "2026-07-01"
    assert rows(wh, "SELECT count(*) FROM holder_status WHERE office='KE' AND verdict='candidate'")[0][0] == 0
    assert rows(wh, "SELECT count(*) FROM holder_status WHERE office='KE' AND reason='office_still_ramping'")[0][0] == 3
    assert rows(wh, "SELECT median_lag_months FROM office_lag WHERE office='KE'")[0][0] == 4
    ke = rows(wh, "SELECT active_share_reported, active_share_since_start FROM office_cost WHERE office='KE'")[0]
    assert ke[0] < 0.4 < 0.8 < ke[1]
    # inactive Kenya months before July are explained by users who started later
    assert rows(wh, "SELECT count(*) FROM seat_month_class WHERE office='KE' AND starts_later")[0][0] > 60


def test_candidates_versus_evidence_needed(wh):
    got = dict(rows(wh, "SELECT office, candidates FROM office_pool"))
    assert got == {"LB": 2, "KE": 0, "CO": 8}
    reasons = dict(rows(wh, "SELECT reason, count(*) FROM holder_status WHERE verdict='needs_evidence' GROUP BY 1"))
    assert reasons["recently_assigned"] == 2 and reasons["usage_missing"] == 1 and reasons["single_month_inactive"] == 3
    # no seat is in both lists
    assert rows(wh, "SELECT count(*) FROM (SELECT seat_id FROM holder_status GROUP BY 1 HAVING count(*) > 1)")[0][0] == 0


def test_forecast_two_options(wh):
    a = rows(wh, "SELECT bought, reallocated, added_cents, spend_cents FROM forecast_options WHERE option='buy' AND office='ALL'")[0]
    b = rows(wh, "SELECT bought, reallocated, added_cents, spend_cents FROM forecast_options WHERE option='reallocate' AND office='ALL'")[0]
    assert a[0] == 24 and a[1] == 0
    assert b[0] + b[1] == 24 and b[1] == 18
    assert b[2] < a[2] and a[3] - b[3] == a[2] - b[2]
    assert a[2] == (8 * 3000 + 10 * 3000 + 6 * 2760) * 3
    keys = {r[0] for r in rows(wh, "SELECT key FROM forecast_assumptions")}
    assert {"activation_rate", "months", "prices", "reallocation_date"} <= keys


# ---- the report ---------------------------------------------------------------------

def test_report_is_self_contained_and_every_recommendation_has_sources(wh):
    html = report.render(wh, DEFAULT_AS_OF)
    assert "http://" not in html and "https://" not in html
    assert "<script src" not in html and "<link" not in html and "@import" not in html
    assert html.count("<svg") >= 4
    assert html.count("class='card rec'") >= 4
    assert html.count("Show the source rows") >= 5
    assert "events/assignment_events_KE.csv:" in html and "usage/usage_KE_2026-07.csv:" in html
    assert "Where it fails" in html and "prefers-color-scheme" in html
