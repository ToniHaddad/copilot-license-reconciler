-- Headline numbers per product and centre. Months with no usage report are left out of cost per
-- active user: spend in a month nobody can judge says nothing about use.
CREATE OR REPLACE TABLE centre_cost AS
SELECT o.centre, o.product,
       sum(r.invoice_cents)::BIGINT AS spend_total,
       sum(r.invoice_cents) FILTER (WHERE u.report_received)::BIGINT AS spend_reported,
       sum(u.n_active) FILTER (WHERE u.report_received)::BIGINT AS active_months,
       spend_reported::DOUBLE / nullif(active_months, 0) AS cents_per_active_month,
       sum(r.invoice_cents) FILTER (WHERE u.report_received AND r.month >= o.start_month)::BIGINT AS spend_since_start,
       sum(u.n_active) FILTER (WHERE u.report_received AND r.month >= o.start_month)::BIGINT AS active_since_start,
       spend_since_start::DOUBLE / nullif(active_since_start, 0) AS cents_per_active_since_start,
       sum(u.n_active) FILTER (WHERE u.report_received)::DOUBLE
         / nullif(sum(u.n_active + u.n_inactive) FILTER (WHERE u.report_received), 0) AS active_share_reported,
       sum(u.n_active) FILTER (WHERE u.report_received AND r.month >= o.start_month)::DOUBLE
         / nullif(sum(u.n_active + u.n_inactive) FILTER (WHERE u.report_received AND r.month >= o.start_month), 0) AS active_share_since_start,
       o.start_month
FROM centre_onboarding o
JOIN reconciliation r ON r.centre = o.centre AND r.product = o.product
JOIN centre_month_usage u ON u.centre = r.centre AND u.product = r.product AND u.month = r.month
GROUP BY o.centre, o.product, o.start_month;

-- One row per product: the whole software bill at a glance.
CREATE OR REPLACE TABLE product_summary AS
WITH sp AS (
    SELECT product, sum(invoice_cents)::BIGINT AS spend_total FROM reconciliation GROUP BY product
), pl AS (
    SELECT product, max(unit_cents) AS unit_cents,
           sum(seats_billed)::BIGINT AS seats_billed,
           sum(free_logged + free_unlogged)::BIGINT AS free_seats,
           sum(candidates)::BIGINT AS candidates,
           sum(needs_evidence)::BIGINT AS needs_evidence,
           sum(active_now)::DOUBLE / nullif(sum(active_now + inactive_now), 0) AS active_share_now
    FROM seat_pool GROUP BY product
)
SELECT sp.product, sp.spend_total, pl.unit_cents, pl.seats_billed, pl.free_seats, pl.candidates,
       pl.needs_evidence, pl.active_share_now
FROM sp JOIN pl USING (product);
