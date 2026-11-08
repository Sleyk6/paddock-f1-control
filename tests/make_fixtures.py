"""Generate tests/fixtures/synthetic.json.

SYNTHETIC TEST DATA ONLY. Driver names, teams and times are invented
("Test Driver ...", "Team Alpha ...") and must never be presented as real results.
Shapes mirror Jolpica-F1 (Ergast format) and OpenF1 responses.
Run:  python tests/make_fixtures.py
"""
import json
import math
import os
import random

rng = random.Random(42)
SEASON, RACE_DATE, LAPS = "2024", "2024-03-02", 20
DRIVERS = [  # (driverId, code, number, given, family, team)
    ("test_alpha", "TDA", "1", "Test Driver", "Alpha", "Team Alpha"),
    ("test_bravo", "TDB", "2", "Test Driver", "Bravo", "Team Alpha"),
    ("test_charlie", "TDC", "3", "Test Driver", "Charlie", "Team Bravo"),
    ("test_delta", "TDD", "4", "Test Driver", "Delta", "Team Bravo"),
    ("test_echo", "TDE", "5", "Test Driver", "Echo", "Team Charlie"),
    ("test_foxtrot", "TDF", "6", "Test Driver", "Foxtrot", "Team Charlie"),
]


def mr(total, **table):
    return {"MRData": {"limit": "100", "offset": "0", "total": str(total), **table}}


def driver(d):
    return {"driverId": d[0], "code": d[1], "permanentNumber": d[2], "givenName": d[3], "familyName": d[4]}


def fmt(t):
    return f"{int(t // 60)}:{t % 60:06.3f}"


circuit = {"circuitId": "test_ring", "circuitName": "Synthetic Test Ring",
           "Location": {"locality": "Testville", "country": "Testland"}}
races = [{"season": SEASON, "round": str(i + 1), "raceName": f"Test Grand Prix {i + 1}", "Circuit": circuit,
          "date": f"2024-03-{2 + 7 * i:02d}", "time": "15:00:00Z"} for i in range(3)]

# lap times: base pace per driver + noise; pit stop on lap 10/11 adds 20 s
pace = {d[0]: 92.0 + i * 0.25 for i, d in enumerate(DRIVERS)}
pit_lap = {d[0]: 10 + (i % 2) for i, d in enumerate(DRIVERS)}
laps = {}
for d in DRIVERS:
    rows = []
    for n in range(1, LAPS + 1):
        t = pace[d[0]] + rng.uniform(-0.4, 0.6) - n * 0.03 + (20.0 if n == pit_lap[d[0]] else 0)
        rows.append(round(t, 3))
    laps[d[0]] = rows
total = {k: sum(v) for k, v in laps.items()}
order = sorted(total, key=total.get)
by_id = {d[0]: d for d in DRIVERS}
points = [25, 18, 15, 12, 10, 8]

results = []
for pos, did in enumerate(order, 1):
    d = by_id[did]
    best = min(laps[did])
    results.append({"number": d[2], "position": str(pos), "positionText": str(pos), "points": str(points[pos - 1]),
                    "Driver": driver(d), "Constructor": {"constructorId": d[5].lower().replace(" ", "_"), "name": d[5]},
                    "grid": str(DRIVERS.index(d) + 1), "laps": str(LAPS), "status": "Finished",
                    "Time": {"time": fmt(total[did]) if pos == 1 else f"+{total[did] - total[order[0]]:.3f}"},
                    "FastestLap": {"rank": "0", "lap": str(laps[did].index(best) + 1), "Time": {"time": fmt(best)}}})

