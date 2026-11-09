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
        src = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=FakeFetch(error=err), sleep=lambda s: None)
        with self.assertRaises(SourceError) as ctx:
            src.get("/x.json")
        self.assertIn("rate limit", ctx.exception.message)

    def test_rate_limit_is_retried_then_succeeds(self):
        calls = {"n": 0}

        def flaky(url, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(url, 429, "Too Many", {"Retry-After": "1"}, None)
            return b'{"ok": 2}'
        waits = []
        src = HttpSource("Test", "https://example.invalid", self.cache, 0, fetch=flaky, sleep=waits.append)
        self.assertEqual(src.get("/r.json")["data"], {"ok": 2})
        self.assertEqual(waits, [1.0])

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


class StrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc, _ = build_service(True, "")
        cls.d = cls.svc.projection(2024, 1, {"SOFT": 2, "MEDIUM": 2, "HARD": 2})["data"]

    def test_recovers_known_wear_rates(self):
        truth = {"SOFT": 0.12, "MEDIUM": 0.07, "HARD": 0.04}  # built into the synthetic data
        for comp, wear in truth.items():
            self.assertAlmostEqual(self.d["compounds"][comp]["deg"], wear, delta=0.015, msg=comp)

    def test_compound_order_soft_fastest_hard_slowest(self):
        off = {c: m["offset"] for c, m in self.d["compounds"].items()}
        self.assertLess(off["SOFT"], off["MEDIUM"])
        self.assertLess(off["MEDIUM"], off["HARD"])

    def test_plans_are_legal_and_ranked(self):
        plans = self.d["plans"]
        self.assertTrue(plans)
        self.assertEqual(plans[0]["delta"], 0)
        for p in plans:
            self.assertGreaterEqual(len(set(p["sequence"])), 2)  # two-compound rule
            self.assertEqual(sum(s["laps"] for s in p["stints"]), self.d["race_laps"])
        self.assertEqual([p["total"] for p in plans], sorted(p["total"] for p in plans))

    def test_allocation_limits_plans(self):
        d = self.svc.projection(2024, 1, {"SOFT": 0, "MEDIUM": 1, "HARD": 1})["data"]
        self.assertTrue(all(sorted(p["sequence"]) == ["HARD", "MEDIUM"] for p in d["plans"]))
        none = self.svc.projection(2024, 1, {"SOFT": 0, "MEDIUM": 2, "HARD": 0})["data"]
        self.assertEqual(none["plans"], [])

    def test_validation_against_real_winner(self):
        v = self.d["validation"]
        self.assertIsNotNone(v)
        self.assertLess(abs(v["error_pct"]), 3)
        self.assertIn("MODEL PROJECTION", self.d["label"])

    def test_results_have_team_colours(self):
        rows = self.svc.results(2024, 1)["data"]["results"]
        self.assertTrue(all(r["team_colour"] and r["team_colour"].startswith("#") for r in rows))


class TrackAndPointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc, _ = build_service(True, "")

    def test_track_map_is_normalised_closed_shape(self):
        d = self.svc.track_map(2024, 1)["data"]
        xs = [p[0] for p in d["points"]]
        ys = [p[1] for p in d["points"]]
        self.assertGreater(len(d["points"]), 100)
        self.assertAlmostEqual(max(max(xs), max(ys)), 100, delta=0.5)
        self.assertGreaterEqual(min(xs + ys), 0)

    def test_future_race_uses_earlier_race_at_same_circuit(self):
        r = self.svc.track_map(2024, 3)
        self.assertIn("traced from", r["meta"]["notes"][0])

    def test_track_status_from_race_control(self):
        by = self.svc.race_control(2024, 1)["data"]["by_lap"]
        self.assertEqual(by[5:7], ["SC", "SC"])
        self.assertEqual(by[11], "GREEN")  # sector yellow does not change track status
        self.assertEqual(by[-1], "CHEQUERED")

    def test_points_tracker(self):
        d = self.svc.points_tracker(2024)["data"]
        self.assertEqual(d["rounds_done"], 1)
        self.assertEqual(d["max_points_left"], 50)  # 2 races left x 25
        self.assertTrue(d["table"][0]["can_still_win"])
        self.assertEqual(d["series"][0]["points"], [[1, 25.0]])


class WeekendTests(unittest.TestCase):
    def setUp(self):
        self.svc, _ = build_service(True, "")

    def test_practice_bests_and_qualifying(self):
        d = self.svc.weekend(2024, 1)["data"]
        p1 = next(x for x in d["sessions"] if x["name"] == "Practice 1")
        self.assertEqual(len(p1["best"]), 6)
        self.assertEqual(p1["best"][0]["gap"], 0.0)
        self.assertTrue(all(a["time"] <= b["time"] for a, b in zip(p1["best"], p1["best"][1:])))
        self.assertEqual(d["qualifying"][0]["q3"], "1:30.800")
        self.assertIsNone(d["qualifying"][-1]["q2"])

    def test_forecast_before_race(self):
        r = self.svc.weather(2024, 1)  # fixture 'today' is the day before the race
        self.assertEqual(len(r["data"]["forecast"]["temp_c"]), 72)
        self.assertIn("Open-Meteo", r["data"]["forecast"]["credit"])

    def test_measured_after_race_and_too_early(self):
        self.svc.today = "2024-03-05"
        r = self.svc.weather(2024, 1)
        self.assertIsNone(r["data"]["forecast"])
        self.assertFalse(r["data"]["measured"]["rain"])
        self.svc.today = "2024-01-01"
        self.assertIn("16 days", self.svc.weather(2024, 1)["meta"]["notes"][0])


class ReplayTests(unittest.TestCase):
    def test_qualifying_replay_timeline(self):
        svc, _ = build_service(True, "")
        d = svc.replay(2024, 1, "Qualifying")["data"]
        self.assertIn("SIMULATION", d["label"])
        self.assertEqual(len(d["laps"]), 18)  # out-laps excluded
        self.assertEqual([x["t"] for x in d["laps"]], sorted(x["t"] for x in d["laps"]))
        sts = [(e["t"], e["status"]) for e in d["status"]]
        self.assertIn((1900.0, "RED"), sts)
        self.assertEqual(sts[-1], (3600.0, "CHEQUERED"))

    def test_car_positions_use_track_map_coordinates(self):
        svc, _ = build_service(True, "")
        d = svc.positions(2024, 1, "Qualifying", 300, 420)["data"]
        self.assertEqual(sorted(d["cars"]), ["1", "2", "3", "4", "5"])  # car 6 starts its run later
        pts = d["cars"]["1"]
        self.assertEqual(len(pts), 120)  # one per second
        self.assertTrue(all(-1 <= x <= 101 and -1 <= y <= 101 for _, x, y in pts))
        with self.assertRaises(SourceError):
            svc.positions(2024, 1, "Qualifying", 0, 500)  # window too long

    def test_replay_missing_session(self):
        svc, _ = build_service(True, "")
        with self.assertRaises(SourceError):
            svc.replay(2024, 1, "Sprint Qualifying")


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

    def test_projection_endpoint(self):
        status, _, body = self.get("/api/projection?season=2024&round=1&soft=2&medium=2&hard=2&pit_loss=21")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["data"]["pit_loss"], 21.0)
        self.assertEqual(self.get("/api/projection?season=2024&round=1&soft=99")[0], 400)

    def test_new_endpoints(self):
        self.assertEqual(self.get("/api/replay?season=2024&round=1&session=Hacker")[0], 400)
        for path in ("/api/positions?season=2024&round=1&session=Qualifying&from=300&to=360",
                     "/api/replay?season=2024&round=1&session=Qualifying", "/api/weekend?season=2024&round=1", "/api/weather?season=2024&round=1", "/api/points?season=2024", "/api/trackmap?season=2024&round=1", "/api/racecontrol?season=2024&round=1"):
            self.assertEqual(self.get(path)[0], 200, path)

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
        self.assertIn(b"<title>PADDOCK F1 Control</title>", body)


if __name__ == "__main__":
    unittest.main()
