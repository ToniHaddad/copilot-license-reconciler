"""Render the single self-contained HTML report from the warehouse. No external assets."""
from __future__ import annotations

from html import escape

from .config import (CENTRES, FORECAST_LABEL, FORECAST_MONTHS, FORECAST_PRODUCT, PRODUCTS, PRODUCT_KIND,
                     PRODUCT_NAME)
from .report_style import CSS, JS

CLASS_LABEL = {
    "active": "Active",
    "confirmed_inactive": "Confirmed inactive",
    "unknown": "Unknown (no usage data)",
    "unassigned": "Paid, nobody assigned",
}
REASON_TEXT = {
    "no real use in the last two reported months": "No real use in the last two reported months",
    "usage_missing": "A month in the window has no usage data for this user",
    "recently_assigned": "Held the seat less than 60 days: too early to judge",
    "centre_still_ramping": "Centre is still ramping up on this product: low use is expected",
    "single_month_inactive": "Inactive in one of the last two months only",
}
FP = FORECAST_PRODUCT
FP_NAME = PRODUCT_NAME[FP]
FP_KIND = PRODUCT_KIND[FP]
MARKERS = {"ZAH": "diamond", "JBE": "circle", "SAI": "square", "TRI": "tri", "HQ": "cross"}


def q(con, sql, args=None):
    cur = con.execute(sql, args or [])
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def money(c, cents=True):
    if c is None:
        return "n/a"
    v = c / 100
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def mlabel(d):
    return d.strftime("%b")


def pct(x, nd=0):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def e(s):
    return escape(str(s))


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ----------------------------------------------------------------------------- charts

def marker_svg(kind, cx, cy, cls):
    if kind == "circle":
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" class="dot {cls}"/>'
    if kind == "square":
        return f'<rect x="{cx - 3.6:.1f}" y="{cy - 3.6:.1f}" width="7.2" height="7.2" class="dot {cls}"/>'
    if kind == "diamond":
        return f'<path d="M{cx:.1f},{cy - 4.6:.1f} L{cx + 4.2:.1f},{cy:.1f} L{cx:.1f},{cy + 4.6:.1f} L{cx - 4.2:.1f},{cy:.1f}Z" class="dot {cls}"/>'
    if kind == "cross":
        return (f'<path d="M{cx - 3.6:.1f},{cy - 3.6:.1f} L{cx + 3.6:.1f},{cy + 3.6:.1f} M{cx + 3.6:.1f},{cy - 3.6:.1f} L{cx - 3.6:.1f},{cy + 3.6:.1f}" '
                f'class="xmark s-{cls[2:]}"/>')
    return f'<path d="M{cx:.1f},{cy - 4.4:.1f} L{cx + 4:.1f},{cy + 3:.1f} L{cx - 4:.1f},{cy + 3:.1f}Z" class="dot {cls}"/>'


def svg_active_share(con):
    data = q(con, "SELECT centre, month, active_share, report_received FROM centre_month_usage WHERE product = ? ORDER BY centre, month", [FP])
    months = sorted({r["month"] for r in data})
    W, H, L, R, T, B = 480, 300, 40, 84, 18, 34
    pw, ph = W - L - R, H - T - B
    x = lambda i: L + pw * i / (len(months) - 1)
    y = lambda v: T + ph * (1 - v)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t1 d1" class="chart">',
           f'<title id="t1">Share of {e(FP_NAME)} seats that are active, by month and centre</title>',
           '<desc id="d1">Four centres sit near 80 to 100 percent. Saida is near zero until June and jumps in July. The Tripoli August report was not received.</desc>']
    for g in (0, .25, .5, .75, 1):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(g):.1f}" y2="{y(g):.1f}" class="grid"/>')
        out.append(f'<text x="{L - 6}" y="{y(g) + 4:.1f}" text-anchor="end" class="tick">{int(g * 100)}%</text>')
    for i, m in enumerate(months):
        out.append(f'<text x="{x(i):.1f}" y="{H - 12}" text-anchor="middle" class="tick">{mlabel(m)}</text>')
    ends = []
    for code in ("ZAH", "JBE", "TRI", "HQ", "SAI"):
        pts = [(i, r["active_share"]) for i, m in enumerate(months)
               for r in data if r["centre"] == code and r["month"] == m and r["active_share"] is not None]
        path = " ".join(f"{'M' if k == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for k, (i, v) in enumerate(pts))
        cls = f"line s-{code}" + (" thick" if code == "SAI" else "")
        out.append(f'<path d="{path}" class="{cls}"/>')
        for i, v in pts:
            out.append(marker_svg(MARKERS[code], x(i), y(v), f"f-{code}"))
        if pts:
            i, v = pts[-1]
            ends.append([code, x(i) + 9, y(v) + 4])
    # keep the direct labels apart
    ends.sort(key=lambda t: t[2])
    for k in range(1, len(ends)):
        if ends[k][2] - ends[k - 1][2] < 14:
            ends[k][2] = ends[k - 1][2] + 14
    for code, lx, ly in ends:
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="lbl l-{code}">{CENTRES[code]}</text>')
    for r in data:
        if not r["report_received"]:
            i = months.index(r["month"])
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(0):.1f}" r="4" class="hollow"/>')
            out.append(f'<text x="{x(i):.1f}" y="{y(0) - 9:.1f}" text-anchor="middle" class="note">{CENTRES[r["centre"]]}: no report yet</text>')
            break
    out.append(f'<text x="{x(0) + 4:.1f}" y="{y(0) - 8:.1f}" class="note">12 seats assigned in one day</text>')
    out.append("</svg>")
    return "".join(out)