jolpica = {
    f"/{SEASON}.json": mr(3, RaceTable={"season": SEASON, "Races": races}),
    f"/{SEASON}/1/results.json": mr(len(results), RaceTable={"Races": [{**races[0], "Results": results}]}),
    f"/{SEASON}/1/pitstops.json": mr(len(DRIVERS), RaceTable={"Races": [{**races[0], "PitStops": [
        {"driverId": d[0], "lap": str(pit_lap[d[0]]), "stop": "1", "time": "15:20:00",
         "duration": f"{rng.uniform(21.5, 24.0):.3f}"} for d in DRIVERS]}]}),
    f"/{SEASON}/driverStandings.json": mr(len(results), StandingsTable={"season": SEASON, "StandingsLists": [
        {"season": SEASON, "round": "1", "DriverStandings": [
            {"position": r["position"], "points": r["points"], "wins": "1" if r["position"] == "1" else "0",
             "Driver": r["Driver"], "Constructors": [r["Constructor"]]} for r in results]}]}),
}
team_pts = {}
for r in results:
    team_pts[r["Constructor"]["name"]] = team_pts.get(r["Constructor"]["name"], 0) + int(r["points"])
jolpica[f"/{SEASON}/constructorStandings.json"] = mr(len(team_pts), StandingsTable={"StandingsLists": [
    {"round": "1", "ConstructorStandings": [
        {"position": str(i + 1), "points": str(p), "wins": "1" if i == 0 else "0", "Constructor": {"name": n}}
        for i, (n, p) in enumerate(sorted(team_pts.items(), key=lambda kv: -kv[1]))]}]})
for d in DRIVERS:
    jolpica[f"/{SEASON}/1/drivers/{d[0]}/laps.json"] = mr(LAPS, RaceTable={"Races": [{**races[0], "Laps": [
        {"number": str(n + 1), "Timings": [{"driverId": d[0], "position": str(order.index(d[0]) + 1),
                                            "time": fmt(t)}]} for n, t in enumerate(laps[d[0]])]}]})

SESSION = 9999
openf1 = {
    "/sessions": [{"session_key": SESSION, "session_name": "Race", "year": 2024,
                   "date_start": RACE_DATE + "T15:00:00+00:00", "country_name": "Testland"}],
    "/drivers": [{"session_key": SESSION, "driver_number": int(d[2]), "name_acronym": d[1],
                  "full_name": f"{d[3]} {d[4]}".upper(), "team_name": d[5]} for d in DRIVERS],
    "/stints": [], "/laps": [], "/car_data": [],
}
for d in DRIVERS:
    n, p = int(d[2]), pit_lap[d[0]]
    openf1["/stints"] += [
        {"session_key": SESSION, "driver_number": n, "stint_number": 1, "lap_start": 1, "lap_end": p,
         "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"session_key": SESSION, "driver_number": n, "stint_number": 2, "lap_start": p + 1, "lap_end": LAPS,
         "compound": "HARD" if n % 2 else "SOFT", "tyre_age_at_start": 0}]
# lap 5 telemetry for drivers 1 and 2, 4 Hz synthetic trace
for n in (1, 2):
    did = DRIVERS[n - 1][0]
    start_s = 300 + 92 * 4
    dur = laps[did][4]
    openf1["/laps"].append({"session_key": SESSION, "driver_number": n, "lap_number": 5,
                            "date_start": f"{RACE_DATE}T15:{start_s // 60:02d}:{start_s % 60:02d}.000000+00:00",
                            "lap_duration": dur})
    for i in range(int(dur * 4)):
        t = i / 4
        phase = (t / dur) * 2 * math.pi * 6  # six braking zones
        speed = 210 + 95 * math.sin(phase) + (n - 1) * 3
        throttle = max(0, min(100, int(60 + 60 * math.sin(phase))))
        brake = 100 if math.sin(phase) < -0.85 else 0
        gear = max(2, min(8, int(2 + (speed - 100) / 30)))
        sec = start_s + t
        openf1["/car_data"].append({"session_key": SESSION, "driver_number": n,
                                    "date": f"{RACE_DATE}T15:{int(sec // 60):02d}:{sec % 60:09.6f}+00:00",
                                    "speed": round(speed), "throttle": throttle, "brake": brake, "n_gear": gear})

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "synthetic.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"_warning": "SYNTHETIC TEST DATA - invented names and times, not real F1 data",
               "jolpica": jolpica, "openf1": openf1}, fh, indent=1)
print("wrote", out)
