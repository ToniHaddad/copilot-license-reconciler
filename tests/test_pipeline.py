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
RAW_TABLES = ["raw_invoice", "raw_events", "raw_usage", "raw_files"]


def rows(con, sql, *a):
    return con.execute(sql, list(a)).fetchall()


def independent_invoice_totals():
    """Parse the raw invoice files with Decimal, skipping byte-identical copies. Returns (total, per product)."""
    seen, total, per = set(), Decimal("0"), {}
    for p in sorted((RAW_DIR / "invoices").glob("*.csv")):
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        with p.open(newline="") as f:
            for r in csv.DictReader(f):
                total += Decimal(r["amount"])
                per[r["product"]] = per.get(r["product"], Decimal("0")) + Decimal(r["amount"])
    return total, per


# ---- 1. spend reconciles to the invoice to the cent ---------------------------------

def test_spend_reconciles_to_invoice_to_the_cent(wh):
    total, _ = independent_invoice_totals()
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
                   invoices=[("ZAH", "ASSIST", "2026-03", 1, 3000)],
                   events=[("2026-03-01", "ZAH", "ASSIST", "S1", "assign", "U1", ""),
                           ("2026-03-11", "ZAH", "ASSIST", "S1", "reassign", "U2", "U1")])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    got = rows(fresh, "SELECT holder, days, alloc_cents FROM seat_month_pieces ORDER BY holder")
    # 10 days of 31 at $30.00 = 967.74 -> 968 cents, the other holder gets the remaining 2032
    assert got == [("U1", 10, 968), ("U2", 21, 2032)]
    assert rows(fresh, "SELECT diff_cents, naive_overcount FROM reconciliation")[0] == (0, 1)


# ---- 2. a reassigned seat is never counted twice ------------------------------------

def test_seat_reassigned_inside_a_centre_is_one_seat(wh):
    got = rows(wh, """SELECT holder, days, alloc_cents FROM seat_month_pieces
                      WHERE seat_id = 'S-HQ-ASSIST-05' AND month = DATE '2026-04-01' ORDER BY holder""")
    assert got == [("HQ-005", 16, 1067), ("HQ-041", 14, 933)]
    assert sum(r[1] for r in got) == 30 and sum(r[2] for r in got) == 2000
    assert rows(wh, "SELECT naive_overcount FROM reconciliation WHERE centre='HQ' AND product='ASSIST' AND month=DATE '2026-04-01'")[0][0] == 1


def test_staff_who_move_between_centres_do_not_double_count(wh):
    # JBE-007 moves from Jbeil to Saida on 2026-05-12: the Jbeil seat goes to a replacement, Saida opens a seat
    got = rows(wh, """SELECT holder, days, alloc_cents FROM seat_month_pieces
                      WHERE seat_id = 'S-JBE-OFFICE-07' AND month = DATE '2026-05-01' ORDER BY holder""")
    assert got == [("JBE-007", 11, 444), ("JBE-031", 20, 806)]
    assert sum(r[2] for r in got) == 1250
    # Saida opens one new office-suite seat from May and the invoice bills it from May
    assert rows(wh, "SELECT known_seats, invoice_qty FROM reconciliation WHERE centre='SAI' AND product='OFFICE' AND month=DATE '2026-04-01'")[0] == (18, 18)
    assert rows(wh, "SELECT known_seats, invoice_qty FROM reconciliation WHERE centre='SAI' AND product='OFFICE' AND month=DATE '2026-05-01'")[0] == (19, 19)
    # the person shows in two centre reports in May, one row each
    assert rows(wh, "SELECT centre, count(*) FROM stg_usage WHERE user_id='JBE-007' AND product='OFFICE' AND month=DATE '2026-05-01' GROUP BY 1 ORDER BY 1") == [("JBE", 1), ("SAI", 1)]
    assert rows(wh, "SELECT count(*) FROM reconciliation WHERE known_seats > invoice_qty")[0][0] == 0


