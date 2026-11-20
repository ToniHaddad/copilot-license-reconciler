-- Raw layer: everything as text, plus where it came from. Persistent and append-only.
CREATE TABLE IF NOT EXISTS raw_files (
    file_name VARCHAR PRIMARY KEY, kind VARCHAR, office VARCHAR, period VARCHAR,
    received_date DATE, sha256 VARCHAR, duplicate_of VARCHAR, n_rows INTEGER
);
CREATE TABLE IF NOT EXISTS raw_invoice (
    file_name VARCHAR, line_no INTEGER, raw_line VARCHAR,
    invoice_id VARCHAR, office VARCHAR, period VARCHAR, sku VARCHAR, description VARCHAR,
    quantity VARCHAR, unit_price VARCHAR, amount VARCHAR, currency VARCHAR
);
CREATE TABLE IF NOT EXISTS raw_events (
    file_name VARCHAR, line_no INTEGER, raw_line VARCHAR,
    event_id VARCHAR, event_date VARCHAR, office VARCHAR, seat_id VARCHAR,
    event_type VARCHAR, user_id VARCHAR, from_user_id VARCHAR
);
CREATE TABLE IF NOT EXISTS raw_usage (
    file_name VARCHAR, line_no INTEGER, raw_line VARCHAR,
    office VARCHAR, report_month VARCHAR, user_id VARCHAR,
    active_days VARCHAR, copilot_actions VARCHAR, last_activity_date VARCHAR
);
