"""Turns raw Jolpica / OpenF1 responses into small, UI-ready structures."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from .sources import SourceError, utc_now_iso

OPENF1_FIRST_SEASON = 2023  # OpenF1 historical coverage starts with the 2023 season


def parse_laptime(text: str | None) -> float | None:
    """'1:32.456' -> 92.456 seconds; '58.1' -> 58.1; bad input -> None."""
    if not text:
        return None
    try:
        if ":" in text:
            minutes, seconds = text.split(":", 1)
            return round(int(minutes) * 60 + float(seconds), 3)
        return round(float(text), 3)
    except ValueError:
        return None


def downsample(rows: list, limit: int = 400) -> list:
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[int(i * step)] for i in range(limit)]


class F1Service:
    def __init__(self, jolpica, openf1, current_year: int | None = None):
        self.jolpica = jolpica
        self.openf1 = openf1
        self.current_year = current_year or datetime.now(timezone.utc).year

    # ---- helpers -------------------------------------------------------
    def _ttl(self, season: int):
        return None if season < self.current_year else 3600  # finished seasons never change

    def _kind(self, season: int, envelopes: list) -> str:
        if any(e.get("cache") == "fixture" for e in envelopes):
            return "fixture"
        return "historical" if season < self.current_year else "recent"

    def _wrap(self, season: int, envelopes: list, data, notes: list | None = None) -> dict:
        meta_sources = [{k: e.get(k) for k in ("source", "url", "fetched_at", "cache", "warning") if e.get(k)}
                        for e in envelopes]
        return {"meta": {"data_kind": self._kind(season, envelopes), "generated_at": utc_now_iso(),
                         "sources": meta_sources, "notes": notes or []},
                "data": data}

    def _jolpica(self, season: int, path: str, params=None) -> dict:
        return self.jolpica.get(path, params, ttl=self._ttl(season))

    def _jolpica_all(self, season: int, path: str, list_key: str) -> tuple[list, list]:
        """Follow Jolpica pagination (limit/offset/total); returns (races, envelopes)."""
        envelopes, races, offset, limit = [], [], 0, 100
        while True:
            env = self._jolpica(season, path, [("limit", "=", str(limit)), ("offset", "=", str(offset))])
            envelopes.append(env)
            mr = env["data"]["MRData"]
            page = mr["RaceTable"]["Races"]
            for race in page:
                if races and races[-1]["round"] == race["round"]:
                    races[-1][list_key].extend(race.get(list_key, []))
                else:
                    races.append(race)
            total = int(mr.get("total", 0))
            offset += limit
            if offset >= total or offset > 5000:
                return races, envelopes

    # ---- Jolpica: schedule, standings, results --------------------------
    def calendar(self, season: int) -> dict:
        env = self._jolpica(season, f"/{season}.json")
        races = [{"round": int(r["round"]), "name": r["raceName"],
                  "circuit": r["Circuit"]["circuitName"],
                  "locality": r["Circuit"]["Location"].get("locality"),
                  "country": r["Circuit"]["Location"].get("country"),
                  "date": r["date"], "time": r.get("time")}
                 for r in env["data"]["MRData"]["RaceTable"]["Races"]]
        return self._wrap(season, [env], {"season": season, "races": races})

    def standings(self, season: int) -> dict:
        d_env = self._jolpica(season, f"/{season}/driverStandings.json")
        c_env = self._jolpica(season, f"/{season}/constructorStandings.json")
        d_lists = d_env["data"]["MRData"]["StandingsTable"]["StandingsLists"]
        c_lists = c_env["data"]["MRData"]["StandingsTable"]["StandingsLists"]
        drivers = [{"position": int(s.get("position") or 0), "driver_id": s["Driver"]["driverId"],
                    "code": s["Driver"].get("code"),
                    "name": f'{s["Driver"]["givenName"]} {s["Driver"]["familyName"]}',
                    "team": (s.get("Constructors") or [{}])[-1].get("name"),
                    "points": float(s["points"]), "wins": int(s["wins"])}
                   for s in (d_lists[0]["DriverStandings"] if d_lists else [])]
        teams = [{"position": int(s.get("position") or 0), "team": s["Constructor"]["name"],
                  "points": float(s["points"]), "wins": int(s["wins"])}
                 for s in (c_lists[0]["ConstructorStandings"] if c_lists else [])]
        after = d_lists[0].get("round") if d_lists else None
        return self._wrap(season, [d_env, c_env],
                          {"season": season, "after_round": after, "drivers": drivers, "constructors": teams})

    def _race_results(self, season: int, rnd: int):
        env = self._jolpica(season, f"/{season}/{rnd}/results.json")
        races = env["data"]["MRData"]["RaceTable"]["Races"]
        if not races:
            raise SourceError("Jolpica-F1", f"no results for {season} round {rnd}", 404)
        return races[0], env

    def results(self, season: int, rnd: int) -> dict:
        race, env = self._race_results(season, rnd)
        rows = []
        for r in race["Results"]:
            fl = r.get("FastestLap") or {}
            rows.append({"position": r.get("positionText"), "number": r.get("number"),
                         "driver_id": r["Driver"]["driverId"], "code": r["Driver"].get("code"),
                         "name": f'{r["Driver"]["givenName"]} {r["Driver"]["familyName"]}',
                         "team": r["Constructor"]["name"], "grid": int(r.get("grid") or 0),
                         "laps": int(r.get("laps") or 0), "status": r.get("status"),
                         "time": (r.get("Time") or {}).get("time"), "points": float(r.get("points") or 0),
                         "fastest_lap": (fl.get("Time") or {}).get("time"),
                         "fastest_lap_rank": fl.get("rank")})
        return self._wrap(season, [env], {"season": season, "round": rnd, "race": race["raceName"],
                                          "date": race["date"], "circuit": race["Circuit"]["circuitName"],
                                          "results": rows})

    # ---- Lap comparison --------------------------------------------------
    def _laps(self, season: int, rnd: int, driver_id: str):
        races, envs = self._jolpica_all(season, f"/{season}/{rnd}/drivers/{driver_id}/laps.json", "Laps")
        laps = []
        for race in races:
            for lap in race.get("Laps", []):
                for t in lap.get("Timings", []):
                    laps.append({"lap": int(lap["number"]), "position": int(t.get("position") or 0),
                                 "time": parse_laptime(t.get("time"))})
        laps.sort(key=lambda x: x["lap"])
        return laps, envs

    @staticmethod
    def _summary(laps: list) -> dict:
        times = [x["time"] for x in laps if x["time"]]
        if not times:
            return {"laps": 0, "best": None, "median": None}
        best = min(times)
        return {"laps": len(times), "best": best,
                "best_lap": next(x["lap"] for x in laps if x["time"] == best),
                "median": round(statistics.median(times), 3)}

    def compare(self, season: int, rnd: int, a: str, b: str) -> dict:
        laps_a, env_a = self._laps(season, rnd, a)
        laps_b, env_b = self._laps(season, rnd, b)
        by_b = {x["lap"]: x["time"] for x in laps_b}
        delta = [{"lap": x["lap"], "delta": round(x["time"] - by_b[x["lap"]], 3)}
                 for x in laps_a if x["time"] and by_b.get(x["lap"])]
        notes = [] if laps_a and laps_b else ["One driver has no lap data for this race."]
        return self._wrap(season, env_a + env_b, {
            "season": season, "round": rnd,
            "drivers": {a: {"laps": laps_a, "summary": self._summary(laps_a)},
                        b: {"laps": laps_b, "summary": self._summary(laps_b)}},
            "delta_a_minus_b": delta}, notes)

    # ---- Strategy: pit stops (Jolpica) + tyre stints (OpenF1) -------------
    def _openf1_session(self, season: int, race_date: str):
        env = self.openf1.get("/sessions", [("year", "=", str(season)), ("session_name", "=", "Race")],
                              ttl=self._ttl(season))
        for s in env["data"]:
            if str(s.get("date_start", ""))[:10] == race_date:
                return s, env
        return None, env

    def strategy(self, season: int, rnd: int) -> dict:
        race, r_env = self._race_results(season, rnd)
        stops_races, p_envs = self._jolpica_all(season, f"/{season}/{rnd}/pitstops.json", "PitStops")
        codes = {r["Driver"]["driverId"]: r["Driver"].get("code") for r in race["Results"]}
        stops = [{"driver_id": p["driverId"], "code": codes.get(p["driverId"]), "stop": int(p["stop"]),
                  "lap": int(p["lap"]), "duration": p.get("duration")}
                 for rr in stops_races for p in rr.get("PitStops", [])]
        envelopes, notes, stints = [r_env] + p_envs, [], []
        if season < OPENF1_FIRST_SEASON:
            notes.append(f"Tyre stints need OpenF1, which covers {OPENF1_FIRST_SEASON} onward.")
        else:
            try:
                session, s_env = self._openf1_session(season, race["date"])
                envelopes.append(s_env)
                if session is None:
                    notes.append("OpenF1 has no matching race session for this date.")
                else:
                    st_env = self.openf1.get("/stints", [("session_key", "=", str(session["session_key"]))],
                                             ttl=self._ttl(season))
                    dr_env = self.openf1.get("/drivers", [("session_key", "=", str(session["session_key"]))],
                                             ttl=self._ttl(season))
                    envelopes += [st_env, dr_env]
                    acr = {d["driver_number"]: d.get("name_acronym") for d in dr_env["data"]}
                    stints = [{"driver_number": s["driver_number"], "code": acr.get(s["driver_number"]),
                               "stint": s.get("stint_number"), "lap_start": s.get("lap_start"),
                               "lap_end": s.get("lap_end"), "compound": s.get("compound"),
                               "tyre_age_at_start": s.get("tyre_age_at_start")} for s in st_env["data"]]
            except SourceError as exc:
                notes.append(f"Tyre stints unavailable: {exc.message}")
        order = [r["Driver"].get("code") for r in race["Results"]]
        return self._wrap(season, envelopes, {"season": season, "round": rnd, "race": race["raceName"],
                                              "finish_order": order, "pit_stops": stops, "stints": stints}, notes)

    # ---- Telemetry: one lap of car data (OpenF1) ---------------------------
    def telemetry(self, season: int, rnd: int, driver_number: int, lap: int) -> dict:
        if season < OPENF1_FIRST_SEASON:
            raise SourceError("OpenF1", f"telemetry is available from {OPENF1_FIRST_SEASON} onward", 404)
        race, r_env = self._race_results(season, rnd)
        session, s_env = self._openf1_session(season, race["date"])
        if session is None:
            raise SourceError("OpenF1", "no matching race session for this date", 404)
        key = str(session["session_key"])
        l_env = self.openf1.get("/laps", [("session_key", "=", key), ("driver_number", "=", str(driver_number)),
                                          ("lap_number", "=", str(lap))], ttl=self._ttl(season))
        if not l_env["data"] or not l_env["data"][0].get("date_start") or not l_env["data"][0].get("lap_duration"):
            raise SourceError("OpenF1", f"no timing for driver {driver_number} lap {lap}", 404)
        lap_row = l_env["data"][0]
        start = _parse_iso(lap_row["date_start"])
        end = start + timedelta(seconds=float(lap_row["lap_duration"]))
        c_env = self.openf1.get("/car_data", [("session_key", "=", key), ("driver_number", "=", str(driver_number)),
                                              ("date", ">=", _fmt_iso(start)), ("date", "<", _fmt_iso(end))],
                                ttl=self._ttl(season))
        points = []
        for row in c_env["data"]:
            t = (_parse_iso(row["date"]) - start).total_seconds()
            points.append({"t": round(t, 2), "speed": row.get("speed"), "throttle": row.get("throttle"),
                           "brake": row.get("brake"), "gear": row.get("n_gear")})
        points.sort(key=lambda p: p["t"])
        return self._wrap(season, [r_env, s_env, l_env, c_env], {
            "season": season, "round": rnd, "race": race["raceName"], "driver_number": driver_number,
            "lap": lap, "lap_time": lap_row.get("lap_duration"), "samples": len(points),
            "points": downsample(points)})


def _parse_iso(text: str) -> datetime:
    text = text.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _fmt_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
