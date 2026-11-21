-- Assignment history as dated intervals [start_date, end_date). Events are never overwritten;
-- each event only decides who holds the seat from its date until the seat's next event.
-- A seat belongs to one product and one centre. Seat ids are never shared between products.
CREATE OR REPLACE TABLE seat_changes AS
SELECT *,
       CASE WHEN event_type = 'unassign' THEN NULL ELSE user_id END AS holder,
       lead(event_date) OVER w AS next_date,
       lead(file_name) OVER w AS next_file,
       lead(line_no)   OVER w AS next_line
FROM stg_events
WINDOW w AS (PARTITION BY seat_id ORDER BY event_date, event_id);

CREATE OR REPLACE TABLE seat_intervals AS
SELECT c.seat_id, c.centre, c.product, c.holder AS user_id,
       c.event_date AS start_date,
       coalesce(c.next_date, b.window_end) AS end_date,
       c.next_date IS NULL AS is_open,
       c.event_type AS start_event,
       c.file_name AS start_file, c.line_no AS start_line,
       c.next_file AS end_file, c.next_line AS end_line
FROM seat_changes c, bounds b
WHERE c.holder IS NOT NULL
  AND coalesce(c.next_date, b.window_end) > c.event_date;

-- A seat exists (and is billed) from the month of its first event.
CREATE OR REPLACE TABLE seats AS
SELECT seat_id, centre, product, min(event_date) AS first_event,
       date_trunc('month', min(event_date))::DATE AS first_month
FROM stg_events GROUP BY seat_id, centre, product;

-- One row per seat per day: the proration base.
CREATE OR REPLACE TABLE seat_day AS
SELECT s.seat_id, s.centre, s.product, t.d::DATE AS day,
       date_trunc('month', t.d)::DATE AS month,
       i.user_id AS holder
FROM seats s
CROSS JOIN bounds b
CROSS JOIN generate_series(b.window_start, b.window_end - 1, INTERVAL 1 DAY) t(d)
LEFT JOIN seat_intervals i
       ON i.seat_id = s.seat_id AND t.d::DATE >= i.start_date AND t.d::DATE < i.end_date
WHERE date_trunc('month', t.d)::DATE >= s.first_month;
