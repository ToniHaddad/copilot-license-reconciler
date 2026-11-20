"""Render the single self-contained HTML report from the warehouse. No external assets."""
from __future__ import annotations

from html import escape

from .config import FORECAST_LABEL, FORECAST_MONTHS, OFFICES, ORG

OFFICE_NAME = {k: v[0] for k, v in OFFICES.items()}
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
    "office_still_ramping": "Office is still ramping up: low use is expected",
    "single_month_inactive": "Inactive in one of the last two months only",
}


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


# ----------------------------------------------------------------------------- charts

def svg_active_share(con):
    data = q(con, "SELECT office, month, active_share, report_received FROM office_month_usage ORDER BY office, month")
    months = sorted({r["month"] for r in data})
    W, H, L, R, T, B = 480, 300, 40, 74, 18, 34
    pw, ph = W - L - R, H - T - B
    x = lambda i: L + pw * i / (len(months) - 1)
    y = lambda v: T + ph * (1 - v)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t1 d1" class="chart">',
           '<title id="t1">Share of seats that are active, by month and office</title>',
           '<desc id="d1">Lebanon and Colombia sit near 80 to 100 percent. Kenya is near zero until June and jumps to about 87 percent in July. The Colombia August report was not received.</desc>']
    for g in (0, .25, .5, .75, 1):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(g):.1f}" y2="{y(g):.1f}" class="grid"/>')
        out.append(f'<text x="{L - 6}" y="{y(g) + 4:.1f}" text-anchor="end" class="tick">{int(g * 100)}%</text>')
    for i, m in enumerate(months):
        out.append(f'<text x="{x(i):.1f}" y="{H - 12}" text-anchor="middle" class="tick">{mlabel(m)}</text>')
    marker = {"LB": "circle", "KE": "square", "CO": "tri"}
    for code in ("LB", "CO", "KE"):
        pts = [(i, r["active_share"]) for i, m in enumerate(months)
               for r in data if r["office"] == code and r["month"] == m and r["active_share"] is not None]
        path = " ".join(f"{'M' if k == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for k, (i, v) in enumerate(pts))
        cls = f"line s-{code}" + (" thick" if code == "KE" else "")
        out.append(f'<path d="{path}" class="{cls}"/>')
        for i, v in pts:
            cx, cy = x(i), y(v)
            if marker[code] == "circle":
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" class="dot f-{code}"/>')
            elif marker[code] == "square":
                out.append(f'<rect x="{cx - 3.6:.1f}" y="{cy - 3.6:.1f}" width="7.2" height="7.2" class="dot f-{code}"/>')
            else:
                out.append(f'<path d="M{cx:.1f},{cy - 4.4:.1f} L{cx + 4:.1f},{cy + 3:.1f} L{cx - 4:.1f},{cy + 3:.1f}Z" class="dot f-{code}"/>')
        if pts:
            i, v = pts[-1]
            out.append(f'<text x="{x(i) + 9:.1f}" y="{y(v) + (0 if code != "CO" else 13):.1f}" class="lbl l-{code}">{OFFICE_NAME[code]}</text>')
    missing = [(r["office"], r["month"]) for r in data if not r["report_received"]]
    for code, m in missing:
        i = months.index(m)
        out.append(f'<circle cx="{x(i):.1f}" cy="{y(0):.1f}" r="4" class="hollow"/>')
        out.append(f'<text x="{x(i):.1f}" y="{y(0) - 9:.1f}" text-anchor="middle" class="note">{OFFICE_NAME[code]}: no report yet</text>')
    out.append(f'<text x="{x(0) + 4:.1f}" y="{y(0) - 8:.1f}" class="note">30 seats assigned in one day</text>')
    out.append("</svg>")
    return "".join(out)


def svg_cost_bars(con):
    rows = q(con, "SELECT * FROM office_cost ORDER BY office")
    W, H = 480, 190
    L, R = 78, 56
    mx = max(max(r["cents_per_active_month"] or 0, r["cents_per_active_since_start"] or 0) for r in rows) * 1.0
    pw = W - L - R
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t2 d2" class="chart">',
           '<title id="t2">Cost per active user per month, by office</title>',
           '<desc id="d2">Two bars per office: all months with a usage report, and only the months since the office started using Copilot.</desc>']
    y = 14
    for r in rows:
        out.append(f'<text x="{L - 8}" y="{y + 22}" text-anchor="end" class="lbl l-{r["office"]}">{OFFICE_NAME[r["office"]]}</text>')
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
    rows = q(con, """SELECT office, class, sum(cents) AS cents FROM spend_by_class GROUP BY office, class""")
    order = ["active", "confirmed_inactive", "unknown", "unassigned"]
    W, H, L, R = 480, 170, 78, 16
    pw = W - L - R
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="t3 d3" class="chart">',
           '<title id="t3">Where the six months of spend went, by office</title>',
           '<desc id="d3">Each bar splits the invoiced spend into active, confirmed inactive, unknown because usage data is missing, and paid but unassigned.</desc>']
    y = 10
    for code in ("LB", "KE", "CO"):
        by = {r["class"]: r["cents"] for r in rows if r["office"] == code}
        tot = sum(by.values())
        out.append(f'<text x="{L - 8}" y="{y + 17}" text-anchor="end" class="lbl l-{code}">{OFFICE_NAME[code]}</text>')
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
        out.append(f'<rect x="{lx}" y="{H - 24}" width="11" height="11" class="seg c-{c}"/>')
        out.append(f'<text x="{lx + 16}" y="{H - 14}" class="tick">{CLASS_LABEL[c].split(" (")[0].replace("Paid, nobody assigned", "Unassigned")}</text>')
        lx += 16 + 7.4 * len(CLASS_LABEL[c].split(" (")[0].replace("Paid, nobody assigned", "Unassigned")) + 14
    out.append("</svg>")
    return "".join(out)