def svg_cost_bars(con):
    rows = q(con, "SELECT * FROM centre_cost WHERE product = ? ORDER BY centre", [FP])
    W = 480
    L, R = 92, 56
    mx = max(max(r["cents_per_active_month"] or 0, r["cents_per_active_since_start"] or 0) for r in rows)
    pw = W - L - R
    H = 14 + len(rows) * 54
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t2 d2" class="chart">',
           f'<title id="t2">Cost per active {e(FP_NAME)} user per month, by centre</title>',
           '<desc id="d2">Two bars per centre: all months with a usage report, and only the months since the centre started using the product.</desc>']
    y = 14
    for r in rows:
        out.append(f'<text x="{L - 8}" y="{y + 22}" text-anchor="end" class="lbl l-{r["centre"]}">{CENTRES[r["centre"]]}</text>')
        for key, cls, lab in (("cents_per_active_month", "bar b-all", "all reported months"),
                              ("cents_per_active_since_start", "bar b-since", "since usage started")):
            v = r[key] or 0
            w = pw * v / mx
            out.append(f'<rect x="{L}" y="{y}" width="{w:.1f}" height="17" rx="2" class="{cls}"><title>{lab}</title></rect>')
            out.append(f'<text x="{L + w + 6:.1f}" y="{y + 13}" class="val">{money(v)}</text>')
            y += 21
        y += 12
    out.append("</svg>")
    return "".join(out)


def svg_class_bars(con):
    rows = q(con, "SELECT product, class, sum(cents) AS cents FROM spend_by_class GROUP BY product, class")
    order = ["active", "confirmed_inactive", "unknown", "unassigned"]
    W, L, R = 480, 100, 16
    pw = W - L - R
    H = 20 + len(PRODUCTS) * 36 + 30
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t3 d3" class="chart">',
           '<title id="t3">Where the six months of spend went, by product</title>',
           '<desc id="d3">Each bar splits the invoiced spend of one product into active, confirmed inactive, unknown because usage data is missing, and paid but unassigned.</desc>']
    y = 10
    for code in PRODUCTS:
        by = {r["class"]: r["cents"] for r in rows if r["product"] == code}
        tot = sum(by.values())
        out.append(f'<text x="{L - 8}" y="{y + 17}" text-anchor="end" class="lbl">{e(PRODUCT_NAME[code])}</text>')
        xx = L
        for c in order:
            v = by.get(c, 0)
            if not v:
                continue
            w = pw * v / tot
            out.append(f'<rect x="{xx:.1f}" y="{y}" width="{w:.1f}" height="24" class="seg c-{c}"><title>{CLASS_LABEL[c]}: {money(v)}</title></rect>')
            if w > 34:
                out.append(f'<text x="{xx + w / 2:.1f}" y="{y + 16}" text-anchor="middle" class="seglabel">{v / tot * 100:.0f}%</text>')
            xx += w
        y += 36
    lx = L
    for c in order:
        lab = {"active": "Active", "confirmed_inactive": "Confirmed inactive", "unknown": "Unknown", "unassigned": "Unassigned"}[c]
        out.append(f'<rect x="{lx}" y="{H - 24}" width="11" height="11" class="seg c-{c}"/>')
        out.append(f'<text x="{lx + 16}" y="{H - 14}" class="tick">{lab}</text>')
        lx += 16 + 7.4 * len(lab) + 14
    out.append("</svg>")
    return "".join(out)


