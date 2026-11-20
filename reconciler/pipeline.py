"""Small runner: load raw files idempotently, then run the SQL files in order."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import duckdb

from .config import BUILD_DIR, DB_PATH, DEFAULT_AS_OF, FORECAST_MONTHS, PARAMS, RAW_DIR, REQUESTS, SQL_DIR

KIND_TABLE = {
    "invoice": ("raw_invoice", 9),
    "events": ("raw_events", 7),
    "usage": ("raw_usage", 6),
}


def connect(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def run_sql_file(con, path: Path):
    con.execute(path.read_text(encoding="utf-8"))


def init_raw(con):
    run_sql_file(con, SQL_DIR / "01_raw.sql")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_raw(con, raw_dir: Path = RAW_DIR) -> dict:
    """Load every file listed in manifest.csv. Importing a file again changes nothing:
    a file already loaded (same name) is skipped, and a file whose bytes were already
    loaded under another name is recorded as a duplicate and contributes no rows."""
    init_raw(con)
    stats = {"loaded": 0, "skipped": 0, "duplicates": 0}
    with (raw_dir / "manifest.csv").open(newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    for m in manifest:
        name = m["file_name"]
        path = raw_dir / name
        digest = sha256_of(path)
        known = con.execute("SELECT sha256 FROM raw_files WHERE file_name = ?", [name]).fetchone()
        if known:
            if known[0] != digest:
                raise ValueError(f"{name} changed after it was imported; refusing to overwrite history")
            stats["skipped"] += 1
            continue
        original = con.execute("SELECT file_name FROM raw_files WHERE sha256 = ? AND duplicate_of IS NULL", [digest]).fetchone()
        if original:
            con.execute(
                "INSERT INTO raw_files VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                [name, m["kind"], m["office"], m["period"], m["received_date"], digest, original[0]],
            )
            stats["duplicates"] += 1
            continue
        table, ncols = KIND_TABLE[m["kind"]]
        rows = []
        with path.open(newline="", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                if line_no == 1 or not line.strip():
                    continue
                cells = next(csv.reader([line]))
                if len(cells) != ncols:
                    raise ValueError(f"{name}:{line_no} has {len(cells)} columns, expected {ncols}")
                rows.append([name, line_no, line.rstrip("\r\n")] + cells)
        marks = ", ".join(["?"] * (3 + ncols))
        con.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        con.execute(
            "INSERT INTO raw_files VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
            [name, m["kind"], m["office"], m["period"], m["received_date"], digest, len(rows)],
        )
        stats["loaded"] += 1
    return stats


def set_params(con, as_of: str = DEFAULT_AS_OF, requests: dict | None = None, overrides: dict | None = None):
    p = dict(PARAMS)
    p.update(overrides or {})
    con.execute(f"CREATE OR REPLACE TABLE params AS SELECT DATE '{as_of}' AS as_of, {FORECAST_MONTHS} AS forecast_months, "
                + ", ".join(f"{v!r} AS {k}" for k, v in p.items()))
    con.execute("CREATE OR REPLACE TABLE requests (office VARCHAR, seats INTEGER)")
    con.executemany("INSERT INTO requests VALUES (?, ?)", list((requests or REQUESTS).items()))


def run_models(con):
    for path in sorted(SQL_DIR.glob("*.sql")):
        if path.name.startswith("01_"):
            continue
        run_sql_file(con, path)


def build_warehouse(con, raw_dir: Path = RAW_DIR, as_of: str = DEFAULT_AS_OF,
                    requests: dict | None = None, overrides: dict | None = None) -> dict:
    stats = load_raw(con, raw_dir)
    set_params(con, as_of, requests, overrides)
    run_models(con)
    return stats


def table_fingerprint(con, tables: list[str]) -> dict:
    """Order-independent fingerprint of tables, used to show a rebuild changes nothing."""
    out = {}
    for t in tables:
        n, h = con.execute(f"SELECT count(*), coalesce(sum(hash(t)::HUGEINT), 0) FROM {t} t").fetchone()
        out[t] = (n, int(h))
    return out