def svg_forecast(con):
    rows = {r["option"]: r for r in q(con, "SELECT * FROM forecast_options WHERE office = 'ALL'")}
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

def evidence_html(con, subjects, like=False, limit=None):
    if like:
        rows = q(con, "SELECT * FROM evidence WHERE subject LIKE ? ORDER BY subject, kind, file_name, line_no", [subjects])
    else:
        ph = ", ".join("?" * len(subjects))
        rows = q(con, f"SELECT * FROM evidence WHERE subject IN ({ph}) ORDER BY subject, kind, file_name, line_no", list(subjects))
    if limit:
        rows = rows[:limit]
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


# ----------------------------------------------------------------------------- recommendation

def recommendations(con, as_of):
    pools = q(con, "SELECT * FROM office_pool ORDER BY office")
    realloc = {r["office"]: r for r in q(con, "SELECT * FROM realloc")}
    fc = {(r["option"], r["office"]): r for r in q(con, "SELECT * FROM forecast_options")}
    cost = {r["office"]: r for r in q(con, "SELECT * FROM office_cost")}
    lag = {r["office"]: r for r in q(con, "SELECT * FROM office_lag")}
    ob = {r["office"]: r for r in q(con, "SELECT * FROM office_onboarding")}
    bounds = q(con, "SELECT * FROM bounds")[0]
    free = sum(p["free_logged"] + p["free_unlogged"] for p in pools)
    cand = sum(p["candidates"] for p in pools)
    need = sum(p["needs_evidence"] for p in pools)
    billed = sum(p["seats_billed"] for p in pools)
    req = sum(r["req"] for r in realloc.values())
    to_buy = sum(r["to_buy"] for r in realloc.values())
    moved = free + cand if free + cand <= req else req
    A, B = fc[("buy", "ALL")], fc[("reallocate", "ALL")]
    save = A["added_cents"] - B["added_cents"]
    recs = []

    buy_split = ", ".join(f"{OFFICE_NAME[o]} {r['to_buy']}" for o, r in sorted(realloc.items()) if r["to_buy"])
    cand_split = ", ".join(f"{OFFICE_NAME[p['office']]} {p['candidates']}" for p in pools if p["candidates"])
    recs.append({
        "title": f"Reallocate {moved} seats first, then buy only the {to_buy} that are still missing",
        "body": (f"{ORG} is billed for {billed} seats. {free} of them have nobody on them ({sum(p['free_logged'] for p in pools)} "
                 f"emptied in the log, {sum(p['free_unlogged'] for p in pools)} billed with no assignment on record) and {cand} are held by "
                 f"people with no real use in the last two reported months ({e(cand_split)}). The three offices asked for {req}. "
                 f"Moving {moved} and buying {to_buy} ({e(buy_split)}) adds {money(B['added_cents'], False)} for {FORECAST_LABEL}; "
                 f"buying all {req} adds {money(A['added_cents'], False)}. The difference is {money(save, False)}."),
        "evidence": evidence_html(con, "FREE:%", like=True) + "<h4>Candidate seats</h4>" + evidence_html(
            con, [r["subject"] for r in q(con, "SELECT DISTINCT 'SEAT:' || seat_id AS subject FROM holder_status WHERE verdict = 'candidate'")]),
    })

    ke_cost, ke_lag, ke_ob = cost["KE"], lag["KE"], ob["KE"]
    burst = q(con, "SELECT start_date, count(*) AS n FROM seat_intervals WHERE office = 'KE' GROUP BY start_date ORDER BY n DESC LIMIT 1")[0]
    recs.append({
        "title": "Leave Kenya's seats alone: low usage there is late onboarding, not rejection",
        "body": (f"Over all six months only {pct(ke_cost['active_share_reported'])} of Kenya's seat-months were active, "
                 f"which makes it look like the weakest office at {money(ke_cost['cents_per_active_month'])} per active user per month. "
                 f"But {burst['n']} seats were assigned on {burst['start_date']} and nobody used them until June. "
                 f"From {mlabel(ke_ob['start_month'])} onward {pct(ke_cost['active_share_since_start'])} are active and the cost falls to "
                 f"{money(ke_cost['cents_per_active_since_start'])}. The median Kenya user took {ke_lag['median_lag_months']:.0f} months from "
                 f"getting a seat to first real use; in Lebanon and Colombia it took {lag['LB']['median_lag_months']:.0f}. "
                 f"{pools[[p['office'] for p in pools].index('KE')]['needs_evidence']} Kenya seats are still idle but sit inside the ramp-up window, so they are held back, not reclaimed."),
        "evidence": evidence_html(con, ["RAMP:KE"]),
    })

    co_missing = q(con, "SELECT period, received_date FROM raw_files WHERE kind = 'usage' AND office = 'CO' AND received_date > (SELECT as_of FROM params)")
    if co_missing:
        cm = co_missing[0]
        co_c = pools[[p["office"] for p in pools].index("CO")]["candidates"]
        recs.append({
            "title": f"Colombia: confirm against the {cm['period']} report before reclaiming",
            "body": (f"The Colombia usage report for {cm['period']} was received on {cm['received_date']}, after the decision date {as_of}. "
                     f"Those seat-months are counted as unknown, never as inactive. The {co_c} Colombia candidates rest on the two reported months before it. "
                     f"Re-run with <code>--as-of {cm['received_date']}</code> once the file is in to check them."),
            "evidence": evidence_html(con, [r["subject"] for r in q(con, "SELECT DISTINCT 'SEAT:' || seat_id AS subject FROM holder_status WHERE verdict = 'candidate' AND office = 'CO' LIMIT 2")]),
        })

    recs.append({
        "title": f"{need} more seats need evidence and are left out of both options",
        "body": ("These seats show low or missing usage, but a rule says the evidence is not enough: held under 60 days, "
                 "inside an office's ramp-up window, inactive in only one month, or missing from a report. They stay where they are "
                 "and are listed below with the reason."),
        "evidence": evidence_html(con, [r["subject"] for r in q(con, "SELECT DISTINCT 'SEAT:' || seat_id AS subject FROM holder_status WHERE verdict = 'needs_evidence'")]),
    })
    return recs, dict(free=free, cand=cand, need=need, billed=billed, req=req, to_buy=to_buy, moved=moved, A=A, B=B, save=save, bounds=bounds)


