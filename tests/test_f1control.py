"""Tests for PADDOCK F1 CONTROL. Run: python -m unittest discover -s tests -v"""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from f1control.server import build_service, make_app
from f1control.service import F1Service, downsample, parse_laptime
from f1control.sources import DiskCache, HttpSource, SourceError, build_query


class FakeFetch:
    """Stands in for the network. Counts calls; can raise or return bad data."""

    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, 0

    def __call__(self, url, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return json.dumps(self.payload).encode() if not isinstance(self.payload, bytes) else self.payload


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cache = DiskCache(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_query_keeps_openf1_operators(self):
        q = build_query([("session_key", "=", "9161"), ("date", ">=", "2023-09-16T13:00:00.0")])
        self.assertEqual(q, "?session_key=9161&date>=2023-09-16T13:00:00.0")

    def test_query_rejects_unknown_operator(self):
        with self.assertRaises(ValueError):
            build_query([("a", "!=", "1")])

    def test_miss_then_hit(self):
        fetch = FakeFetch({"ok": 1})
        src = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=fetch)
        first, second = src.get("/x.json"), src.get("/x.json")
        self.assertEqual((first["cache"], second["cache"]), ("miss", "hit"))
        self.assertEqual(fetch.calls, 1)
        self.assertEqual(second["data"], {"ok": 1})

    def test_ttl_expiry_refetches(self):
        fetch = FakeFetch({"ok": 1})
        src = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=fetch)
        src.get("/x.json", ttl=0.01)
        time.sleep(0.05)
        self.assertEqual(src.get("/x.json", ttl=0.01)["cache"], "miss")
        self.assertEqual(fetch.calls, 2)

    def test_rate_limit_error_is_explained(self):
        err = urllib.error.HTTPError("u", 429, "Too Many", {}, None)
        src = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=FakeFetch(error=err))
        with self.assertRaises(SourceError) as ctx:
            src.get("/x.json")
        self.assertIn("rate limit", ctx.exception.message)

    def test_outage_serves_stale_cache_with_warning(self):
        good = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=FakeFetch({"v": 1}))
        good.get("/x.json", ttl=0)
        down = HttpSource("Test", "https://example.invalid", self.cache, 0,
                          fetch=FakeFetch(error=urllib.error.URLError("down")))
        env = down.get("/x.json", ttl=0)
        self.assertEqual(env["cache"], "stale")
        self.assertIn("unreachable", env["warning"])

    def test_bad_json(self):
        src = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=FakeFetch(b"<html>"))
        with self.assertRaises(SourceError):
            src.get("/x.json")


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc, _ = build_service(True, "")

    def test_parse_laptime(self):
        self.assertEqual(parse_laptime("1:32.456"), 92.456)
        self.assertEqual(parse_laptime("58.1"), 58.1)
        self.assertIsNone(parse_laptime("DNF"))
        self.assertIsNone(parse_laptime(None))

    def test_downsample(self):
        self.assertEqual(len(downsample(list(range(1000)), 400)), 400)
        self.assertEqual(downsample([1, 2], 400), [1, 2])

    def test_everything_is_labelled_fixture(self):
        for result in (self.svc.calendar(2024), self.svc.standings(2024), self.svc.results(2024, 1)):
            self.assertEqual(result["meta"]["data_kind"], "fixture")
            self.assertTrue(all("TEST FIXTURE" in s["source"] for s in result["meta"]["sources"]))

    def test_standings_and_results(self):
        st = self.svc.standings(2024)["data"]
        self.assertEqual(st["drivers"][0]["points"], 25.0)
        self.assertEqual(len(st["constructors"]), 3)
        res = self.svc.results(2024, 1)["data"]
        self.assertEqual(len(res["results"]), 6)
        self.assertEqual(res["results"][0]["position"], "1")

    def test_compare(self):
        c = self.svc.compare(2024, 1, "test_alpha", "test_bravo")["data"]
        self.assertEqual(c["drivers"]["test_alpha"]["summary"]["laps"], 20)
        self.assertEqual(len(c["delta_a_minus_b"]), 20)

    def test_strategy_has_stints_and_stops(self):
        s = self.svc.strategy(2024, 1)["data"]
        self.assertEqual(len(s["pit_stops"]), 6)
        self.assertEqual(len(s["stints"]), 12)
        self.assertEqual({x["compound"] for x in s["stints"]}, {"MEDIUM", "HARD", "SOFT"})

    def test_telemetry_lap(self):
        t = self.svc.telemetry(2024, 1, 1, 5)["data"]
        self.assertGreater(t["samples"], 300)
        self.assertTrue(all(0 <= p["throttle"] <= 100 for p in t["points"]))

    def test_old_seasons_explain_missing_openf1(self):
        with self.assertRaises(SourceError):
            self.svc.telemetry(2019, 1, 1, 5)

    def test_historical_label_for_finished_season(self):
        payload = {"MRData": {"total": "0", "RaceTable": {"season": "2021", "Races": []}}}
        d = tempfile.mkdtemp()
        try:
            src = HttpSource("Jolpica-F1", "https://example.invalid", DiskCache(d), 0, fetch=FakeFetch(payload))
            svc = F1Service(src, src, current_year=2026)
            self.assertEqual(svc.calendar(2021)["meta"]["data_kind"], "historical")
            self.assertEqual(svc.calendar(2026)["meta"]["data_kind"], "recent")
        finally:
            shutil.rmtree(d)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc, mode = build_service(True, "")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_app(svc, mode))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_health(self):
        status, _, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["mode"], "fixture")

    def test_results_endpoint_reports_timing(self):
        status, _, body = self.get("/api/results?season=2024&round=1")
        self.assertEqual(status, 200)
        self.assertIn("server_ms", json.loads(body)["meta"])

    def test_bad_input_rejected(self):
        self.assertEqual(self.get("/api/results?season=abc")[0], 400)
        self.assertEqual(self.get("/api/compare?a=Robert';DROP&b=x")[0], 400)

    def test_missing_data_is_502_with_source(self):
        status, _, body = self.get("/api/results?season=2024&round=9")
        self.assertEqual(status, 502)
        self.assertIn("source", json.loads(body))

    def test_unknown_and_traversal(self):
        self.assertEqual(self.get("/api/nope")[0], 404)
        self.assertEqual(self.get("/../f1control/server.py")[0], 404)
        self.assertEqual(self.get("/%2e%2e/f1control/server.py")[0], 404)

    def test_static_page_has_security_headers(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertIn(b"PADDOCK F1 CONTROL", body)


if __name__ == "__main__":
    unittest.main()
