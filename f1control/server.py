"""Local web server for PADDOCK F1 CONTROL (standard library only).

Run:  python -m f1control.server            (live public APIs, cached)
      python -m f1control.server --fixtures (offline synthetic test data)
Binds to 127.0.0.1 only, so nothing on the network can reach it.
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import F1Service
from .sources import (JOLPICA_BASE, OPENF1_BASE, OPENMETEO_BASE, DiskCache, FixtureSource, HttpSource, SourceError,
                      utc_now_iso)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")
VERSION = "0.6.3"
log = logging.getLogger("f1control")


class BadRequest(Exception):
    pass


def _int(q: dict, name: str, lo: int, hi: int, default: int | None = None) -> int:
    raw = (q.get(name) or [None])[0]
    if raw is None:
        if default is None:
            raise BadRequest(f"missing '{name}'")
        return default
    if not re.fullmatch(r"\d{1,4}", raw) or not lo <= int(raw) <= hi:
        raise BadRequest(f"'{name}' must be a number from {lo} to {hi}")
    return int(raw)


def _driver(q: dict, name: str) -> str:
    raw = (q.get(name) or [""])[0]
    if not re.fullmatch(r"[a-z0-9_]{2,40}", raw):
        raise BadRequest(f"'{name}' must be a driver id like 'max_verstappen'")
    return raw


def make_app(service: F1Service, mode: str):
    started = time.time()

    def route(path: str, q: dict):
        season = lambda: _int(q, "season", 1950, 2100, service.current_year)  # noqa: E731
        rnd = lambda: _int(q, "round", 1, 30, 1)  # noqa: E731
        if path == "/api/health":
            return {"status": "ok", "version": VERSION, "mode": mode, "uptime_s": round(time.time() - started),
                    "time": utc_now_iso(),
                    "sources": {"jolpica": service.jolpica.stats, "openf1": service.openf1.stats}}
        if path == "/api/calendar":
            return service.calendar(season())
        if path == "/api/standings":
            return service.standings(season())
        if path == "/api/results":
            return service.results(season(), rnd())
        if path == "/api/compare":
            return service.compare(season(), rnd(), _driver(q, "a"), _driver(q, "b"))
        if path == "/api/strategy":
            return service.strategy(season(), rnd())
        if path in ("/api/replay", "/api/positions"):
            name = (q.get("session") or ["Qualifying"])[0]
            if name not in ("Qualifying", "Sprint Qualifying", "Practice 1", "Practice 2", "Practice 3", "Race", "Sprint"):
                raise BadRequest("unknown session name")
            if path == "/api/positions":
                return service.positions(season(), rnd(), name, _int(q, "from", 0, 20000), _int(q, "to", 1, 20000))
            return service.replay(season(), rnd(), name)
        if path == "/api/weekend":
            return service.weekend(season(), rnd())
        if path == "/api/weather":
            return service.weather(season(), rnd())
        if path == "/api/points":
            return service.points_tracker(season())
        if path == "/api/trackmap":
            return service.track_map(season(), rnd())
        if path == "/api/racecontrol":
            return service.race_control(season(), rnd())
        if path == "/api/projection":
            alloc = {c: _int(q, c.lower(), 0, 8, d) for c, d in (("SOFT", 2), ("MEDIUM", 2), ("HARD", 2))}
            pit = _int(q, "pit_loss", 10, 60, 0) or None
            return service.projection(season(), rnd(), alloc, float(pit) if pit else None)
        if path == "/api/telemetry":
            return service.telemetry(season(), rnd(), _int(q, "driver", 1, 99), _int(q, "lap", 1, 100))
        return None

    class Handler(BaseHTTPRequestHandler):
        server_version = "PaddockF1/" + VERSION

        def log_message(self, fmt, *args):  # route through logging instead of stderr spam
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, json.dumps(obj).encode(), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path.startswith("/api/"):
                t0 = time.perf_counter()
                try:
                    result = route(url.path, parse_qs(url.query))
                    if result is None:
                        return self._json(404, {"error": "unknown endpoint"})
                    if isinstance(result, dict) and "meta" in result:
                        result["meta"]["server_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                    return self._json(200, result)
                except BadRequest as exc:
                    return self._json(400, {"error": str(exc)})
                except SourceError as exc:
                    return self._json(502, {"error": exc.message, "source": exc.source})
                except Exception:  # never leak tracebacks to the browser
                    log.exception("unexpected error on %s", url.path)
                    return self._json(500, {"error": "internal error; see server log"})
            name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            full = os.path.realpath(os.path.join(STATIC, name))
            if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
                return self._json(404, {"error": "not found"})
            with open(full, "rb") as fh:
                body = fh.read()
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, body, ctype)

    return Handler


def build_service(fixtures: bool, cache_dir: str) -> tuple[F1Service, str]:
    if fixtures:
        with open(os.path.join(ROOT, "tests", "fixtures", "synthetic.json"), encoding="utf-8") as fh:
            table = json.load(fh)
        return F1Service(FixtureSource("Jolpica-F1", table["jolpica"]), FixtureSource("OpenF1", table["openf1"]),
                         current_year=2026, weather=FixtureSource("Open-Meteo", table["openmeteo"]),
                         today="2024-03-01"), "fixture"
    cache = DiskCache(cache_dir)
    # Jolpica allows 4 req/s burst; we stay well under. OpenF1 free tier is also limited.
    return F1Service(HttpSource("Jolpica-F1", JOLPICA_BASE, cache, 0.3),
                     HttpSource("OpenF1", OPENF1_BASE, cache, 0.6),
                     weather=HttpSource("Open-Meteo", OPENMETEO_BASE, cache, 0.3)), "live"


def main(argv=None):
    ap = argparse.ArgumentParser(description="PADDOCK F1 CONTROL local server")
    ap.add_argument("--port", type=int, default=8301)
    ap.add_argument("--fixtures", action="store_true", help="use offline synthetic test data")
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, ".cache"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service, mode = build_service(args.fixtures, args.cache_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_app(service, mode))
    log.info("PADDOCK F1 CONTROL %s (%s mode) on http://127.0.0.1:%d  - Ctrl+C to stop",
             VERSION, mode, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    main()