def svg_forecast(con):
    rows = {r["option"]: r for r in q(con, "SELECT * FROM forecast_options WHERE centre = 'ALL'")}
    a, b = rows["buy"], rows["reallocate"]
    W, H, L, R = 480, 120, 150, 70
    pw = W - L - R
    mx = max(a["added_cents"], b["added_cents"], 1)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t4 d4" class="chart">',
           '<title id="t4">New spend next quarter under each option</title>',
           f'<desc id="d4">Buying costs {money(a["added_cents"])} of new spend and reallocating costs {money(b["added_cents"])}.</desc>']
    for i, (lab, r, cls) in enumerate((("Option A: buy", a, "b-buy"), ("Option B: reallocate", b, "b-realloc"))):
        yy = 14 + i * 44
        w = pw * r["added_cents"] / mx
        out.append(f'<text x="{L - 8}" y="{yy + 18}" text-anchor="end" class="lbl">{lab}</text>')
        out.append(f'<rect x="{L}" y="{yy}" width="{max(w, 1):.1f}" height="28" rx="2" class="bar {cls}"/>')
        out.append(f'<text x="{L + w + 6:.1f}" y="{yy + 19}" class="val">{money(r["added_cents"], False)}</text>')
    out.append("</svg>")
    return "".join(out)


# ----------------------------------------------------------------------------- evidence

def evidence_html(con, subjects, like=False):
    if like:
        rows = q(con, "SELECT * FROM evidence WHERE subject LIKE ? ORDER BY subject, kind, file_name, line_no", [subjects])
    else:
        if not subjects:
            return "<p class='muted'>No rows.</p>"
        ph = ", ".join("?" * len(subjects))
        rows = q(con, f"SELECT * FROM evidence WHERE subject IN ({ph}) ORDER BY subject, kind, file_name, line_no", list(subjects))
    if not rows:
        return "<p class='muted'>No rows.</p>"
    body = []
    for r in rows:
        loc = f"{e(r['file_name'])}:{r['line_no']}" if r["line_no"] else e(r["file_name"])
        body.append(f"<tr><td class='src'>{loc}</td><td><code>{e(r['raw_line'])}</code></td><td>{e(r['note'])}</td></tr>")
    return ("<div class='tw ev'><table><thead><tr><th>Source (file:line)</th><th>The line</th><th>What it shows</th></tr></thead>"
            "<tbody>" + "".join(body) + "</tbody></table></div>")


def details(summary, inner, cls=""):
    return f"<details class='{cls}'><summary>{summary}</summary>{inner}</details>"


def seat_subjects(con, where):
    return [r["subject"] for r in q(con, f"SELECT DISTINCT 'SEAT:' || seat_id AS subject FROM holder_status WHERE {where} ORDER BY 1")]


# ----------------------------------------------------------------------------- recommendation

