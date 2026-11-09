"""Turns raw Jolpica / OpenF1 responses into small, UI-ready structures."""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta, timezone

from .sources import SourceError, utc_now_iso
from . import strategy as strat

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
    def __init__(self, jolpica, openf1, current_year: int | None = None, weather=None, today: str | None = None):
        self.jolpica = jolpica
        self.openf1 = openf1
        self.weather_src = weather  # Open-Meteo (forecast); optional
        self.today = today
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
                  "date": r["date"], "time": r.get("time"), "circuit_id": r["Circuit"].get("circuitId"),
                  "lat": _float(r["Circuit"]["Location"].get("lat")), "lon": _float(r["Circuit"]["Location"].get("long")),
                  "sprint": bool(r.get("Sprint"))}
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
                         "fastest_lap_rank": fl.get("rank"), "nationality": r["Driver"].get("nationality")})
        envs, colours = [env], {}
        if season >= OPENF1_FIRST_SEASON:  # optional: team colours for driver cards
            try:
                session, s_env = self._openf1_session(season, race["date"])
                if session:
                    d_env = self.openf1.get("/drivers", [("session_key", "=", str(session["session_key"]))],
                                            ttl=self._ttl(season))
                    envs += [s_env, d_env]
                    colours = {str(d["driver_number"]): "#" + d["team_colour"] for d in d_env["data"]
                               if re.fullmatch(r"[0-9A-Fa-f]{6}", str(d.get("team_colour") or ""))}
            except SourceError:
                pass
        for row in rows:
            row["team_colour"] = colours.get(str(row["number"]))
        return self._wrap(season, envs, {"season": season, "round": rnd, "race": race["raceName"],
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

    # ---- Strategy projection (model) ---------------------------------------
    def projection(self, season: int, rnd: int, allocation: dict, pit_loss: float | None = None,
                   fuel_gain: float = 0.055, cliff_factor: float = 2.0) -> dict:
        if season < OPENF1_FIRST_SEASON:
            raise SourceError("OpenF1", f"strategy projection needs OpenF1 lap data ({OPENF1_FIRST_SEASON} onward)", 404)
        race, r_env = self._race_results(season, rnd)
        session, s_env = self._openf1_session(season, race["date"])
        if session is None:
            raise SourceError("OpenF1", "no matching race session for this date", 404)
        key = str(session["session_key"])
        ttl = self._ttl(season)
        l_env = self.openf1.get("/laps", [("session_key", "=", key)], ttl=ttl)
        st_env = self.openf1.get("/stints", [("session_key", "=", key)], ttl=ttl)
        stops_races, p_envs = self._jolpica_all(season, f"/{season}/{rnd}/pitstops.json", "PitStops")
        notes = []
        durations = [parse_laptime(p.get("duration")) for rr in stops_races for p in rr.get("PitStops", [])]
        durations = [d for d in durations if d and d < 40]  # drop red-flag / penalty outliers
        measured_pit = round(statistics.median(durations), 2) if durations else None
        if pit_loss is None:
            pit_loss = measured_pit if measured_pit else 22.0
            if not measured_pit:
                notes.append("No pit-lane times found; assumed 22 s pit loss.")
        model = strat.fit_compounds(l_env["data"], st_env["data"], fuel_gain)
        if len(model) < 2:
            raise SourceError("OpenF1", "not enough clean dry-tyre laps to fit two compounds (wet race?)", 404)
        winner = race["Results"][0]
        race_laps = int(winner.get("laps") or 0)
        plans = strat.project(model, race_laps, allocation, pit_loss, fuel_gain, cliff_factor)
        missing = [c for c in strat.DRY if c not in model]
        if missing:
            notes.append(f"No usable race data for {', '.join(missing)}: plans using it are not shown.")
        # validation against what really happened
        validation = None
        seq, stops = _strategy_of(st_env["data"], int(winner["number"]))
        actual_ms = (winner.get("Time") or {}).get("millis")
        if seq and all(c in model for c in seq) and len(stops) == len(seq) - 1 and actual_ms:
            pred, _ = strat.simulate(seq, stops, race_laps, model, pit_loss, fuel_gain, cliff_factor)
            actual = int(actual_ms) / 1000
            validation = {"driver": winner["Driver"].get("code"), "sequence": list(seq), "pit_laps": list(stops),
                          "predicted": round(pred, 1), "actual": round(actual, 1),
                          "error_pct": round((pred - actual) / actual * 100, 2)}
        used = {}
        for r in race["Results"][:10]:
            sq, _ = _strategy_of(st_env["data"], int(r["number"]))
            if sq:
                used.setdefault("-".join(c[0] for c in sq), []).append(r["Driver"].get("code"))
        assumptions = [f"Fuel burn makes each lap {fuel_gain:.3f} s faster", f"Pit loss {pit_loss:.1f} s per stop "
                       f"({'median pit-lane time this race' if measured_pit and pit_loss == measured_pit else 'set by you'})",
                       f"Wear is linear; beyond the longest stint seen it grows {cliff_factor:g}x faster",
                       "Every stint starts on a new set", "No traffic, safety cars, weather, track evolution or driver differences"]
        return self._wrap(season, [r_env, s_env, l_env, st_env] + p_envs, {
            "season": season, "round": rnd, "race": race["raceName"], "race_laps": race_laps,
            "allocation": allocation, "pit_loss": pit_loss, "measured_pit_loss": measured_pit,
            "compounds": model, "plans": plans, "validation": validation, "used_top10": used,
            "assumptions": assumptions, "label": "MODEL PROJECTION - an estimate, not official data"}, notes)

    # ---- Points tracker: championship progression round by round -------------
    def points_tracker(self, season: int, top: int = 10) -> dict:
        cal = self.calendar(season)["data"]["races"]
        st = self.standings(season)
        done = int(st["data"]["after_round"] or 0)
        envs, series = [], {}
        for rnd in range(1, done + 1):
            env = self._jolpica(season, f"/{season}/{rnd}/driverStandings.json")
            envs.append(env)
            lists = env["data"]["MRData"]["StandingsTable"]["StandingsLists"]
            for row in (lists[0]["DriverStandings"] if lists else []):
                d = row["Driver"]
                s = series.setdefault(d["driverId"], {"driver_id": d["driverId"], "code": d.get("code"),
                                                      "name": f'{d["givenName"]} {d["familyName"]}', "points": []})
                s["points"].append([rnd, float(row["points"])])
        leaders = [d["driver_id"] for d in st["data"]["drivers"][:top]]
        remaining = [r for r in cal if r["round"] > done]
        sprints_left = sum(1 for r in remaining if r.get("sprint"))
        max_left = 25 * len(remaining) + 8 * sprints_left
        table = []
        lead_pts = st["data"]["drivers"][0]["points"] if st["data"]["drivers"] else 0
        for d in st["data"]["drivers"][:top]:
            gap = lead_pts - d["points"]
            table.append({**d, "gap": gap, "can_still_win": gap <= max_left if d["position"] != 1 else True})
        notes = [f"Max points still available: {max_left} ({len(remaining)} races x 25"
                 + (f" + {sprints_left} sprints x 8" if sprints_left else "") + "). Ignores tie-breaks."]
        return self._wrap(season, envs + [], {"season": season, "rounds_done": done, "rounds_total": len(cal),
                                              "max_points_left": max_left, "table": table,
                                              "series": [series[i] for i in leaders if i in series]}, notes)

    # ---- Race weekend: practice bests, qualifying, weather ----------------------
    def _today(self) -> str:
        return self.today or datetime.now(timezone.utc).date().isoformat()

    def weekend(self, season: int, rnd: int) -> dict:
        cal = self.calendar(season)["data"]["races"]
        race = next((r for r in cal if r["round"] == rnd), None)
        if race is None:
            raise SourceError("Jolpica-F1", f"no round {rnd} in {season}", 404)
        envs, notes, sessions = [], [], []
        # Qualifying (Jolpica) - published after the session
        quali = []
        try:
            q_env = self._jolpica(season, f"/{season}/{rnd}/qualifying.json")
            envs.append(q_env)
            races = q_env["data"]["MRData"]["RaceTable"]["Races"]
            for q in (races[0].get("QualifyingResults", []) if races else []):
                quali.append({"position": int(q.get("position") or 0), "number": q.get("number"),
                              "code": q["Driver"].get("code"), "name": f'{q["Driver"]["givenName"]} {q["Driver"]["familyName"]}',
                              "team": q["Constructor"]["name"], "q1": q.get("Q1"), "q2": q.get("Q2"), "q3": q.get("Q3")})
        except SourceError as exc:
            notes.append(f"Qualifying not available: {exc.message}")
        if not quali:
            notes.append("No qualifying result published yet.")
        # Practice and other sessions (OpenF1) - free data arrives after each session
        if season >= OPENF1_FIRST_SEASON:
            try:
                s_env = self.openf1.get("/sessions", [("year", "=", str(season))], ttl=self._ttl(season))
                envs.append(s_env)
                start = (datetime.fromisoformat(race["date"]) - timedelta(days=4)).date().isoformat()
                weekend = [x for x in s_env["data"] if start <= str(x.get("date_start", ""))[:10] <= race["date"]]
                for x in sorted(weekend, key=lambda x: x.get("date_start", "")):
                    item = {"name": x.get("session_name"), "start": x.get("date_start"), "end": x.get("date_end"),
                            "key": x.get("session_key"), "best": []}
                    if str(x.get("session_name", "")).startswith("Practice") and x.get("date_start", "") < self._today():
                        try:
                            l_env = self.openf1.get("/laps", [("session_key", "=", str(x["session_key"]))], ttl=self._ttl(season))
                            d_env = self.openf1.get("/drivers", [("session_key", "=", str(x["session_key"]))], ttl=self._ttl(season))
                            envs += [l_env, d_env]
                            acr = {d["driver_number"]: (d.get("name_acronym"), d.get("team_name"),
                                                        "#" + d["team_colour"] if re.fullmatch(r"[0-9A-Fa-f]{6}", str(d.get("team_colour") or "")) else None)
                                   for d in d_env["data"]}
                            best = {}
                            for lap in l_env["data"]:
                                t = lap.get("lap_duration")
                                if t and not lap.get("is_pit_out_lap") and (lap["driver_number"] not in best or t < best[lap["driver_number"]]):
                                    best[lap["driver_number"]] = t
                            order = sorted(best.items(), key=lambda kv: kv[1])
                            top = order[0][1] if order else None
                            item["best"] = [{"number": n, "code": acr.get(n, (None,))[0], "team": acr.get(n, (None, None))[1],
                                             "team_colour": acr.get(n, (None, None, None))[2], "time": t,
                                             "gap": round(t - top, 3)} for n, t in order]
                        except SourceError as exc:
                            item["error"] = exc.message
                    sessions.append(item)
            except SourceError as exc:
                notes.append(f"Session list not available: {exc.message}")
        return self._wrap(season, envs or [{"source": "Jolpica-F1", "cache": "n/a"}], {
            "season": season, "round": rnd, "race": race["name"], "date": race["date"],
            "sessions": sessions, "qualifying": quali}, notes)

    def weather(self, season: int, rnd: int) -> dict:
        cal = self.calendar(season)["data"]["races"]
        race = next((r for r in cal if r["round"] == rnd), None)
        if race is None:
            raise SourceError("Jolpica-F1", f"no round {rnd} in {season}", 404)
        out, envs, notes = {"race": race["name"], "date": race["date"], "time": race.get("time"),
                            "forecast": None, "measured": None}, [], []
        today = self._today()
        days_ahead = (datetime.fromisoformat(race["date"]).date() - datetime.fromisoformat(today).date()).days
        # Forecast: Open-Meteo gives up to 16 days ahead
        if self.weather_src is None or race.get("lat") is None:
            notes.append("No forecast source configured.")
        elif days_ahead > 15:
            notes.append(f"Forecast opens 16 days before the race ({days_ahead} days to go).")
        elif days_ahead >= -1:
            start = (datetime.fromisoformat(race["date"]) - timedelta(days=2)).date().isoformat()
            env = self.weather_src.get("/forecast", [
                ("latitude", "=", f'{race["lat"]:.4f}'), ("longitude", "=", f'{race["lon"]:.4f}'),
                ("hourly", "=", "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,cloud_cover"),
                ("start_date", "=", start), ("end_date", "=", race["date"]), ("timezone", "=", "UTC")], ttl=1800)
            envs.append(env)
            h = env["data"].get("hourly") or {}
            out["forecast"] = {"time": h.get("time", []), "temp_c": h.get("temperature_2m", []),
                               "rain_pct": h.get("precipitation_probability", []), "rain_mm": h.get("precipitation", []),
                               "wind_kmh": h.get("wind_speed_10m", []), "cloud_pct": h.get("cloud_cover", []),
                               "credit": "Weather data by Open-Meteo.com (CC BY 4.0)"}
        else:
            notes.append("Race is in the past: showing measured track weather instead of a forecast.")
        # Measured at the track (OpenF1 weather station) for finished races
        if season >= OPENF1_FIRST_SEASON and days_ahead <= 0:
            try:
                session, s_env = self._openf1_session(season, race["date"])
                if session:
                    w_env = self.openf1.get("/weather", [("session_key", "=", str(session["session_key"]))], ttl=self._ttl(season))
                    envs += [s_env, w_env]
                    rows = sorted(w_env["data"], key=lambda w: w.get("date", ""))
                    if rows:
                        out["measured"] = {"time": [w.get("date") for w in rows], "air_c": [w.get("air_temperature") for w in rows],
                                           "track_c": [w.get("track_temperature") for w in rows],
                                           "rain": any(w.get("rainfall") for w in rows),
                                           "humidity": [w.get("humidity") for w in rows]}
            except SourceError as exc:
                notes.append(f"Measured weather not available: {exc.message}")
        return self._wrap(season, envs or [{"source": "Open-Meteo", "cache": "n/a"}], out, notes)

    # ---- Live drill: replay a finished session on a simulated clock -------------
    def replay(self, season: int, rnd: int, session_name: str = "Qualifying") -> dict:
        if season < OPENF1_FIRST_SEASON:
            raise SourceError("OpenF1", f"session replay needs OpenF1 data ({OPENF1_FIRST_SEASON} onward)", 404)
        cal = self.calendar(season)["data"]["races"]
        race = next((r for r in cal if r["round"] == rnd), None)
        if race is None:
            raise SourceError("Jolpica-F1", f"no round {rnd} in {season}", 404)
        ttl = self._ttl(season)
        s_env = self.openf1.get("/sessions", [("year", "=", str(season))], ttl=ttl)
        start_win = (datetime.fromisoformat(race["date"]) - timedelta(days=4)).date().isoformat()
        cands = [x for x in s_env["data"] if x.get("session_name") == session_name
                 and start_win <= str(x.get("date_start", ""))[:10] <= race["date"]]
        if not cands:
            raise SourceError("OpenF1", f"no {session_name} session published for this weekend yet", 404)
        sess = cands[0]
        key = str(sess["session_key"])
        t0 = _parse_iso(sess["date_start"])
        l_env = self.openf1.get("/laps", [("session_key", "=", key)], ttl=ttl)
        d_env = self.openf1.get("/drivers", [("session_key", "=", key)], ttl=ttl)
        rc_env = self.openf1.get("/race_control", [("session_key", "=", key)], ttl=ttl)
        drivers = {d["driver_number"]: {"number": d["driver_number"], "code": d.get("name_acronym"),
                                        "team": d.get("team_name"),
                                        "team_colour": "#" + d["team_colour"] if re.fullmatch(r"[0-9A-Fa-f]{6}", str(d.get("team_colour") or "")) else None}
                   for d in d_env["data"]}
        laps = []
        for lap in l_env["data"]:
            if not lap.get("date_start") or not lap.get("lap_duration") or lap.get("is_pit_out_lap"):
                continue
            end = (_parse_iso(lap["date_start"]) - t0).total_seconds() + float(lap["lap_duration"])
            laps.append({"t": round(end, 2), "driver": lap["driver_number"], "time": float(lap["lap_duration"])})
        laps.sort(key=lambda x: x["t"])
        status_events = [{"t": 0.0, "status": "GREEN", "message": "Session start"}]
        for m in sorted(rc_env["data"], key=lambda m: m.get("date") or ""):
            if not m.get("date"):
                continue
            st = _status_from_message(m)
            if st:
                status_events.append({"t": round((_parse_iso(m["date"]) - t0).total_seconds(), 2), "status": st,
                                      "message": m.get("message")})
        length = max([x["t"] for x in laps] + [e["t"] for e in status_events] + [1.0])
        if sess.get("date_end"):
            length = max(length, (_parse_iso(sess["date_end"]) - t0).total_seconds())
        return self._wrap(season, [s_env, l_env, d_env, rc_env], {
            "season": season, "round": rnd, "race": race["name"], "session": session_name,
            "session_start": sess["date_start"], "session_key": sess["session_key"], "length_s": round(length),
            "drivers": list(drivers.values()),
            "laps": laps, "status": status_events,
            "label": "SIMULATION - replay of a finished session, not live data"})

    # ---- Car tracker: positions for a window of a replayed session -------------
    def positions(self, season: int, rnd: int, session_name: str, t_from: int, t_to: int) -> dict:
        """Car positions (1 per second per car) between t_from and t_to seconds after session start,
        in the same 0-100 coordinates as the track map."""
        if t_to <= t_from or t_to - t_from > 180:
            raise SourceError("PADDOCK", "window must be 1-180 seconds", 400)
        tm = self.track_map(season, rnd)["data"]["transform"]
        rp = self.replay(season, rnd, session_name)["data"]
        t0 = _parse_iso(rp["session_start"])
        ttl = self._ttl(season)
        key = str(rp["session_key"])
        env = self.openf1.get("/location", [("session_key", "=", key),
                                            ("date", ">=", _fmt_iso(t0 + timedelta(seconds=t_from))),
                                            ("date", "<", _fmt_iso(t0 + timedelta(seconds=t_to)))], ttl=ttl)
        cars: dict = {}
        for p in env["data"]:
            if p.get("x") is None or p.get("date") is None or (p.get("x") == 0 and p.get("y") == 0):
                continue  # (0,0) means no fix (car in garage)
            t = round((_parse_iso(p["date"]) - t0).total_seconds())
            x = round((p["x"] - tm["min_x"]) / tm["span"] * 100, 1)
            y = round((tm["max_y"] - p["y"]) / tm["span"] * 100, 1)
            cars.setdefault(p["driver_number"], {})[t] = [t, x, y]  # keep one point per second
        return self._wrap(season, [env], {"from": t_from, "to": t_to,
                                          "cars": {str(n): sorted(v.values()) for n, v in cars.items()}})

    # ---- Track map + race control (OpenF1 location / race_control) -----------
    def _past_session_for_circuit(self, season: int, rnd: int):
        """The race itself if already run, else the latest earlier OpenF1-era race at the same circuit."""
        today = datetime.now(timezone.utc).date().isoformat()
        cal = self.calendar(season)["data"]["races"]
        race = next((r for r in cal if r["round"] == rnd), None)
        if race is None:
            raise SourceError("Jolpica-F1", f"no round {rnd} in {season}", 404)
        for year in range(season, OPENF1_FIRST_SEASON - 1, -1):
            races = cal if year == season else self.calendar(year)["data"]["races"]
            match = next((r for r in races if r["circuit_id"] == race["circuit_id"] and r["date"] < today), None)
            if match:
                session, _ = self._openf1_session(year, match["date"])
                if session:
                    return race, match, year, session
        return race, None, None, None

    def track_map(self, season: int, rnd: int) -> dict:
        race, used, year, session = self._past_session_for_circuit(season, rnd)
        if session is None:
            raise SourceError("OpenF1", "no position data for this circuit yet (OpenF1 covers 2023 onward)", 404)
        key = str(session["session_key"])
        ttl = self._ttl(year)
        laps = self.openf1.get("/laps", [("session_key", "=", key)], ttl=ttl)["data"]
        clean = sorted((l for l in laps if l.get("lap_duration") and l.get("date_start") and not l.get("is_pit_out_lap")
                        and (l.get("lap_number") or 0) > 2), key=lambda l: l["lap_duration"])
        if not clean:
            raise SourceError("OpenF1", "no clean lap to trace the track from", 404)
        # typical racing laps (around median pace); try a few in case one car has no position data
        try:  # prefer the winner's laps (always tracked); then anyone else
            winner = int(self._race_results(year, used["round"])[0]["Results"][0]["number"])
        except (SourceError, KeyError, ValueError, IndexError):
            winner = None
        own = [l for l in clean if l["driver_number"] == winner]
        candidates = own[len(own) // 2:len(own) // 2 + 2] + clean[len(clean) // 2:][:4]
        pts, loc = [], None
        for lap in candidates:
            start = _parse_iso(lap["date_start"])
            end = start + timedelta(seconds=float(lap["lap_duration"]))
            loc = self.openf1.get("/location", [("session_key", "=", key), ("driver_number", "=", str(lap["driver_number"])),
                                                ("date", ">=", _fmt_iso(start)), ("date", "<", _fmt_iso(end))], ttl=ttl)
            pts = [(p["x"], p["y"]) for p in sorted(loc["data"], key=lambda p: p["date"]) if p.get("x") is not None]
            if len(pts) >= 20:
                break
        if len(pts) < 20:
            raise SourceError("OpenF1", "not enough position samples for a map", 404)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1
        norm = [[round((x - min(xs)) / span * 100, 1), round((max(ys) - y) / span * 100, 1)] for x, y in downsample(pts, 300)]
        notes = [] if year == season and used["round"] == rnd else [f"Outline traced from the {year} race at this circuit."]
        return self._wrap(year, [loc], {"season": season, "round": rnd, "circuit": race["circuit"], "country": race["country"],
                                        "traced_from": {"season": year, "date": used["date"]},
                                        "width": round((max(xs) - min(xs)) / span * 100, 1),
                                        "height": round((max(ys) - min(ys)) / span * 100, 1), "points": norm,
                                        "transform": {"min_x": min(xs), "max_y": max(ys), "span": span}}, notes)

    def race_control(self, season: int, rnd: int) -> dict:
        if season < OPENF1_FIRST_SEASON:
            raise SourceError("OpenF1", f"race control messages cover {OPENF1_FIRST_SEASON} onward", 404)
        race, r_env = self._race_results(season, rnd)
        session, s_env = self._openf1_session(season, race["date"])
        if session is None:
            raise SourceError("OpenF1", "no matching race session", 404)
        env = self.openf1.get("/race_control", [("session_key", "=", str(session["session_key"]))], ttl=self._ttl(season))
        laps = int(race["Results"][0].get("laps") or 0)
        events = [{"lap": m.get("lap_number"), "flag": m.get("flag"), "category": m.get("category"),
                   "scope": m.get("scope"), "message": m.get("message"), "date": m.get("date")}
                  for m in sorted(env["data"], key=lambda m: m.get("date") or "")]
        return self._wrap(season, [r_env, s_env, env], {"season": season, "round": rnd, "race_laps": laps,
                                                         "by_lap": track_status_by_lap(events, laps), "events": events[-60:]})

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
        if not points:
            raise SourceError("OpenF1", f"no car data recorded for car {driver_number} on lap {lap}; try another lap", 404)
        return self._wrap(season, [r_env, s_env, l_env, c_env], {
            "season": season, "round": rnd, "race": race["raceName"], "driver_number": driver_number,
            "lap": lap, "lap_time": lap_row.get("lap_duration"), "samples": len(points),
            "points": downsample(points)})


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def track_status_by_lap(events: list, laps: int) -> list:
    """Whole-track status per lap from race-control messages: GREEN, YELLOW, VSC, SC, RED, CHEQUERED.
    Local (sector) yellows are ignored; only track-wide states change the light."""
    status, out, by_lap = "GREEN", [], {}
    for e in events:
        if e.get("lap") is not None:
            by_lap.setdefault(int(e["lap"]), []).append(e)
    for lap in range(1, laps + 1):
        for e in by_lap.get(lap, []):
            msg, flag, cat = str(e.get("message") or "").upper(), str(e.get("flag") or "").upper(), str(e.get("category") or "")
            if flag == "RED":
                status = "RED"
            elif flag == "CHEQUERED":
                status = "CHEQUERED"
            elif "VIRTUAL SAFETY CAR DEPLOYED" in msg or "VSC DEPLOYED" in msg:
                status = "VSC"
            elif cat == "SafetyCar" and "DEPLOYED" in msg:
                status = "SC"
            elif "ENDING" in msg or "IN THIS LAP" in msg or flag in ("GREEN", "CLEAR") and e.get("scope") == "Track":
                status = "GREEN"
            elif flag in ("YELLOW", "DOUBLE YELLOW") and e.get("scope") == "Track":
                status = "YELLOW"
        out.append(status)
    return out


def _status_from_message(m: dict) -> str | None:
    """Track-wide status implied by one race-control message (None = no change)."""
    msg, flag, cat = str(m.get("message") or "").upper(), str(m.get("flag") or "").upper(), str(m.get("category") or "")
    scope = m.get("scope")
    if flag == "RED":
        return "RED"
    if flag == "CHEQUERED":
        return "CHEQUERED"
    if "VIRTUAL SAFETY CAR DEPLOYED" in msg or "VSC DEPLOYED" in msg:
        return "VSC"
    if cat == "SafetyCar" and "DEPLOYED" in msg:
        return "SC"
    if flag in ("YELLOW", "DOUBLE YELLOW"):
        return "YELLOW"  # in a replay any yellow is worth flashing
    if flag in ("GREEN", "CLEAR") or "ENDING" in msg or "TRACK CLEAR" in msg or "IN THIS LAP" in msg:
        return "GREEN"
    return None


def _strategy_of(stints: list, number: int) -> tuple[tuple, tuple]:
    own = sorted((s for s in stints if s.get("driver_number") == number), key=lambda s: s.get("stint_number") or 0)
    seq = tuple(str(s.get("compound") or "?").upper() for s in own)
    stops = tuple(s["lap_end"] for s in own[:-1] if s.get("lap_end"))
    return seq, stops


def _parse_iso(text: str) -> datetime:
    text = text.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _fmt_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
