-- Next-quarter forecast, two options. Every assumption is a row in forecast_assumptions.
CREATE OR REPLACE TABLE forecast_assumptions AS
WITH r AS (
    SELECT sum(active_now)::DOUBLE / nullif(sum(active_now + inactive_now), 0) AS rate FROM office_pool
)
SELECT 'activation_rate' AS key, round(r.rate, 3)::VARCHAR AS value,
       'Share of known seat-holders who are active, latest reported month of each office. Applied to every seat given to a requester.' AS note
FROM r
UNION ALL SELECT 'months', (SELECT forecast_months FROM params)::VARCHAR,
       'Length of the forecast quarter.'
UNION ALL SELECT 'prices', 'unchanged', 'Each office keeps the unit price on its latest invoice.'
UNION ALL SELECT 'reallocation_date', 'first day of the quarter',
       'Candidate and free seats move on day 1, so the full quarter benefits. Evidence-needed seats are not moved.'
UNION ALL SELECT 'baseline', 'latest invoiced seats x price',
       'Both options start from what is billed today; only the difference is shown as new spend.'
UNION ALL SELECT 'active_users', 'same in both options',
       'Both options serve the same requests, so the active-user forecast is identical and only cost differs.';

CREATE OR REPLACE TABLE realloc AS
WITH a AS (
    SELECT p.office, q.seats AS req, p.pool,
           least(q.seats, p.pool) AS own,
           q.seats - least(q.seats, p.pool) AS rem,
           p.pool - least(q.seats, p.pool) AS spare
    FROM office_pool p JOIN requests q USING (office)
), b AS (
    SELECT *, (SELECT sum(spare) FROM a) AS leftover,
           coalesce(sum(rem) OVER (ORDER BY office ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_rem
    FROM a
), c AS (
    SELECT *, least(rem, greatest(0, leftover - prior_rem)) AS cross_filled FROM b
)
SELECT office, req, pool, own AS from_own_pool, cross_filled AS from_other_offices,
       req - own - cross_filled AS to_buy
FROM c;

CREATE OR REPLACE TABLE forecast_options AS
WITH base AS (
    SELECT p.office, p.seats_billed, p.unit_cents, p.active_now,
           (SELECT forecast_months FROM params) AS months,
           (SELECT value::DOUBLE FROM forecast_assumptions WHERE key = 'activation_rate') AS rate,
           r.req, r.from_own_pool + r.from_other_offices AS moved, r.to_buy
    FROM office_pool p JOIN realloc r USING (office)
), opt AS (
    SELECT 'buy' AS option, office, req AS bought, 0 AS reallocated, seats_billed, unit_cents, months,
           active_now + req * rate AS active_users, req AS served FROM base
    UNION ALL
    SELECT 'reallocate', office, to_buy, moved, seats_billed, unit_cents, months,
           active_now + req * rate, req FROM base
), per AS (
    SELECT option, office, bought, reallocated, served,
           seats_billed * unit_cents * months AS baseline_cents,
           bought * unit_cents * months AS added_cents,
           active_users, months
    FROM opt
)
SELECT option, office, bought, reallocated, served, baseline_cents, added_cents,
       baseline_cents + added_cents AS spend_cents, active_users,
       (baseline_cents + added_cents) / months / active_users AS cents_per_active_user_month
FROM per
UNION ALL
SELECT option, 'ALL', sum(bought), sum(reallocated), sum(served), sum(baseline_cents), sum(added_cents),
       sum(baseline_cents + added_cents), sum(active_users),
       sum(baseline_cents + added_cents) / max(months) / sum(active_users)
FROM per GROUP BY option;