def recommendations(con, as_of):
    pools = q(con, "SELECT * FROM forecast_pool ORDER BY centre")
    realloc = {r["centre"]: r for r in q(con, "SELECT * FROM realloc")}
    fc = {(r["option"], r["centre"]): r for r in q(con, "SELECT * FROM forecast_options")}
    cost = {(r["centre"], r["product"]): r for r in q(con, "SELECT * FROM centre_cost")}
    lag = {(r["centre"], r["product"]): r for r in q(con, "SELECT * FROM centre_lag")}
    ob = {(r["centre"], r["product"]): r for r in q(con, "SELECT * FROM centre_onboarding")}
    bounds = q(con, "SELECT * FROM bounds")[0]
    all_billed = q(con, "SELECT sum(seats_billed) AS n FROM seat_pool")[0]["n"]
    billed = sum(p["seats_billed"] for p in pools)
    free_logged = sum(p["free_logged"] for p in pools)
    free_unlogged = sum(p["free_unlogged"] for p in pools)
    free = free_logged + free_unlogged
    cand = sum(p["candidates"] for p in pools)
    need_all = q(con, "SELECT sum(needs_evidence) AS n FROM seat_pool")[0]["n"]
    req = sum(r["req"] for r in realloc.values())
    to_buy = sum(r["to_buy"] for r in realloc.values())
    moved = sum(r["from_own_pool"] + r["from_other_centres"] for r in realloc.values())
    A, B = fc[("buy", "ALL")], fc[("reallocate", "ALL")]
    save = A["added_cents"] - B["added_cents"]
    recs = []

    buy_split = ", ".join(f"{CENTRES[c]} {r['to_buy']}" for c, r in sorted(realloc.items()) if r["to_buy"])
    cand_split = ", ".join(f"{CENTRES[p['centre']]} {p['candidates']}" for p in pools if p["candidates"])
    ask_split = ", ".join(f"{CENTRES[c]} {r['req']}" for c, r in sorted(realloc.items()))
    recs.append({
        "title": f"Move {moved} {FP_NAME} seats first, then buy only the {to_buy} still missing",
        "body": (f"The Organization is billed for {billed} {e(FP_NAME)} ({e(FP_KIND)}) seats. {free} of them have nobody on them "
                 f"({free_logged} emptied in the log, {free_unlogged} billed with no assignment on record) and {cand} are held by "
                 f"people with no real use in the last two reported months ({e(cand_split)}). Three centres asked for {req} more "
                 f"({e(ask_split)}). Moving {moved} and buying {to_buy} ({e(buy_split)}) adds {money(B['added_cents'], False)} for "
                 f"{FORECAST_LABEL}; buying all {req} adds {money(A['added_cents'], False)}. The difference is {money(save, False)}. "
                 f"Seats only move within {e(FP_NAME)}: a seat of another product is never counted."),
        "evidence": evidence_html(con, f"FREE:{FP}:%", like=True) + "<h4>Candidate seats</h4>"
                    + evidence_html(con, seat_subjects(con, f"verdict = 'candidate' AND product = '{FP}'")),
    })

    sk = cost[("SAI", FP)]
    sk_lag = lag[("SAI", FP)]
    sk_ob = ob[("SAI", FP)]
    sk_office = cost[("SAI", "OFFICE")]
    burst = q(con, "SELECT start_date, count(*) AS n FROM seat_intervals WHERE centre = 'SAI' AND product = ? GROUP BY start_date ORDER BY n DESC LIMIT 1", [FP])[0]
    other_lag = q(con, "SELECT median(median_lag_months) AS m FROM centre_lag WHERE product = ? AND centre <> 'SAI'", [FP])[0]["m"]
    sai_need = [p for p in pools if p["centre"] == "SAI"][0]["needs_evidence"]
    recs.append({
        "title": "Leave Saida's AI seats alone: low use there is late onboarding, not rejection",
        "body": (f"Over all six months only {pct(sk['active_share_reported'])} of Saida's {e(FP_NAME)} seat-months were active, "
                 f"which makes it look like the weakest centre at {money(sk['cents_per_active_month'])} per active user per month. "
                 f"But {burst['n']} seats were assigned on {burst['start_date']} and almost nobody used them before June, which fits the delayed training. "
                 f"From {mlabel(sk_ob['start_month'])} onward {pct(sk['active_share_since_start'])} are active and the cost falls to "
                 f"{money(sk['cents_per_active_since_start'])}. The median Saida user took {sk_lag['median_lag_months']:.0f} months from "
                 f"getting a seat to first real use; in the other centres it took {other_lag:.0f} months. Saida's office suite is "
                 f"{pct(sk_office['active_share_reported'])} active over the same months, so this is about one product, not the centre. "
                 f"{plural(sai_need, 'Saida seat')} still idle but inside the ramp-up window or held under 60 days, so they are held back, not reclaimed."),
        "evidence": evidence_html(con, [f"RAMP:{FP}:SAI"]),
    })

    late = q(con, "SELECT centre, period, received_date FROM raw_files WHERE kind = 'usage' AND received_date > (SELECT as_of FROM params) ORDER BY period LIMIT 1")
    if late:
        lt = late[0]
        n_late = [p for p in pools if p["centre"] == lt["centre"]][0]["candidates"]
        recs.append({
            "title": f"{CENTRES[lt['centre']]}: confirm against the {lt['period']} report before reclaiming",
            "body": (f"The {CENTRES[lt['centre']]} usage report for {lt['period']} was received on {lt['received_date']}, after the decision date {as_of}. "
                     f"Those seat-months are counted as unknown, never as inactive. The {n_late} {CENTRES[lt['centre']]} candidates rest on the two reported months before it. "
                     f"Re-run with <code>--as-of {lt['received_date']}</code> once the file is in to check them."),
            "evidence": evidence_html(con, seat_subjects(con, f"verdict = 'candidate' AND product = '{FP}' AND centre = '{lt['centre']}'")),
        })

    other = q(con, f"""SELECT sum(free_logged + free_unlogged) AS free, sum(candidates) AS cand,
                       sum((free_logged + free_unlogged + candidates) * unit_cents) AS monthly
                       FROM seat_pool WHERE product <> '{FP}'""")[0]
    recs.append({
        "title": f"Outside this decision: {other['free'] + other['cand']} seats of the other products are idle",
        "body": (f"The Organization is billed for {all_billed} seats across {len(PRODUCTS)} products. Besides {FP_NAME}, {other['free']} seats of the other "
                 f"products have nobody on them and {other['cand']} are held by people with no real use. Releasing them would cut "
                 f"{money(other['monthly'], False)} a month at the next renewal. They are listed in the tables below with the product named; "
                 f"they are not part of the two options."),
        "evidence": evidence_html(con, [r["subject"] for r in q(con, f"SELECT DISTINCT subject FROM evidence WHERE subject LIKE 'FREE:%' AND product <> '{FP}' ORDER BY 1")])
                    + "<h4>Candidate seats</h4>" + evidence_html(con, seat_subjects(con, f"verdict = 'candidate' AND product <> '{FP}'")),
    })

    recs.append({
        "title": f"{need_all} more seats need evidence and are left out of both options",
        "body": ("These seats show low or missing usage, but a rule says the evidence is not enough: held under 60 days, "
                 "inside a centre's ramp-up window, inactive in only one month, or missing from a report. They stay where they are "
                 "and are listed below with the reason."),
        "evidence": evidence_html(con, seat_subjects(con, "verdict = 'needs_evidence'")),
    })
    return recs, dict(free=free, cand=cand, need=need_all, billed=billed, all_billed=all_billed, req=req, to_buy=to_buy,
                      moved=moved, A=A, B=B, save=save, bounds=bounds, other=other)


