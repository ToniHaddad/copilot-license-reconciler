-- Source rows behind every statement in the report: file name, line number, the line itself.
CREATE OR REPLACE TABLE evidence (
    subject VARCHAR, centre VARCHAR, product VARCHAR, kind VARCHAR, file_name VARCHAR, line_no INTEGER,
    raw_line VARCHAR, note VARCHAR
);

-- Seats flagged as candidate or needing evidence: the assignment event and the usage rows.
INSERT INTO evidence
SELECT 'SEAT:' || h.seat_id, h.centre, h.product, 'assignment', h.start_file, h.start_line, e.raw_line,
       'seat held by ' || h.user_id || ' since ' || h.start_date
FROM holder_status h JOIN raw_events e ON e.file_name = h.start_file AND e.line_no = h.start_line
WHERE h.verdict IN ('candidate', 'needs_evidence');

INSERT INTO evidence
SELECT 'SEAT:' || h.seat_id, h.centre, h.product, 'usage', u.file_name, u.line_no, u.raw_line,
       strftime(u.month, '%Y-%m') || ': ' || u.active_days || ' active days'
FROM holder_status h
JOIN last_two l ON l.centre = h.centre AND l.product = h.product
JOIN stg_usage u ON u.centre = h.centre AND u.product = h.product AND u.month = l.month AND u.user_id = h.user_id
WHERE h.verdict IN ('candidate', 'needs_evidence');

-- A report that exists but was received after the as-of date: named, never read as inactivity.
INSERT INTO evidence
SELECT 'SEAT:' || h.seat_id, h.centre, h.product, 'report_missing', f.file_name, 0, '(file not read)',
       strftime(m.month, '%Y-%m') || ' report received ' || f.received_date
       || ', after the as-of date: counted as unknown, not inactive'
FROM holder_status h
JOIN months m ON m.month > (SELECT max(month) FROM report_months r WHERE r.centre = h.centre AND r.product = h.product)
JOIN raw_files f ON f.centre = h.centre AND f.kind = 'usage' AND f.period = strftime(m.month, '%Y-%m')
WHERE h.verdict IN ('candidate', 'needs_evidence');

-- Free seats: the log line that emptied the seat, and the invoice that still bills it.
INSERT INTO evidence
SELECT 'FREE:' || s.product || ':' || s.centre, s.centre, s.product, 'unassign', s.file_name, s.line_no, e.raw_line,
       s.seat_id || ' empty since ' || s.last_event_date
FROM free_seats s JOIN raw_events e ON e.file_name = s.file_name AND e.line_no = s.line_no;

INSERT INTO evidence
SELECT 'FREE:' || p.product || ':' || p.centre, p.centre, p.product, 'invoice', i.file_name, i.line_no, i.raw_line,
       strftime(p.invoice_month, '%Y-%m') || ' invoice bills ' || p.seats_billed || ' seats; the log accounts for '
       || (p.seats_billed - p.free_unlogged) || ', so ' || p.free_unlogged || ' are billed with no assignment on record'
FROM seat_pool p JOIN stg_invoice i
  ON i.centre = p.centre AND i.product = p.product AND i.month = p.invoice_month
WHERE p.free_unlogged > 0 OR p.free_logged > 0;

-- Centres whose use of a product started late: users who held a seat for months before their first active month.
INSERT INTO evidence
WITH late AS (
    SELECT l.centre, l.product, l.user_id, l.first_assigned, l.first_active_month,
           row_number() OVER (PARTITION BY l.centre, l.product ORDER BY l.user_id) AS rn
    FROM user_lag l JOIN centre_onboarding o USING (centre, product)
    WHERE o.start_month > (SELECT window_start FROM bounds)
      AND l.first_active_month >= date_trunc('month', l.first_assigned)::DATE + INTERVAL 2 MONTH
)
SELECT 'RAMP:' || late.product || ':' || late.centre, late.centre, late.product, 'assignment', i.start_file, i.start_line, e.raw_line,
       late.user_id || ' assigned ' || late.first_assigned
FROM late
JOIN seat_intervals i ON i.centre = late.centre AND i.product = late.product AND i.user_id = late.user_id
     AND i.start_date = late.first_assigned
JOIN raw_events e ON e.file_name = i.start_file AND e.line_no = i.start_line
WHERE late.rn <= 4;

INSERT INTO evidence
WITH late AS (
    SELECT l.centre, l.product, l.user_id, l.first_assigned, l.first_active_month,
           row_number() OVER (PARTITION BY l.centre, l.product ORDER BY l.user_id) AS rn
    FROM user_lag l JOIN centre_onboarding o USING (centre, product)
    WHERE o.start_month > (SELECT window_start FROM bounds)
      AND l.first_active_month >= date_trunc('month', l.first_assigned)::DATE + INTERVAL 2 MONTH
)
SELECT 'RAMP:' || late.product || ':' || late.centre, late.centre, late.product, 'usage', c.usage_file, c.usage_line, u.raw_line,
       late.user_id || ' ' || strftime(c.month, '%Y-%m') || ': ' || c.active_days || ' active days'
FROM late
JOIN seat_month_class c ON c.centre = late.centre AND c.product = late.product AND c.user_id = late.user_id
     AND (c.month = (SELECT window_start FROM bounds) OR c.month = late.first_active_month)
JOIN stg_usage u ON u.file_name = c.usage_file AND u.line_no = c.usage_line
WHERE late.rn <= 4;
