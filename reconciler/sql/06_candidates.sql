-- Reassignment candidates versus seats that need more evidence.
-- The two latest months for which the office's report was actually received are the evidence window.
CREATE OR REPLACE TABLE last_two AS
SELECT office, month, rn FROM (
    SELECT office, month, row_number() OVER (PARTITION BY office ORDER BY month DESC) AS rn
    FROM report_months
) WHERE rn <= 2;

CREATE OR REPLACE TABLE holder_status AS
WITH cur AS (
    SELECT i.*, date_diff('day', i.start_date, (SELECT window_end FROM bounds)) AS tenure_days
    FROM seat_intervals i WHERE i.is_open
), x AS (
    SELECT cur.seat_id, cur.office, cur.user_id, cur.start_date, cur.tenure_days,
           cur.start_file, cur.start_line,
           coalesce(max(c.class) FILTER (WHERE l.rn = 1), 'not_held') AS c1,
           coalesce(max(c.class) FILTER (WHERE l.rn = 2), 'not_held') AS c2,
           max(l.month) FILTER (WHERE l.rn = 1) AS m1,
           max(l.month) FILTER (WHERE l.rn = 2) AS m2
    FROM cur
    LEFT JOIN last_two l ON l.office = cur.office
    LEFT JOIN seat_month_class c
           ON c.seat_id = cur.seat_id AND c.user_id = cur.user_id AND c.month = l.month
    GROUP BY cur.seat_id, cur.office, cur.user_id, cur.start_date, cur.tenure_days, cur.start_file, cur.start_line
), y AS (
    SELECT x.*, (x.m2 < o.ramp_until) AS in_ramp FROM x JOIN office_onboarding o USING (office)
)
SELECT y.*,
       CASE
         WHEN c1 = 'confirmed_inactive' AND c2 = 'confirmed_inactive' AND NOT in_ramp
              AND tenure_days >= (SELECT min_tenure_days FROM params) THEN 'candidate'
         WHEN c1 = 'unknown' OR c2 = 'unknown' THEN 'needs_evidence'
         WHEN 'confirmed_inactive' IN (c1, c2) THEN 'needs_evidence'
         ELSE 'in_use' END AS verdict,
       CASE
         WHEN c1 = 'confirmed_inactive' AND c2 = 'confirmed_inactive' AND NOT in_ramp
              AND tenure_days >= (SELECT min_tenure_days FROM params)
              THEN 'no real use in the last two reported months'
         WHEN c1 = 'unknown' OR c2 = 'unknown' THEN 'usage_missing'
         WHEN 'confirmed_inactive' IN (c1, c2) AND tenure_days < (SELECT min_tenure_days FROM params)
              THEN 'recently_assigned'
         WHEN 'confirmed_inactive' IN (c1, c2) AND in_ramp THEN 'office_still_ramping'
         WHEN 'confirmed_inactive' IN (c1, c2) THEN 'single_month_inactive'
         ELSE '' END AS reason
FROM y;

-- Seats that are billed but have nobody on them right now.
CREATE OR REPLACE TABLE free_seats AS
SELECT s.seat_id, s.office, c.file_name, c.line_no, c.event_date AS last_event_date
FROM seats s
JOIN seat_changes c ON c.seat_id = s.seat_id AND c.next_date IS NULL
WHERE c.holder IS NULL;

CREATE OR REPLACE TABLE office_pool AS
WITH latest AS (SELECT office, max(month) AS m FROM reconciliation GROUP BY office),
inv AS (
    SELECT r.office, r.invoice_qty AS seats_billed, r.unit_cents, r.unattributed_seats, r.source, r.month
    FROM reconciliation r JOIN latest l ON r.office = l.office AND r.month = l.m
), fl AS (SELECT office, count(*) AS n FROM free_seats GROUP BY office),
cd AS (
    SELECT office,
           count(*) FILTER (WHERE verdict = 'candidate') AS candidates,
           count(*) FILTER (WHERE verdict = 'needs_evidence') AS needs_evidence,
           count(*) AS held
    FROM holder_status GROUP BY office
), lu AS (
    SELECT o.office, o.n_active, o.n_inactive
    FROM office_month_usage o JOIN (
        SELECT office, max(month) AS m FROM office_month_usage WHERE report_received GROUP BY office
    ) z ON z.office = o.office AND z.m = o.month
)
SELECT inv.office, inv.seats_billed, inv.unit_cents, inv.source AS invoice_source, inv.month AS invoice_month,
       coalesce(fl.n, 0) AS free_logged,
       greatest(inv.unattributed_seats, 0) AS free_unlogged,
       coalesce(cd.candidates, 0) AS candidates,
       coalesce(cd.needs_evidence, 0) AS needs_evidence,
       coalesce(cd.held, 0) AS held,
       coalesce(fl.n, 0) + greatest(inv.unattributed_seats, 0) + coalesce(cd.candidates, 0) AS pool,
       lu.n_active AS active_now, lu.n_inactive AS inactive_now
FROM inv
LEFT JOIN fl USING (office) LEFT JOIN cd USING (office) LEFT JOIN lu USING (office);