def test_a_seat_has_one_holder_on_any_day(wh):
    assert rows(wh, """SELECT count(*) FROM seat_intervals a JOIN seat_intervals b
                       ON a.seat_id = b.seat_id AND a.start_date < b.start_date AND b.start_date < a.end_date""")[0][0] == 0
    assert rows(wh, "SELECT count(*) FROM (SELECT seat_id, day FROM seat_day GROUP BY 1,2 HAVING count(*) > 1)")[0][0] == 0


def test_history_is_kept_as_dated_intervals(wh):
    got = rows(wh, "SELECT user_id, start_date, end_date FROM seat_intervals WHERE seat_id='S-HQ-ASSIST-05' ORDER BY start_date")
    assert [g[0] for g in got] == ["HQ-005", "HQ-041"]
    assert str(got[0][2]) == "2026-04-17" == str(got[1][1])


# ---- 2b. product is a dimension: a seat of one product is never a seat of another ---

def test_seats_and_money_never_cross_products(wh):
    assert rows(wh, "SELECT count(*) FROM (SELECT seat_id FROM seats GROUP BY 1 HAVING count(DISTINCT product) > 1)")[0][0] == 0
    # per-product invoiced money matches an independent parse of the files
    _, per = independent_invoice_totals()
    got = dict(rows(wh, "SELECT product, sum(invoice_cents) FROM reconciliation GROUP BY 1"))
    assert got == {k: int(v * 100) for k, v in per.items()}
    # a person with seats of four products keeps four separate seat-months
    two = rows(wh, """SELECT product, count(DISTINCT seat_id), sum(alloc_cents) FROM seat_month_pieces
                      WHERE holder = 'HQ-001' AND month = DATE '2026-07-01' GROUP BY 1 ORDER BY 1""")
    assert two == [("ASSIST", 1, 2000), ("FLOW", 1, 2400), ("OFFICE", 1, 1250), ("SURVEY", 1, 1800)]
    # known seats never exceed what that product's invoice bills
    assert rows(wh, "SELECT count(*) FROM reconciliation WHERE known_seats > invoice_qty")[0][0] == 0


def test_same_person_two_products_are_classified_separately(tmp_path, fresh):
    raw = make_raw(tmp_path / "raw",
                   invoices=[("ZAH", "OFFICE", "2026-03", 1, 1250), ("ZAH", "ASSIST", "2026-03", 1, 2000)],
                   events=[("2026-03-01", "ZAH", "OFFICE", "S-O", "assign", "U1", ""),
                           ("2026-03-01", "ZAH", "ASSIST", "S-A", "assign", "U1", "")],
                   usage=[("ZAH", "2026-03", "OFFICE", "U1", 15), ("ZAH", "2026-03", "ASSIST", "U1", 0)])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    assert dict(rows(fresh, "SELECT product, class FROM seat_month_class")) == {"OFFICE": "active", "ASSIST": "confirmed_inactive"}
    # an AI seat is not reallocated to cover a missing office-suite seat: pools are per product
    assert dict(rows(fresh, "SELECT product, seats_billed FROM seat_pool")) == {"OFFICE": 1, "ASSIST": 1}


def test_forecast_only_touches_the_decision_product(wh):
    assert {r[0] for r in rows(wh, "SELECT DISTINCT product FROM forecast_pool")} == {"ASSIST"}
    assert rows(wh, "SELECT value FROM forecast_assumptions WHERE key = 'product'") == [("ASSIST",)]


# ---- 3. a repeated import changes nothing -------------------------------------------

def test_repeated_import_gives_identical_totals():
    con = pipeline.connect(":memory:")
    first = pipeline.build_warehouse(con, RAW_DIR, DEFAULT_AS_OF)
    a = pipeline.table_fingerprint(con, TABLES + RAW_TABLES)
    second = pipeline.build_warehouse(con, RAW_DIR, DEFAULT_AS_OF)
    b = pipeline.table_fingerprint(con, TABLES + RAW_TABLES)
    assert first["loaded"] > 0 and second["loaded"] == 0 and second["duplicates"] == 0
    assert a == b
    con.close()