# ----------------------------------------------------------------------------- tables

def seat_table(con, verdict):
    rows = q(con, """
        SELECT h.*,
          (SELECT active_days FROM stg_usage u WHERE u.centre = h.centre AND u.product = h.product AND u.month = h.m2 AND u.user_id = h.user_id) AS d2,
          (SELECT active_days FROM stg_usage u WHERE u.centre = h.centre AND u.product = h.product AND u.month = h.m1 AND u.user_id = h.user_id) AS d1,
          (SELECT count(*) FROM evidence ev WHERE ev.subject = 'SEAT:' || h.seat_id) AS n_src
        FROM holder_status h WHERE h.verdict = ?
        ORDER BY (h.product <> ?), h.product, h.centre, h.seat_id""", [verdict, FP])
    if not rows:
        return "<p class='muted'>None.</p>"

    def days(v):
        return "no data" if v is None else f"{v} day{'s' if v != 1 else ''}"

    body = []
    for r in rows:
        why = REASON_TEXT.get(r["reason"], r["reason"])
        inner = evidence_html(con, ["SEAT:" + r["seat_id"]])
        body.append(
            f"<tr><td><b>{e(PRODUCT_NAME[r['product']])}</b></td><td>{CENTRES[r['centre']]}<br><span class='muted'>{e(r['department'] or '')}</span></td>"
            f"<td><b>{e(r['seat_id'])}</b><br><span class='muted'>{e(r['user_id'])}</span></td>"
            f"<td>{r['start_date']}</td><td>{days(r['d2'])}</td><td>{days(r['d1'])}</td><td>{e(why)}</td>"
            f"<td>{details(f'{r['n_src']} source rows', inner)}</td></tr>")
    hdr = ("<thead><tr><th>Product</th><th>Centre / dept</th><th>Seat / user</th><th>Held since</th>"
           "<th>Active days,<br>2nd last report</th><th>Active days,<br>last report</th><th>Why</th><th>Evidence</th></tr></thead>")
    return "<div class='tw'><table class='seats'>" + hdr + "<tbody>" + "".join(body) + "</tbody></table></div>"


def product_table(con):
    rows = q(con, "SELECT * FROM product_summary ORDER BY (product <> ?), product", [FP])
    body = []
    for r in rows:
        v = PRODUCTS[r["product"]]
        body.append(
            f"<tr><td><b>{e(v[0])}</b><br><span class='muted'>{e(v[1])}, {e(v[2])}</span></td>"
            f"<td class='n'>{money(r['unit_cents'])}</td><td class='n'>{r['seats_billed']}</td><td class='n'>{money(r['spend_total'])}</td>"
            f"<td class='n'>{pct(r['active_share_now'])}</td><td class='n'>{r['free_seats']}</td><td class='n'>{r['candidates']}</td>"
            f"<td class='n'>{r['needs_evidence']}</td></tr>")
    tot = q(con, "SELECT sum(spend_total) AS s, sum(seats_billed) AS n FROM product_summary")[0]
    body.append(f"<tr class='total'><td>All products</td><td></td><td class='n'>{tot['n']}</td><td class='n'>{money(tot['s'])}</td><td colspan='4'></td></tr>")
    return ("<div class='tw'><table><thead><tr><th>Product</th><th>Price per seat per month</th><th>Seats billed, Aug</th>"
            "<th>Invoiced, six months</th><th>Active share, latest month</th><th>Empty seats</th><th>Candidates</th><th>Need evidence</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div>")