# ----------------------------------------------------------------------------- tables

def seat_table(con, verdict):
    rows = q(con, """
        SELECT h.*,
          (SELECT active_days FROM stg_usage u WHERE u.office = h.office AND u.month = h.m2 AND u.user_id = h.user_id) AS d2,
          (SELECT active_days FROM stg_usage u WHERE u.office = h.office AND u.month = h.m1 AND u.user_id = h.user_id) AS d1,
          (SELECT count(*) FROM evidence ev WHERE ev.subject = 'SEAT:' || h.seat_id) AS n_src
        FROM holder_status h WHERE h.verdict = ? ORDER BY h.office, h.seat_id""", [verdict])
    if not rows:
        return "<p class='muted'>None.</p>"
    body = []
    for r in rows:
        why = REASON_TEXT.get(r["reason"], r["reason"])
        d1 = "no data" if r["d1"] is None else f"{r['d1']} days"
        d2 = "no data" if r["d2"] is None else f"{r['d2']} days"
        inner = evidence_html(con, ["SEAT:" + r["seat_id"]])
        body.append(
            f"<tr><td>{OFFICE_NAME[r['office']]}</td><td><b>{e(r['seat_id'])}</b><br><span class='muted'>{e(r['user_id'])}</span></td>"
            f"<td>{r['start_date']}</td><td>{d2}</td><td>{d1}</td><td>{e(why)}</td>"
            f"<td>{details(f'{r['n_src']} source rows', inner)}</td></tr>")
    hdr = ("<thead><tr><th>Office</th><th>Seat / user</th><th>Held since</th>"
           "<th>Active days,<br>2nd last report</th><th>Active days,<br>last report</th><th>Why</th><th>Evidence</th></tr></thead>")
    return "<div class='tw'><table class='seats'>" + hdr + "<tbody>" + "".join(body) + "</tbody></table></div>"


