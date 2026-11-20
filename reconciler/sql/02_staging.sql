-- Staging: typed, trimmed, de-duplicated, and limited to files received by the as-of date.
CREATE OR REPLACE TABLE stg_files AS
SELECT f.*, f.received_date <= (SELECT as_of FROM params) AS in_scope
FROM raw_files f;

CREATE OR REPLACE TABLE stg_invoice AS
SELECT i.file_name, i.line_no, i.raw_line, i.invoice_id,
       upper(trim(i.office)) AS office,
       (i.period || '-01')::DATE AS month,
       i.sku,
       i.quantity::INTEGER AS qty,
       round(i.unit_price::DECIMAL(12,2) * 100)::BIGINT AS unit_cents,
       round(i.amount::DECIMAL(12,2) * 100)::BIGINT AS amount_cents,
       i.quantity::INTEGER * round(i.unit_price::DECIMAL(12,2) * 100)::BIGINT
           = round(i.amount::DECIMAL(12,2) * 100)::BIGINT AS invoice_math_ok
FROM raw_invoice i JOIN stg_files f USING (file_name)
WHERE f.in_scope AND f.duplicate_of IS NULL
QUALIFY row_number() OVER (PARTITION BY i.invoice_id, i.sku
                           ORDER BY f.received_date DESC, i.file_name, i.line_no) = 1;

CREATE OR REPLACE TABLE stg_events AS
SELECT e.file_name, e.line_no, e.raw_line, e.event_id,
       e.event_date::DATE AS event_date,
       upper(trim(e.office)) AS office,
       trim(e.seat_id) AS seat_id,
       lower(trim(e.event_type)) AS event_type,
       upper(trim(e.user_id)) AS user_id,
       nullif(upper(trim(e.from_user_id)), '') AS from_user_id
FROM raw_events e JOIN stg_files f USING (file_name)
WHERE f.in_scope AND f.duplicate_of IS NULL
  AND e.event_date::DATE <= (SELECT as_of FROM params)
QUALIFY row_number() OVER (PARTITION BY e.event_id
                           ORDER BY f.received_date DESC, e.file_name, e.line_no) = 1;

CREATE OR REPLACE TABLE stg_usage AS
SELECT u.file_name, u.line_no, u.raw_line,
       upper(trim(u.office)) AS office,
       (trim(u.report_month) || '-01')::DATE AS month,
       upper(trim(u.user_id)) AS user_id,
       u.active_days::INTEGER AS active_days,
       u.copilot_actions::INTEGER AS actions,
       nullif(trim(u.last_activity_date), '')::DATE AS last_activity_date
FROM raw_usage u JOIN stg_files f USING (file_name)
WHERE f.in_scope AND f.duplicate_of IS NULL
QUALIFY row_number() OVER (PARTITION BY upper(trim(u.office)), trim(u.report_month), upper(trim(u.user_id))
                           ORDER BY u.file_name, u.line_no) = 1;

CREATE OR REPLACE TABLE bounds AS
SELECT min(month) AS window_start, (max(month) + INTERVAL 1 MONTH)::DATE AS window_end
FROM stg_invoice;

CREATE OR REPLACE TABLE months AS
SELECT t.m::DATE AS month,
       date_diff('day', t.m::DATE, (t.m + INTERVAL 1 MONTH)::DATE) AS dim
FROM bounds, generate_series(window_start, window_end - 1, INTERVAL 1 MONTH) t(m);
