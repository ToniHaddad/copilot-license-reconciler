-- Classify each seat-month row: active, confirmed_inactive, unknown, or unassigned.
-- Missing data is never inactivity: no report, no row for the user, or too few days held -> unknown.
CREATE OR REPLACE TABLE report_months AS
SELECT office, month, count(*) AS users_in_report, min(file_name) AS file_name
FROM stg_usage GROUP BY office, month;

CREATE OR REPLACE TABLE seat_month_base AS
SELECT p.seat_id, p.office, p.month, p.holder AS user_id, p.days, p.alloc_cents,
       u.active_days, u.file_name AS usage_file, u.line_no AS usage_line,
       CASE WHEN p.holder IS NULL THEN 'unassigned'
            WHEN rm.office IS NULL THEN 'unknown'
            WHEN u.user_id IS NULL THEN 'unknown'
            WHEN u.active_days >= (SELECT active_days_threshold FROM params) THEN 'active'
            WHEN p.days < (SELECT min_days_held FROM params) THEN 'unknown'
            ELSE 'confirmed_inactive' END AS class,
       CASE WHEN p.holder IS NULL THEN 'no holder on those days'
            WHEN rm.office IS NULL THEN 'usage report not received'
            WHEN u.user_id IS NULL THEN 'user missing from the report'
            WHEN u.active_days >= (SELECT active_days_threshold FROM params) THEN 'enough active days'
            WHEN p.days < (SELECT min_days_held FROM params) THEN 'held too few days to judge'
            ELSE 'report received, too few active days' END AS reason
FROM seat_month_pieces p
LEFT JOIN report_months rm ON rm.office = p.office AND rm.month = p.month
LEFT JOIN stg_usage u ON u.office = p.office AND u.month = p.month AND u.user_id = p.holder;

CREATE OR REPLACE TABLE office_month_usage AS
SELECT o.office, mo.month,
       count(c.class) FILTER (WHERE c.class = 'active') AS n_active,
       count(c.class) FILTER (WHERE c.class = 'confirmed_inactive') AS n_inactive,
       count(c.class) FILTER (WHERE c.class = 'unknown') AS n_unknown,
       n_active::DOUBLE / nullif(n_active + n_inactive, 0) AS active_share,
       EXISTS (SELECT 1 FROM report_months r WHERE r.office = o.office AND r.month = mo.month) AS report_received
FROM (SELECT DISTINCT office FROM seats) o
CROSS JOIN months mo
LEFT JOIN seat_month_base c ON c.office = o.office AND c.month = mo.month
GROUP BY o.office, mo.month;

-- When did the office actually start using it? First month with a real share of seats active.
CREATE OR REPLACE TABLE office_onboarding AS
SELECT office,
       min(month) FILTER (WHERE active_share >= (SELECT onboarding_share FROM params)) AS start_month,
       coalesce((min(month) FILTER (WHERE active_share >= (SELECT onboarding_share FROM params))
                 + (SELECT grace_months FROM params) * INTERVAL 1 MONTH)::DATE,
                (SELECT window_end FROM bounds)) AS ramp_until
FROM office_month_usage GROUP BY office;

-- Months from a user's first seat to the first month they were active.
CREATE OR REPLACE TABLE user_lag AS
SELECT i.office, i.user_id, min(i.start_date) AS first_assigned,
       (SELECT min(c.month) FROM seat_month_base c
         WHERE c.office = i.office AND c.user_id = i.user_id AND c.class = 'active') AS first_active_month
FROM seat_intervals i GROUP BY i.office, i.user_id;

CREATE OR REPLACE TABLE office_lag AS
SELECT office,
       count(*) AS users,
       count(first_active_month) AS users_started,
       median(date_diff('month', date_trunc('month', first_assigned)::DATE, first_active_month)) AS median_lag_months
FROM user_lag GROUP BY office;

CREATE OR REPLACE TABLE seat_month_class AS
SELECT b.*,
       b.month < o.ramp_until AS in_ramp,
       coalesce(b.class = 'confirmed_inactive' AND l.first_active_month > b.month, false) AS starts_later
FROM seat_month_base b
JOIN office_onboarding o USING (office)
LEFT JOIN user_lag l ON l.office = b.office AND l.user_id = b.user_id;

-- Spend by class. Seats the invoice bills but the log never mentions are 'unassigned'.
CREATE OR REPLACE TABLE spend_by_class AS
SELECT office, month, class, sum(alloc_cents)::BIGINT AS cents
FROM seat_month_class GROUP BY office, month, class
UNION ALL
SELECT office, month, 'unassigned', unattributed_cents FROM reconciliation WHERE unattributed_cents <> 0;