def recon_table(con):
    rows = q(con, "SELECT * FROM reconciliation ORDER BY office, month")
    body, last = [], None
    for r in rows:
        flag = "ok" if r["diff_cents"] == 0 and r["status"] == "ok" else "bad"
        if r["naive_overcount"]:
            note = f"<span class='pill warn'>seat reassigned: counting users would give {r['naive_overcount']} extra</span>"
        elif r["unattributed_seats"]:
            note = f"<span class='muted'>{r['unattributed_seats']} billed, never assigned</span>"
        else:
            note = ""
        body.append(
            f"<tr><td>{OFFICE_NAME[r['office']]}</td><td>{mlabel(r['month'])}</td><td class='n'>{r['invoice_qty']}</td>"
            f"<td class='n'>{money(r['invoice_cents'])}</td><td class='n'>{money(r['held_cents'])}</td>"
            f"<td class='n'>{money(r['reconciled_cents'] - r['held_cents'])}</td><td class='n {flag}'>{money(r['diff_cents'])}</td>"
            f"<td>{note}</td><td class='src'>{e(r['source'])}</td></tr>")
    tot = q(con, "SELECT sum(invoice_cents) AS i, sum(held_cents) AS h, sum(reconciled_cents) AS r, sum(diff_cents) AS d FROM reconciliation")[0]
    body.append(f"<tr class='total'><td colspan='3'>All offices, six months</td><td class='n'>{money(tot['i'])}</td>"
                f"<td class='n'>{money(tot['h'])}</td><td class='n'>{money(tot['r'] - tot['h'])}</td><td class='n ok'>{money(tot['d'])}</td><td colspan='2'></td></tr>")
    return ("<div class='tw'><table class='recon'><thead><tr><th>Office</th><th>Month</th><th>Seats billed</th><th>Invoice</th>"
            "<th>On assigned seats</th><th>On empty seats</th><th>Difference</th><th>Note</th><th>Invoice line</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div>")