def recon_table(con):
    pairs = q(con, """SELECT product, centre, sum(invoice_qty) AS seat_months, sum(invoice_cents) AS inv, sum(held_cents) AS held,
                      sum(reconciled_cents) AS rec, sum(diff_cents) AS diff, sum(naive_overcount) AS over, max(unattributed_seats) AS unattr
                      FROM reconciliation GROUP BY product, centre ORDER BY (product <> ?), product, centre""", [FP])
    body = []
    for p in pairs:
        months = q(con, "SELECT * FROM reconciliation WHERE product = ? AND centre = ? ORDER BY month", [p["product"], p["centre"]])
        inner = ["<div class='tw'><table><thead><tr><th>Month</th><th>Seats billed</th><th>Invoice</th><th>On assigned seats</th>"
                 "<th>On empty seats</th><th>Difference</th><th>Note</th><th>Invoice line</th></tr></thead><tbody>"]
        for r in months:
            note = ""
            if r["naive_overcount"]:
                note = f"<span class='pill warn'>reassigned: counting users gives +{r['naive_overcount']}</span>"
            elif r["unattributed_seats"]:
                note = f"<span class='muted'>{r['unattributed_seats']} billed, never assigned</span>"
            inner.append(
                f"<tr><td>{mlabel(r['month'])}</td><td class='n'>{r['invoice_qty']}</td><td class='n'>{money(r['invoice_cents'])}</td>"
                f"<td class='n'>{money(r['held_cents'])}</td><td class='n'>{money(r['reconciled_cents'] - r['held_cents'])}</td>"
                f"<td class='n ok'>{money(r['diff_cents'])}</td><td>{note}</td><td class='src'>{e(r['source'])}</td></tr>")
        inner.append("</tbody></table></div>")
        flag = "ok" if p["diff"] == 0 else "bad"
        note = ""
        if p["over"]:
            note = f"<span class='pill warn'>{plural(p['over'], 'seat-month')} counted twice if you count users</span>"
        elif p["unattr"]:
            note = f"<span class='muted'>{p['unattr']} billed, never assigned</span>"
        body.append(
            f"<tr><td>{e(PRODUCT_NAME[p['product']])}</td><td>{CENTRES[p['centre']]}</td><td class='n'>{p['seat_months']}</td>"
            f"<td class='n'>{money(p['inv'])}</td><td class='n'>{money(p['held'])}</td><td class='n'>{money(p['rec'] - p['held'])}</td>"
            f"<td class='n {flag}'>{money(p['diff'])}</td><td>{note}</td><td>{details('months', ''.join(inner))}</td></tr>")
    tot = q(con, "SELECT sum(invoice_cents) AS i, sum(held_cents) AS h, sum(reconciled_cents) AS r, sum(diff_cents) AS d FROM reconciliation")[0]
    body.append(f"<tr class='total'><td colspan='3'>All products and centres, six months</td><td class='n'>{money(tot['i'])}</td>"
                f"<td class='n'>{money(tot['h'])}</td><td class='n'>{money(tot['r'] - tot['h'])}</td><td class='n ok'>{money(tot['d'])}</td><td colspan='2'></td></tr>")
    return ("<div class='tw'><table class='recon'><thead><tr><th>Product</th><th>Centre</th><th>Seat-months billed</th><th>Invoice</th>"
            "<th>On assigned seats</th><th>On empty seats</th><th>Difference</th><th>Note</th><th>By month</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div>")


