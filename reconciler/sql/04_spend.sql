-- Seat-months prorated by day, with the invoiced price split so that every
-- seat-month adds up to exactly one seat's price (cumulative rounding, no lost cents).
CREATE OR REPLACE TABLE seat_month_pieces AS
WITH g AS (
    SELECT seat_id, centre, product, month, holder, count(*)::BIGINT AS days, min(day) AS first_day
    FROM seat_day GROUP BY seat_id, centre, product, month, holder
), price AS (
    SELECT centre, product, month, max(unit_cents) AS unit_cents FROM stg_invoice GROUP BY centre, product, month
), m AS (
    SELECT g.*, mo.dim, p.unit_cents,
           sum(g.days) OVER (PARTITION BY g.seat_id, g.month ORDER BY g.first_day
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)::BIGINT AS cum
    FROM g JOIN months mo ON mo.month = g.month
           JOIN price p ON p.centre = g.centre AND p.product = g.product AND p.month = g.month
)
SELECT seat_id, centre, product, month, holder, days, dim, unit_cents,
       ((unit_cents * cum * 2 + dim) // (2 * dim))
     - ((unit_cents * (cum - days) * 2 + dim) // (2 * dim)) AS alloc_cents
FROM m;

-- One row per product, centre and month. A seat of one product is never counted as a seat of another.
CREATE OR REPLACE TABLE reconciliation AS
WITH inv AS (
    SELECT centre, product, month, sum(qty)::BIGINT AS invoice_qty, sum(amount_cents)::BIGINT AS invoice_cents,
           bool_and(invoice_math_ok) AS math_ok, max(unit_cents) AS unit_cents,
           string_agg(file_name || ':' || line_no, '; ') AS source
    FROM stg_invoice GROUP BY centre, product, month
), pc AS (
    SELECT centre, product, month,
           count(DISTINCT seat_id) AS known_seats,
           sum(alloc_cents)::BIGINT AS attributed_cents,
           coalesce(sum(alloc_cents) FILTER (WHERE holder IS NOT NULL), 0)::BIGINT AS held_cents,
           count(DISTINCT seat_id) FILTER (WHERE holder IS NOT NULL) AS held_seats,
           count(DISTINCT holder) AS naive_users
    FROM seat_month_pieces GROUP BY centre, product, month
)
SELECT inv.centre, inv.product, inv.month, inv.invoice_qty, inv.invoice_cents, inv.unit_cents,
       pc.known_seats,
       inv.invoice_qty - pc.known_seats AS unattributed_seats,
       pc.attributed_cents,
       (inv.invoice_qty - pc.known_seats) * inv.unit_cents AS unattributed_cents,
       pc.attributed_cents + (inv.invoice_qty - pc.known_seats) * inv.unit_cents AS reconciled_cents,
       inv.invoice_cents - (pc.attributed_cents + (inv.invoice_qty - pc.known_seats) * inv.unit_cents) AS diff_cents,
       pc.held_cents,
       pc.held_seats,
       pc.naive_users,
       pc.naive_users - pc.held_seats AS naive_overcount,
       CASE WHEN NOT inv.math_ok THEN 'invoice arithmetic wrong'
            WHEN inv.invoice_qty < pc.known_seats THEN 'invoice has fewer seats than the log'
            ELSE 'ok' END AS status,
       inv.source
FROM inv JOIN pc USING (centre, product, month);