def forecast_section(con):
    rows = q(con, "SELECT * FROM forecast_options ORDER BY option, office")
    by = {(r["option"], r["office"]): r for r in rows}
    ass = q(con, "SELECT * FROM forecast_assumptions")
    pools = {r["office"]: r for r in q(con, "SELECT * FROM office_pool")}
    realloc = {r["office"]: r for r in q(con, "SELECT * FROM realloc")}
    A, B = by[("buy", "ALL")], by[("reallocate", "ALL")]

    def card(title, r, sub, cls):
        return (f"<div class='opt {cls}'><h3>{title}</h3><p class='sub'>{sub}</p>"
                f"<div class='big'>{money(r['added_cents'], False)}</div><p class='lab'>new spend, {FORECAST_LABEL}</p>"
                f"<dl><dt>Seats bought</dt><dd>{int(r['bought'])}</dd><dt>Seats reallocated</dt><dd>{int(r['reallocated'])}</dd>"
                f"<dt>Total quarter spend</dt><dd>{money(r['spend_cents'], False)}</dd>"
                f"<dt>Active users (avg)</dt><dd>{r['active_users']:.1f}</dd>"
                f"<dt>Per active user per month</dt><dd>{money(r['cents_per_active_user_month'])}</dd></dl></div>")

    cards = ("<div class='opts'>" + card("Option A: buy", A, "Buy every seat each office asked for", "a")
             + card("Option B: reallocate", B, "Move free and candidate seats first, buy only the shortfall", "b") + "</div>")
    t = ["<div class='tw'><table><thead><tr><th>Office</th><th>Asked for</th><th>Free + candidate seats</th><th>Option B: from own pool</th>"
         "<th>Option B: from other offices</th><th>Option B: to buy</th><th>A: new spend</th><th>B: new spend</th></tr></thead><tbody>"]
    for o in sorted(realloc):
        r = realloc[o]
        t.append(f"<tr><td>{OFFICE_NAME[o]}</td><td class='n'>{r['req']}</td><td class='n'>{r['pool']}</td><td class='n'>{r['from_own_pool']}</td>"
                 f"<td class='n'>{r['from_other_offices']}</td><td class='n'>{r['to_buy']}</td>"
                 f"<td class='n'>{money(by[('buy', o)]['added_cents'])}</td><td class='n'>{money(by[('reallocate', o)]['added_cents'])}</td></tr>")
    t.append("</tbody></table></div>")
    al = "".join(f"<li><b>{e(a['key'].replace('_', ' '))}:</b> {e(a['value'])}. {e(a['note'])}</li>" for a in ass)
    prices = ", ".join(f"{OFFICE_NAME[o]} {money(p['unit_cents'])}" for o, p in sorted(pools.items()))
    al += f"<li><b>seat prices per month:</b> {e(prices)}. Taken from each office's latest invoice.</li>"
    return svg_forecast(con) + cards + "".join(t) + "<h4>Assumptions</h4><ul class='assume'>" + al + "</ul>"


# ----------------------------------------------------------------------------- page

