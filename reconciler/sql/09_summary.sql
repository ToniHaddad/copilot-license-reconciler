-- Headline numbers per office. Months with no usage report are left out of cost per active user:
-- spend in a month nobody can judge says nothing about use.
CREATE OR REPLACE TABLE office_cost AS
SELECT o.office,
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
FROM office_onboarding o
JOIN reconciliation r ON r.office = o.office
JOIN office_month_usage u ON u.office = r.office AND u.month = r.month
GROUP BY o.office, o.start_month;