def forecast_section(con):
    rows = q(con, "SELECT * FROM forecast_options ORDER BY option, centre")
    by = {(r["option"], r["centre"]): r for r in rows}
    ass = q(con, "SELECT * FROM forecast_assumptions")
    pools = {r["centre"]: r for r in q(con, "SELECT * FROM forecast_pool")}
    realloc = {r["centre"]: r for r in q(con, "SELECT * FROM realloc")}
    A, B = by[("buy", "ALL")], by[("reallocate", "ALL")]

    def card(title, r, sub, cls):
        return (f"<div class='opt {cls}'><h3>{title}</h3><p class='sub'>{sub}</p>"
                f"<div class='big'>{money(r['added_cents'], False)}</div><p class='lab'>new spend, {FORECAST_LABEL}</p>"
                f"<dl><dt>Seats bought</dt><dd>{int(r['bought'])}</dd><dt>Seats reallocated</dt><dd>{int(r['reallocated'])}</dd>"
                f"<dt>Total quarter spend, {e(FP_NAME)}</dt><dd>{money(r['spend_cents'], False)}</dd>"
                f"<dt>Active users (avg)</dt><dd>{r['active_users']:.1f}</dd>"
                f"<dt>Per active user per month</dt><dd>{money(r['cents_per_active_user_month'])}</dd></dl></div>")

    cards = ("<div class='opts'>" + card("Option A: buy", A, "Buy every seat the centres asked for", "a")
             + card("Option B: reallocate", B, "Move free and candidate seats first, buy only the shortfall", "b") + "</div>")
    t = ["<div class='tw'><table><thead><tr><th>Centre</th><th>Asked for</th><th>Free + candidate seats</th><th>B: from own pool</th>"
         "<th>B: from other centres</th><th>B: to buy</th><th>A: new spend</th><th>B: new spend</th></tr></thead><tbody>"]
    for c in sorted(realloc):
        r = realloc[c]
        t.append(f"<tr><td>{CENTRES[c]}</td><td class='n'>{r['req']}</td><td class='n'>{r['pool']}</td><td class='n'>{r['from_own_pool']}</td>"
                 f"<td class='n'>{r['from_other_centres']}</td><td class='n'>{r['to_buy']}</td>"
                 f"<td class='n'>{money(by[('buy', c)]['added_cents'])}</td><td class='n'>{money(by[('reallocate', c)]['added_cents'])}</td></tr>")
    t.append("</tbody></table></div>")
    holding = [c for c in sorted(pools) if c not in realloc and pools[c]["pool"]]
    extra = ""
    if holding:
        extra = ("<p class='muted'>Centres that did not ask but hold free or candidate seats: "
                 + ", ".join(f"{CENTRES[c]} {pools[c]['pool']}" for c in holding) + ".</p>")
    al = "".join(f"<li><b>{e(a['key'].replace('_', ' '))}:</b> {e(a['value'])}. {e(a['note'])}</li>" for a in ass)
    return svg_forecast(con) + cards + "".join(t) + extra + "<h4>Assumptions</h4><ul class='assume'>" + al + "</ul>"


# ----------------------------------------------------------------------------- page

