-- Classify each seat-month row: active, confirmed_inactive, unknown, or unassigned.
-- Missing data is never inactivity: no report, no row for the user, or too few days held -> unknown.
CREATE OR REPLACE TABLE report_months AS
SELECT centre, product, month, count(*) AS users_in_report, min(file_name) AS file_name
FROM stg_usage GROUP BY centre, product, month;

CREATE OR REPLACE TABLE user_dept AS
SELECT centre, user_id, arg_max(department, month) AS department
FROM stg_usage GROUP BY centre, user_id;

CREATE OR REPLACE TABLE seat_month_base AS
SELECT p.seat_id, p.centre, p.product, p.month, p.holder AS user_id, p.days, p.alloc_cents,
       u.active_days, u.file_name AS usage_file, u.line_no AS usage_line,
       CASE WHEN p.holder IS NULL THEN 'unassigned'
            WHEN rm.centre IS NULL THEN 'unknown'
            WHEN u.user_id IS NULL THEN 'unknown'
            WHEN u.active_days >= (SELECT active_days_threshold FROM params) THEN 'active'
            WHEN p.days < (SELECT min_days_held FROM params) THEN 'unknown'
            ELSE 'confirmed_inactive' END AS class,
       CASE WHEN p.holder IS NULL THEN 'no holder on those days'
            WHEN rm.centre IS NULL THEN 'usage report not received'
            WHEN u.user_id IS NULL THEN 'user missing from the report'
            WHEN u.active_days >= (SELECT active_days_threshold FROM params) THEN 'enough active days'
            WHEN p.days < (SELECT min_days_held FROM params) THEN 'held too few days to judge'
            ELSE 'report received, too few active days' END AS reason
FROM seat_month_pieces p
LEFT JOIN report_months rm ON rm.centre = p.centre AND rm.product = p.product AND rm.month = p.month
LEFT JOIN stg_usage u ON u.centre = p.centre AND u.product = p.product AND u.month = p.month AND u.user_id = p.holder;

CREATE OR REPLACE TABLE centre_month_usage AS
SELECT o.centre, o.product, mo.month,
       count(c.class) FILTER (WHERE c.class = 'active') AS n_active,
       count(c.class) FILTER (WHERE c.class = 'confirmed_inactive') AS n_inactive,
       count(c.class) FILTER (WHERE c.class = 'unknown') AS n_unknown,
       n_active::DOUBLE / nullif(n_active + n_inactive, 0) AS active_share,
       EXISTS (SELECT 1 FROM report_months r WHERE r.centre = o.centre AND r.product = o.product AND r.month = mo.month) AS report_received
FROM (SELECT DISTINCT centre, product FROM seats) o
CROSS JOIN months mo
LEFT JOIN seat_month_base c ON c.centre = o.centre AND c.product = o.product AND c.month = mo.month
GROUP BY o.centre, o.product, mo.month;

-- When did the centre actually start using the product? First month with a real share of seats active.
CREATE OR REPLACE TABLE centre_onboarding AS
SELECT centre, product,
       min(month) FILTER (WHERE active_share >= (SELECT onboarding_share FROM params)) AS start_month,
       coalesce((min(month) FILTER (WHERE active_share >= (SELECT onboarding_share FROM params))
                 + (SELECT grace_months FROM params) * INTERVAL 1 MONTH)::DATE,
                (SELECT window_end FROM bounds)) AS ramp_until
FROM centre_month_usage GROUP BY centre, product;

-- Months from a user's first seat of a product to the first month they were active on it.
CREATE OR REPLACE TABLE user_lag AS
SELECT i.centre, i.product, i.user_id, min(i.start_date) AS first_assigned,
       (SELECT min(c.month) FROM seat_month_base c
         WHERE c.centre = i.centre AND c.product = i.product AND c.user_id = i.user_id AND c.class = 'active') AS first_active_month
FROM seat_intervals i GROUP BY i.centre, i.product, i.user_id;

CREATE OR REPLACE TABLE centre_lag AS
SELECT centre, product,
       count(*) AS users,
       count(first_active_month) AS users_started,
       median(date_diff('month', date_trunc('month', first_assigned)::DATE, first_active_month)) AS median_lag_months
FROM user_lag GROUP BY centre, product;

CREATE OR REPLACE TABLE seat_month_class AS
SELECT b.*,
       b.month < o.ramp_until AS in_ramp,
       coalesce(b.class = 'confirmed_inactive' AND l.first_active_month > b.month, false) AS starts_later
FROM seat_month_base b
JOIN centre_onboarding o ON o.centre = b.centre AND o.product = b.product
LEFT JOIN user_lag l ON l.centre = b.centre AND l.product = b.product AND l.user_id = b.user_id;

-- Spend by class. Seats the invoice bills but the log never mentions are 'unassigned'.
CREATE OR REPLACE TABLE spend_by_class AS
SELECT centre, product, month, class, sum(alloc_cents)::BIGINT AS cents
FROM seat_month_class GROUP BY centre, product, month, class
UNION ALL
SELECT centre, product, month, 'unassigned', unattributed_cents FROM reconciliation WHERE unattributed_cents <> 0;