CSS = """
:root{--bg:#f4f1ea;--surf:#fffdf8;--ink:#1d2623;--muted:#5b6662;--line:#ddd6c8;--accent:#0d6b61;--accent-soft:#d9ece8;
--warn:#a8480e;--warn-soft:#f6e2d3;--ok:#1d7a4a;--bad:#b3261e;
--c-lb:#2a5db0;--c-ke:#c4521a;--c-co:#14796d;
--c-active:#2f8f5b;--c-confirmed_inactive:#c4521a;--c-unknown:#9a9a9a;--c-unassigned:#d9a521;
--bar-all:#7a8a86;--bar-since:#0d6b61;--buy:#b3592e;--realloc:#0d6b61;--shadow:0 1px 2px rgba(30,40,35,.08)}
:root[data-theme=dark]{--bg:#111715;--surf:#18201d;--ink:#e8eeeb;--muted:#9bada6;--line:#2b3733;--accent:#52c4b3;--accent-soft:#1c3a35;
--warn:#f0a070;--warn-soft:#3a2819;--ok:#5fcf91;--bad:#ff8a80;
--c-lb:#7fa9ef;--c-ke:#f08a52;--c-co:#4ccbb9;
--c-active:#4cc486;--c-confirmed_inactive:#f08a52;--c-unknown:#8a8f8d;--c-unassigned:#e6bd4a;
--bar-all:#6f817c;--bar-since:#52c4b3;--buy:#e08a5a;--realloc:#52c4b3;--shadow:none}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111715;--surf:#18201d;--ink:#e8eeeb;--muted:#9bada6;--line:#2b3733;--accent:#52c4b3;--accent-soft:#1c3a35;
--warn:#f0a070;--warn-soft:#3a2819;--ok:#5fcf91;--bad:#ff8a80;
--c-lb:#7fa9ef;--c-ke:#f08a52;--c-co:#4ccbb9;
--c-active:#4cc486;--c-confirmed_inactive:#f08a52;--c-unknown:#8a8f8d;--c-unassigned:#e6bd4a;
--bar-all:#6f817c;--bar-since:#52c4b3;--buy:#e08a5a;--realloc:#52c4b3;--shadow:none}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px 56px}
header.top{padding:28px 0 8px;display:flex;gap:16px;justify-content:space-between;align-items:flex-start}
h1{font:700 clamp(1.5rem,4.5vw,2.2rem)/1.15 Georgia,"Times New Roman",serif;margin:0 0 6px;letter-spacing:-.01em}
.lede{color:var(--muted);margin:0;max-width:60ch}
h2{font:700 1.35rem/1.25 Georgia,"Times New Roman",serif;margin:44px 0 6px}
h3{margin:0;font-size:1.05rem}
h4{margin:18px 0 6px;font-size:.95rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.kicker{color:var(--accent);font-weight:700;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase}
.muted{color:var(--muted)}
button.theme{background:var(--surf);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:6px 12px;font:inherit;font-size:.85rem;cursor:pointer}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0 0}
.kpi{background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:var(--shadow)}
.kpi b{display:block;font:700 1.55rem/1.1 Georgia,serif}
.kpi span{font-size:.82rem;color:var(--muted)}
.card{background:var(--surf);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0;box-shadow:var(--shadow)}
.rec h3{font-size:1.05rem;line-height:1.3}
.rec p{margin:.5em 0 .7em}
details{margin:6px 0}
summary{cursor:pointer;color:var(--accent);font-weight:600;font-size:.9rem}
details[open]>summary{margin-bottom:8px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.76rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:transparent;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.src{font-family:Consolas,"SF Mono",monospace;font-size:.78rem;white-space:nowrap;color:var(--muted)}
td.ok{color:var(--ok);font-weight:700}td.bad{color:var(--bad);font-weight:700}
tr.total td{font-weight:700;border-top:2px solid var(--ink)}
code{font-family:Consolas,"SF Mono",monospace;font-size:.78rem;word-break:break-all}
.ev table{font-size:.8rem}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.76rem}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.two{display:grid;grid-template-columns:1fr;gap:14px}
@media(min-width:820px){.two{grid-template-columns:1fr 1fr}}
.chart{width:100%;height:auto;display:block}
.chart text{font-family:"Segoe UI",system-ui,sans-serif}
.tick{font-size:12px;fill:var(--muted)}
.note{font-size:11.5px;fill:var(--muted);font-style:italic}
.lbl{font-size:13px;font-weight:700;fill:var(--ink)}
.val{font-size:12.5px;font-weight:700;fill:var(--ink)}
.seglabel{font-size:12px;font-weight:700;fill:#fff}
.grid{stroke:var(--line);stroke-width:1}
.line{fill:none;stroke-width:2.2;stroke-linejoin:round}.line.thick{stroke-width:3.6}
.s-LB{stroke:var(--c-lb)}.s-KE{stroke:var(--c-ke)}.s-CO{stroke:var(--c-co)}
.f-LB{fill:var(--c-lb)}.f-KE{fill:var(--c-ke)}.f-CO{fill:var(--c-co)}
.l-LB{fill:var(--c-lb)}.l-KE{fill:var(--c-ke)}.l-CO{fill:var(--c-co)}
.hollow{fill:var(--surf);stroke:var(--muted);stroke-width:1.6;stroke-dasharray:2 2}
.bar{fill:var(--bar-all)}.b-since{fill:var(--bar-since)}.b-buy{fill:var(--buy)}.b-realloc{fill:var(--realloc)}
.c-active{fill:var(--c-active)}.c-confirmed_inactive{fill:var(--c-confirmed_inactive)}.c-unknown{fill:var(--c-unknown)}.c-unassigned{fill:var(--c-unassigned)}
.seg{stroke:var(--surf);stroke-width:1}
.legend{font-size:.82rem;color:var(--muted);margin:4px 0 0}
.sw{display:inline-block;width:11px;height:11px;border-radius:2px;margin:0 4px -1px 10px}
.opts{display:grid;grid-template-columns:1fr;gap:14px;margin:14px 0}
@media(min-width:700px){.opts{grid-template-columns:1fr 1fr}}
.opt{background:var(--surf);border:1px solid var(--line);border-top:5px solid var(--buy);border-radius:12px;padding:16px 18px}
.opt.b{border-top-color:var(--realloc)}
.opt .sub{color:var(--muted);margin:2px 0 8px;font-size:.9rem}
.opt .big{font:700 2.1rem/1 Georgia,serif}
.opt .lab{margin:2px 0 10px;color:var(--muted);font-size:.85rem}
dl{display:grid;grid-template-columns:1fr auto;gap:4px 12px;margin:0;font-size:.9rem}dt{color:var(--muted)}dd{margin:0;text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.assume{font-size:.88rem;color:var(--muted);padding-left:18px}
.assume b{color:var(--ink)}
.callout{border-left:5px solid var(--c-ke);background:var(--warn-soft);border-radius:0 10px 10px 0;padding:12px 16px;margin:12px 0}
.fail li{margin:6px 0}
footer{margin-top:48px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:14px}
"""