def render(con, as_of: str) -> str:
    recs, s = recommendations(con, as_of)
    cost = {(r["centre"], r["product"]): r for r in q(con, "SELECT * FROM centre_cost")}
    sk = cost[("SAI", FP)]
    zh = cost[("JBE", FP)]
    tot_spend = q(con, "SELECT sum(invoice_cents) AS c FROM reconciliation")[0]["c"]
    cls = {r["class"]: r["c"] for r in q(con, "SELECT class, sum(cents) AS c FROM spend_by_class GROUP BY class")}
    last_month = q(con, "SELECT max(month) AS m FROM reconciliation")[0]["m"]
    period = f"{s['bounds']['window_start']:%b %Y} to {last_month:%b %Y}"
    idle_other = s["other"]["free"] + s["other"]["cand"]

    kpis = (f"<div class='kpis'>"
            f"<div class='kpi'><b>{money(tot_spend, False)}</b><span>invoiced for {len(PRODUCTS)} products, {period}</span></div>"
            f"<div class='kpi'><b>{s['all_billed']}</b><span>seats billed in the last month</span></div>"
            f"<div class='kpi'><b>{s['free'] + s['cand']}</b><span>{e(FP_NAME)} seats that can move now ({s['free']} empty, {s['cand']} unused)</span></div>"
            f"<div class='kpi'><b>{money(s['save'], False)}</b><span>saved next quarter by moving them first</span></div></div>")

    rec_html = "".join(
        f"<div class='card rec'><h3>{i + 1}. {e(r['title'])}</h3><p>{r['body']}</p>"
        f"{details('Show the source rows (file and line)', r['evidence'])}</div>"
        for i, r in enumerate(recs))

    saida = (
        f"<h2 id='saida'>The centre that looks idle is not</h2>"
        f"<p class='muted'>Saida's six-month use of the {e(FP_NAME)} is {pct(sk['active_share_reported'])} active, against {pct(zh['active_share_reported'])} in Jbeil. "
        "Read alone, that says reclaim the seats. The month-by-month shape says otherwise.</p>"
        f"<div class='card'>{svg_active_share(con)}<p class='legend'>Share of assigned {e(FP_NAME)} seats that were active in the month "
        "(3 or more active days). Open circle: the usage report for that month had not arrived, so nothing is plotted.</p></div>"
        f"<div class='callout'><b>Saida was near zero for three months, then crossed 20% in {mlabel(sk['start_month'])} and reached "
        f"{pct(sk['active_share_since_start'])} across the months since.</b> The seats were handed out in one batch in March and used months later. "
        "Counting only the months since use started, Saida's cost per active user is "
        f"{money(sk['cents_per_active_since_start'])}, close to the other centres. Reclaiming its seats would have punished a late start.</div>"
        f"{details('Show the source rows for Saida (file and line)', evidence_html(con, [f'RAMP:{FP}:SAI']))}")

    cost_block = (f"<h2>Cost per active user, {e(FP_NAME)}, by centre</h2>"
                  "<p class='muted'>Invoiced spend divided by active user-months, using only months with a usage report. "
                  "The grey bar counts all months; the green bar counts the months since the centre started using the product.</p>"
                  f"<div class='two'><div class='card'>{svg_cost_bars(con)}"
                  "<p class='legend'><span class='sw' style='background:var(--bar-all)'></span>all reported months"
                  "<span class='sw' style='background:var(--bar-since)'></span>since use started</p></div>"
                  f"<div class='card'>{svg_class_bars(con)}<p class='legend'>Where the invoiced money went, by product. "
                  f"Unknown ({money(cls.get('unknown', 0), False)} in all) is spend in months with no usable usage data. It is not counted as waste.</p></div></div>")

    fail = """
<h2>Where it fails</h2>
<div class='card fail'><ul>
<li><b>Without sign-in data it cannot say why a seat is silent.</b> The usage report counts active days per product. It cannot tell a person on leave, one who left, one who works offline in the field, and one who does not want the tool. All four look like zero.</li>
<li><b>Saida's explanation is inferred from a shape, not proved.</b> The pipeline sees a bulk assignment followed by a step change. No input says that training was delayed. A one-off campaign would look the same.</li>
<li><b>The answer depends on a late file.</b> The Tripoli August report arrives after the decision date. When it arrives the candidate list can change. The README shows the measured difference.</li>
<li><b>The thresholds are choices.</b> Three active days is a line, not a fact. <code>python -m reconciler sensitivity</code> prints how many candidates each threshold gives.</li>
</ul></div>"""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Software seats: paid, assigned, used</title>
<style>{CSS}</style></head><body><div class="wrap">
<header class="top"><div><div class="kicker">A humanitarian organization in Lebanon &middot; synthetic data</div>
<h1>Software seats: paid, assigned, used</h1>
<p class="lede">Decision date {e(as_of)}. Three centres asked for {s['req']} more {e(FP_NAME)} ({e(FP_KIND)}) seats for {FORECAST_LABEL}. Buy more, or move idle ones first?</p></div>
<button id="theme" class="theme" type="button">Dark mode</button></header>
{kpis}
<h2>Recommendation</h2>
<p class="muted">Generated from the figures below. Open any item to see the exact file and line behind it.</p>
{rec_html}
{saida}
{cost_block}
<h2>All products at a glance</h2>
<p class="muted">Each product is billed per seat per month and reconciled on its own. A seat of one product is never counted as a seat of another.</p>
<div class="card">{product_table(con)}</div>
<h2>Reconciliation: invoice to seat-days</h2>
<p class="muted">Each seat is split across the people who held it, day by day. Every seat-month adds up to exactly one seat's price, so the difference column is zero to the cent.
A reassigned seat is counted once, not once per person. Open "months" for the invoice line behind each month.</p>
<div class="card">{recon_table(con)}</div>
<h2>Reassignment candidates</h2>
<p class="muted">Held by someone with no real use in both of the last two months for which the centre's report arrived, not in a ramp-up window, held at least 60 days. The {e(FP_NAME)} decision uses the first block; the other products are listed for the next renewal.</p>
<div class="card">{seat_table(con, 'candidate')}</div>
<h2>Seats that need more evidence</h2>
<p class="muted">Not moved in either option. Each row says what is missing.</p>
<div class="card">{seat_table(con, 'needs_evidence')}</div>
<h2>Next quarter, two options</h2>
<p class="muted">{FORECAST_LABEL}: {FORECAST_MONTHS} months, {e(FP_NAME)} only. Same requests, same active users, different cost.</p>
{forecast_section(con)}
{fail}
<footer>All data is synthetic; vendors, products and prices are invented. Built by <code>python -m reconciler build</code> from the raw files in <code>data/raw</code>.
No network, no external fonts, no chart library.</footer>
</div><script>{JS}</script></body></html>"""
    return html
