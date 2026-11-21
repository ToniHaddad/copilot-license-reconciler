-- Reassignment candidates versus seats that need more evidence, per product and centre.
-- The two latest months for which the centre's report was actually received are the evidence window.
CREATE OR REPLACE TABLE last_two AS
SELECT centre, product, month, rn FROM (
    SELECT centre, product, month,
           row_number() OVER (PARTITION BY centre, product ORDER BY month DESC) AS rn
    FROM report_months
) WHERE rn <= 2;

CREATE OR REPLACE TABLE holder_status AS
WITH cur AS (
    SELECT i.*, date_diff('day', i.start_date, (SELECT window_end FROM bounds)) AS tenure_days
    FROM seat_intervals i WHERE i.is_open
), x AS (
    SELECT cur.seat_id, cur.centre, cur.product, cur.user_id, cur.start_date, cur.tenure_days,
           cur.start_file, cur.start_line,
           coalesce(max(c.class) FILTER (WHERE l.rn = 1), 'not_held') AS c1,
           coalesce(max(c.class) FILTER (WHERE l.rn = 2), 'not_held') AS c2,
           max(l.month) FILTER (WHERE l.rn = 1) AS m1,
           max(l.month) FILTER (WHERE l.rn = 2) AS m2
    FROM cur
    LEFT JOIN last_two l ON l.centre = cur.centre AND l.product = cur.product
    LEFT JOIN seat_month_class c
           ON c.seat_id = cur.seat_id AND c.user_id = cur.user_id AND c.month = l.month
    GROUP BY cur.seat_id, cur.centre, cur.product, cur.user_id, cur.start_date, cur.tenure_days, cur.start_file, cur.start_line
), y AS (
    SELECT x.*, (x.m2 < o.ramp_until) AS in_ramp, d.department
    FROM x JOIN centre_onboarding o ON o.centre = x.centre AND o.product = x.product
    LEFT JOIN user_dept d ON d.centre = x.centre AND d.user_id = x.user_id
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
         WHEN 'confirmed_inactive' IN (c1, c2) AND in_ramp THEN 'centre_still_ramping'
         WHEN 'confirmed_inactive' IN (c1, c2) THEN 'single_month_inactive'
         ELSE '' END AS reason
FROM y;

-- Seats that are billed but have nobody on them right now.
CREATE OR REPLACE TABLE free_seats AS
SELECT s.seat_id, s.centre, s.product, c.file_name, c.line_no, c.event_date AS last_event_date
FROM seats s
JOIN seat_changes c ON c.seat_id = s.seat_id AND c.next_date IS NULL
WHERE c.holder IS NULL;

CREATE OR REPLACE TABLE seat_pool AS
WITH latest AS (SELECT centre, product, max(month) AS m FROM reconciliation GROUP BY centre, product),
inv AS (
    SELECT r.centre, r.product, r.invoice_qty AS seats_billed, r.unit_cents, r.unattributed_seats, r.source, r.month
    FROM reconciliation r JOIN latest l ON r.centre = l.centre AND r.product = l.product AND r.month = l.m
), fl AS (SELECT centre, product, count(*) AS n FROM free_seats GROUP BY centre, product),
cd AS (
    SELECT centre, product,
           count(*) FILTER (WHERE verdict = 'candidate') AS candidates,
           count(*) FILTER (WHERE verdict = 'needs_evidence') AS needs_evidence,
           count(*) AS held
    FROM holder_status GROUP BY centre, product
), lu AS (
    SELECT o.centre, o.product, o.n_active, o.n_inactive
    FROM centre_month_usage o JOIN (
        SELECT centre, product, max(month) AS m FROM centre_month_usage WHERE report_received GROUP BY centre, product
    ) z ON z.centre = o.centre AND z.product = o.product AND z.m = o.month
)
SELECT inv.centre, inv.product, inv.seats_billed, inv.unit_cents, inv.source AS invoice_source, inv.month AS invoice_month,
       coalesce(fl.n, 0) AS free_logged,
       greatest(inv.unattributed_seats, 0) AS free_unlogged,
       coalesce(cd.candidates, 0) AS candidates,
       coalesce(cd.needs_evidence, 0) AS needs_evidence,
       coalesce(cd.held, 0) AS held,
       coalesce(fl.n, 0) + greatest(inv.unattributed_seats, 0) + coalesce(cd.candidates, 0) AS pool,
       coalesce(lu.n_active, 0) AS active_now, coalesce(lu.n_inactive, 0) AS inactive_now
FROM inv
LEFT JOIN fl USING (centre, product) LEFT JOIN cd USING (centre, product) LEFT JOIN lu USING (centre, product);