CSS = CSS.replace("#9bada6", "#9bada6".replace(" ", ""))

JS = """
(function(){var b=document.getElementById('theme'),r=document.documentElement;
function cur(){var t=r.getAttribute('data-theme');if(t)return t;return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}
b.addEventListener('click',function(){var n=cur()==='dark'?'light':'dark';r.setAttribute('data-theme',n);b.textContent=n==='dark'?'Light mode':'Dark mode'});
b.textContent=cur()==='dark'?'Light mode':'Dark mode';})();
"""


def render(con, as_of: str) -> str:
    recs, s = recommendations(con, as_of)
    cost = {r["office"]: r for r in q(con, "SELECT * FROM office_cost")}
    ke = cost["KE"]
    tot_spend = q(con, "SELECT sum(invoice_cents) AS c FROM reconciliation")[0]["c"]
    cls = {r["class"]: r["c"] for r in q(con, "SELECT class, sum(cents) AS c FROM spend_by_class GROUP BY class")}
    b = s["bounds"]
    last_month = q(con, "SELECT max(month) AS m FROM reconciliation")[0]["m"]
    period = f"{b['window_start']:%b %Y} to {last_month:%b %Y}"
    n_cand = s["cand"]

    kpis = (f"<div class='kpis'>"
            f"<div class='kpi'><b>{money(tot_spend, False)}</b><span>invoiced, {period}</span></div>"
            f"<div class='kpi'><b>{s['billed']}</b><span>seats billed in the last month</span></div>"
            f"<div class='kpi'><b>{s['free'] + n_cand}</b><span>seats that can move now ({s['free']} empty, {n_cand} unused)</span></div>"
            f"<div class='kpi'><b>{money(s['save'], False)}</b><span>saved next quarter by moving them first</span></div></div>")

    rec_html = "".join(
        f"<div class='card rec'><h3>{i + 1}. {e(r['title'])}</h3><p>{r['body']}</p>"
        f"{details('Show the source rows (file and line)', r['evidence'])}</div>"
        for i, r in enumerate(recs))

    kenya_block = (
        "<h2 id='kenya'>The office that looks idle is not</h2>"
        f"<p class='muted'>Kenya's six-month usage is {pct(ke['active_share_reported'])} active, against {pct(cost['LB']['active_share_reported'])} in Lebanon. "
        "Read alone, that says reclaim the seats. The month-by-month shape says otherwise.</p>"
        f"<div class='card'>{svg_active_share(con)}<p class='legend'>Share of assigned seats that were active in the month "
        "(3 or more active days). Open circle: the usage report for that month had not arrived, so nothing is plotted.</p></div>"
        f"<div class='callout'><b>Kenya was near zero for three months, then crossed {pct(0.2)} in {mlabel(ke['start_month'])} and reached "
        f"{pct(ke['active_share_since_start'])} across the months since.</b> The seats were handed out in one batch in March and used months later. "
        "Counting only the months since usage started, Kenya's cost per active user is "
        f"{money(ke['cents_per_active_since_start'])}, in line with the other offices. Reclaiming its seats would have punished a late start.</div>"
        f"{details('Show the source rows for Kenya (file and line)', evidence_html(con, ['RAMP:KE']))}")

    cost_block = ("<h2>Cost per active user, by office</h2>"
                  "<p class='muted'>Invoiced spend divided by active user-months, using only months with a usage report. "
                  "The lighter bar counts all months; the green bar counts the months since the office started using it.</p>"
                  f"<div class='two'><div class='card'>{svg_cost_bars(con)}"
                  "<p class='legend'><span class='sw' style='background:var(--bar-all)'></span>all reported months"
                  "<span class='sw' style='background:var(--bar-since)'></span>since usage started</p></div>"
                  f"<div class='card'>{svg_class_bars(con)}<p class='legend'>Where the invoiced money went. "
                  f"Unknown ({money(cls.get('unknown', 0), False)}) is spend in months with no usable usage data. It is not counted as waste.</p></div></div>")

    fail = """
<h2>Where it fails</h2>
<div class='card fail'><ul>
<li><b>Without sign-in data it cannot say why a seat is silent.</b> The usage report counts active days. It cannot tell a user on leave, a user who left, a user who works offline in the field, and a user who simply does not want the tool. All four look like zero.</li>
<li><b>Kenya's explanation is inferred from a shape, not proved.</b> The pipeline sees a bulk assignment followed by a step change in use. No input says that training started in June. A one-off campaign would look the same.</li>
<li><b>The answer depends on a late file.</b> Colombia's August report arrives after the decision date. When it arrives the candidate list can change. The README shows the measured difference.</li>
<li><b>The thresholds are choices.</b> Three active days is a line, not a fact. <code>python -m reconciler sensitivity</code> prints how many candidates each threshold gives.</li>
</ul></div>"""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Copilot licence reconciliation - {e(ORG)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header class="top"><div><div class="kicker">{e(ORG)} &middot; synthetic data</div>
<h1>Copilot licences: paid, assigned, used</h1>
<p class="lede">Decision date {e(as_of)}. Three offices asked for {s['req']} more Microsoft 365 Copilot seats for {FORECAST_LABEL}. Should we buy, reassign, or train first?</p></div>
<button id="theme" class="theme" type="button">Dark mode</button></header>
{kpis}
<h2>Recommendation</h2>
<p class="muted">Generated from the figures below. Open any item to see the exact file and line behind it.</p>
{rec_html}
{kenya_block}
{cost_block}
<h2>Reconciliation: invoice to seat-days</h2>
<p class="muted">Each seat is split across the people who held it, day by day. Every seat-month adds up to exactly one seat's price, so the difference column is zero to the cent.
A reassigned seat is counted once, not once per user.</p>
<div class="card">{recon_table(con)}</div>
<h2>Reassignment candidates</h2>
<p class="muted">Held by someone with no real use in both of the last two months for which the office's report arrived, not in a ramp-up window, held at least 60 days.</p>
<div class="card">{seat_table(con, 'candidate')}</div>
<h2>Seats that need more evidence</h2>
<p class="muted">Not moved in either option. Each row says what is missing.</p>
<div class="card">{seat_table(con, 'needs_evidence')}</div>
<h2>Next quarter, two options</h2>
<p class="muted">{FORECAST_LABEL}: {FORECAST_MONTHS} months. Same requests, same active users, different cost.</p>
{forecast_section(con)}
{fail}
<footer>All data is synthetic. Built by <code>python -m reconciler build</code> from the raw files in <code>data/raw</code>.
No network, no external fonts, no chart library.</footer>
</div><script>{JS}</script></body></html>"""
    return html
