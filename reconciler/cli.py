"""Command line: build, serve, generate, sensitivity."""
from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
from pathlib import Path

from . import pipeline, report
from .config import BUILD_DIR, DB_PATH, DEFAULT_AS_OF, PORT, RAW_DIR, REPORT_PATH
from .generate import generate


def cmd_build(args) -> int:
    if args.fresh and DB_PATH.exists():
        DB_PATH.unlink()
    con = pipeline.connect(DB_PATH)
    stats = pipeline.build_warehouse(con, Path(args.raw), args.as_of)
    html = report.render(con, args.as_of)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(html, encoding="utf-8")
    rec = con.execute("SELECT count(*), sum(invoice_cents), sum(diff_cents) FROM reconciliation").fetchone()
    pool = con.execute("SELECT sum(candidates), sum(needs_evidence), sum(free_logged + free_unlogged) FROM office_pool").fetchone()
    fc = {r[0]: r[1] for r in con.execute("SELECT option, added_cents FROM forecast_options WHERE office = 'ALL'").fetchall()}
    print(f"raw files: {stats['loaded']} loaded, {stats['skipped']} already loaded, {stats['duplicates']} duplicate of an earlier file")
    print(f"reconciled {rec[0]} office-months, invoiced ${rec[1] / 100:,.2f}, difference ${rec[2] / 100:,.2f}")
    print(f"seats: {pool[2]} free, {pool[0]} reassignment candidates, {pool[1]} need more evidence")
    print(f"next quarter new spend: buy ${fc['buy'] / 100:,.2f}, reallocate ${fc['reallocate'] / 100:,.2f}")
    print(f"report: {REPORT_PATH.relative_to(REPORT_PATH.parent.parent)}")
    con.close()
    return 0


def cmd_generate(args) -> int:
    print(generate())
    return 0


def cmd_serve(args) -> int:
    if not REPORT_PATH.exists():
        cmd_build(argparse.Namespace(raw=str(RAW_DIR), as_of=DEFAULT_AS_OF, fresh=False))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html", "/report.html"):
                self.send_error(404)
                return
            body = REPORT_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as srv:
        print(f"serving the report at http://127.0.0.1:{args.port}/  (Ctrl+C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def sensitivity_rows(as_of_values=(DEFAULT_AS_OF, "2026-10-10"), thresholds=(1, 2, 3, 4, 5, 6)):
    out = []
    for as_of in as_of_values:
        for t in thresholds:
            con = pipeline.connect(":memory:")
            pipeline.build_warehouse(con, RAW_DIR, as_of, overrides={"active_days_threshold": t})
            c = dict(con.execute("SELECT office, sum(candidates) FROM office_pool GROUP BY office").fetchall())
            n = con.execute("SELECT sum(needs_evidence) FROM office_pool").fetchone()[0]
            out.append((as_of, t, c.get("LB", 0), c.get("KE", 0), c.get("CO", 0), n))
            con.close()
    return out


def cmd_sensitivity(args) -> int:
    print("as_of       threshold  LB  KE  CO  needs_evidence")
    for r in sensitivity_rows():
        print(f"{r[0]}  {r[1]:>9}  {r[2]:>2}  {r[3]:>2}  {r[4]:>2}  {r[5]:>14}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m reconciler", description="Copilot licence reconciler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="rebuild everything from the raw files and write the HTML report")
    b.add_argument("--as-of", default=DEFAULT_AS_OF, help="decision date; files received later are ignored")
    b.add_argument("--raw", default=str(RAW_DIR))
    b.add_argument("--fresh", action="store_true", help="delete the warehouse first")
    b.set_defaults(fn=cmd_build)
    s = sub.add_parser("serve", help="serve the report")
    s.add_argument("--port", type=int, default=PORT)
    s.set_defaults(fn=cmd_serve)
    g = sub.add_parser("generate", help="rewrite the synthetic raw files (seeded)")
    g.set_defaults(fn=cmd_generate)
    n = sub.add_parser("sensitivity", help="how the candidate list moves with the threshold and the decision date")
    n.set_defaults(fn=cmd_sensitivity)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