def test_duplicate_invoice_file_is_not_double_counted(tmp_path):
    clean = tmp_path / "clean"
    shutil.copytree(RAW_DIR, clean)
    (clean / "invoices" / "invoice_ASSIST_2026-04 (1).csv").unlink()
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
    p = raw / "invoices" / "invoice_FLOW_2026-03.csv"
    assert "96.00" in p.read_text()
    p.write_bytes(p.read_bytes().replace(b"96.00", b"97.00"))
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
                      WHERE centre = 'TRI' AND month = DATE '2026-08-01' AND user_id IS NOT NULL GROUP BY 1, 2""")
    assert got == [("unknown", "usage report not received", 30)]


def test_inactive_always_rests_on_a_real_usage_row(wh):
    assert rows(wh, """SELECT count(*) FROM seat_month_class
                       WHERE class = 'confirmed_inactive' AND (usage_file IS NULL OR active_days IS NULL)""")[0][0] == 0
    got = rows(wh, "SELECT class, reason FROM seat_month_class WHERE user_id='ZAH-004' AND product='ASSIST' AND month=DATE '2026-07-01'")
    assert got == [("unknown", "user missing from the report")]


def test_no_usage_files_at_all_means_all_unknown(tmp_path, fresh):
    raw = make_raw(tmp_path / "raw",
                   invoices=[("ZAH", "ASSIST", "2026-03", 2, 2000)],
                   events=[("2026-03-01", "ZAH", "ASSIST", "S1", "assign", "U1", ""), ("2026-03-01", "ZAH", "ASSIST", "S2", "assign", "U2", "")])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    assert rows(fresh, "SELECT DISTINCT class FROM seat_month_class") == [("unknown",)]


def test_zero_active_days_in_a_received_report_is_inactive(tmp_path, fresh):
    raw = make_raw(tmp_path / "raw",
                   invoices=[("ZAH", "ASSIST", "2026-03", 2, 2000)],
                   events=[("2026-03-01", "ZAH", "ASSIST", "S1", "assign", "U1", ""), ("2026-03-01", "ZAH", "ASSIST", "S2", "assign", "U2", "")],
                   usage=[("ZAH", "2026-03", "ASSIST", "U1", 0), ("ZAH", "2026-03", "ASSIST", "U2", 9)])
    pipeline.build_warehouse(fresh, raw, "2026-04-30")
    assert dict(rows(fresh, "SELECT user_id, class FROM seat_month_class")) == {"U1": "confirmed_inactive", "U2": "active"}


def test_late_report_arrival_changes_the_answer():
    early = build_at(DEFAULT_AS_OF)
    late = build_at("2026-10-10")
    c = "SELECT count(*) FROM holder_status WHERE centre='TRI' AND product='ASSIST' AND verdict='candidate'"
    assert rows(early, c)[0][0] == 2 and rows(late, c)[0][0] == 1
    # the person who came back in August is a candidate only while that month is unknown
    q = "SELECT verdict FROM holder_status WHERE user_id = 'TRI-002' AND product = 'ASSIST'"
    assert rows(early, q) == [("candidate",)] and rows(late, q) == [("needs_evidence",)]
    assert rows(late, "SELECT count(*) FROM seat_month_class WHERE month=DATE '2026-08-01' AND centre='TRI' AND class='unknown'")[0][0] == 0


# ---- the interpretation: Saida, candidates and the forecast -------------------------

def test_saida_late_onboarding_is_held_back_not_reclaimed(wh):
    assert str(rows(wh, "SELECT start_month FROM centre_onboarding WHERE centre='SAI' AND product='ASSIST'")[0][0]) == "2026-07-01"
    # the same centre's other products started on day one: it is the AI add-on, not the centre
    assert str(rows(wh, "SELECT start_month FROM centre_onboarding WHERE centre='SAI' AND product='OFFICE'")[0][0]) == "2026-03-01"
    assert rows(wh, "SELECT count(*) FROM holder_status WHERE centre='SAI' AND verdict='candidate'")[0][0] == 0
    assert rows(wh, "SELECT count(*) FROM holder_status WHERE centre='SAI' AND reason='centre_still_ramping'")[0][0] == 2
    assert rows(wh, "SELECT median_lag_months FROM centre_lag WHERE centre='SAI' AND product='ASSIST'")[0][0] == 4
    s = rows(wh, "SELECT active_share_reported, active_share_since_start FROM centre_cost WHERE centre='SAI' AND product='ASSIST'")[0]
    assert s[0] < 0.4 and s[1] > 0.6
    assert rows(wh, "SELECT active_share_reported FROM centre_cost WHERE centre='SAI' AND product='OFFICE'")[0][0] == 1.0
    assert rows(wh, "SELECT count(*) FROM seat_month_class WHERE centre='SAI' AND product='ASSIST' AND starts_later")[0][0] > 30


def test_candidates_versus_evidence_needed(wh):
    got = dict(rows(wh, "SELECT centre, candidates FROM forecast_pool"))
    assert got == {"ZAH": 0, "JBE": 2, "SAI": 0, "TRI": 2, "HQ": 4}
    reasons = dict(rows(wh, "SELECT reason, count(*) FROM holder_status WHERE verdict='needs_evidence' AND product='ASSIST' GROUP BY 1"))
    assert reasons == {"recently_assigned": 2, "usage_missing": 1, "single_month_inactive": 2, "centre_still_ramping": 2}
    # other products have their own candidates, listed but outside the decision
    assert dict(rows(wh, "SELECT product, sum(candidates) FROM seat_pool GROUP BY 1")) == {"ASSIST": 8, "FLOW": 1, "OFFICE": 0, "SURVEY": 2}
    assert rows(wh, "SELECT count(*) FROM (SELECT seat_id FROM holder_status GROUP BY 1 HAVING count(*) > 1)")[0][0] == 0


def test_forecast_two_options(wh):
    a = rows(wh, "SELECT bought, reallocated, added_cents, spend_cents FROM forecast_options WHERE option='buy' AND centre='ALL'")[0]
    b = rows(wh, "SELECT bought, reallocated, added_cents, spend_cents FROM forecast_options WHERE option='reallocate' AND centre='ALL'")[0]
    assert a[0] == 19 and a[1] == 0
    assert b[0] + b[1] == 19 and b[1] == 12
    assert b[2] < a[2] and a[3] - b[3] == a[2] - b[2]
    assert a[2] == 19 * 2000 * 3
    # seats come from centres that did not ask (head office, Jbeil) as well as from the askers' own pools
    assert rows(wh, "SELECT sum(from_other_centres) FROM realloc")[0][0] == 10
    keys = {r[0] for r in rows(wh, "SELECT key FROM forecast_assumptions")}
    assert {"product", "activation_rate", "months", "prices", "reallocation_date"} <= keys


# ---- the report ---------------------------------------------------------------------

def test_report_is_self_contained_and_every_recommendation_has_sources(wh):
    html = report.render(wh, DEFAULT_AS_OF)
    assert "http://" not in html and "https://" not in html
    assert "<script src" not in html and "<link" not in html and "@import" not in html
    assert html.count("<svg") >= 4
    assert html.count("class='card rec'") >= 5
    assert html.count("Show the source rows") >= 6
    assert "events/assignment_events_SAI.csv:" in html and "usage/usage_SAI_2026-07.csv:" in html
    assert "Where it fails" in html and "prefers-color-scheme" in html
    for old in ("North" + "bridge", "Ken" + "ya", "Colom" + "bia", "Copi" + "lot"):
        assert old not in html
