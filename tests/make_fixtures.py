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


NATS = ["British", "Dutch", "Monegasque", "Spanish", "Australian", "Japanese"]


def driver(d):
    return {"driverId": d[0], "code": d[1], "permanentNumber": d[2], "givenName": d[3], "familyName": d[4],
            "nationality": NATS[int(d[2]) - 1]}


def fmt(t):
    return f"{int(t // 60)}:{t % 60:06.3f}"


circuit = {"circuitId": "test_ring", "circuitName": "Synthetic Test Ring",
           "Location": {"lat": "10.5", "long": "20.25", "locality": "Testville", "country": "Testland"}}
races = [{"season": SEASON, "round": str(i + 1), "raceName": f"Test Grand Prix {i + 1}", "Circuit": circuit,
          "date": f"2024-03-{2 + 7 * i:02d}", "time": "15:00:00Z"} for i in range(3)]

# Lap times follow a KNOWN tyre model so tests can check the fitter recovers it:
# time = driver pace + compound offset + wear*age - fuel 0.055 s/lap + small noise; pit lap +20 s.
# Stint 1 MEDIUM, stint 2 HARD (odd car numbers) or SOFT (even).
TRUE = {"SOFT": (0.0, 0.12), "MEDIUM": (0.4, 0.07), "HARD": (0.8, 0.04)}  # (offset s, wear s/lap)
FUEL = 0.055
pace = {d[0]: 92.0 + i * 0.25 for i, d in enumerate(DRIVERS)}
pit_lap = {d[0]: 10 + (i % 2) for i, d in enumerate(DRIVERS)}
second = {d[0]: "HARD" if int(d[2]) % 2 else "SOFT" for d in DRIVERS}
laps = {}
for d in DRIVERS:
    rows = []
    for n in range(1, LAPS + 1):
        p = pit_lap[d[0]]
        comp, age = ("MEDIUM", n) if n <= p else (second[d[0]], n - p)
        off, wear = TRUE[comp]
        t = pace[d[0]] + off + wear * age - FUEL * (n - 1) + rng.uniform(-0.15, 0.15) + (20.0 if n == p else 0)
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
                    "Time": {"millis": str(round(total[did] * 1000)), "time": fmt(total[did]) if pos == 1 else f"+{total[did] - total[order[0]]:.3f}"},
                    "FastestLap": {"rank": "1" if did == min(laps, key=lambda k: min(laps[k])) else "2", "lap": str(laps[did].index(best) + 1), "Time": {"time": fmt(best)}}})

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
jolpica[f"/{SEASON}/1/driverStandings.json"] = jolpica[f"/{SEASON}/driverStandings.json"]
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
                  "full_name": f"{d[3]} {d[4]}".upper(), "team_name": d[5],
                  "team_colour": {"Team Alpha": "E8002D", "Team Bravo": "27F4D2", "Team Charlie": "FF8000"}[d[5]]} for d in DRIVERS],
    "/stints": [], "/laps": [], "/car_data": [],
}
for d in DRIVERS:
    n, p = int(d[2]), pit_lap[d[0]]
    openf1["/stints"] += [
        {"session_key": SESSION, "driver_number": n, "stint_number": 1, "lap_start": 1, "lap_end": p,
         "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"session_key": SESSION, "driver_number": n, "stint_number": 2, "lap_start": p + 1, "lap_end": LAPS,
         "compound": second[d[0]], "tyre_age_at_start": 0}]
# OpenF1 laps for every car and lap (start times accumulate from 15:00:00), car_data for lap 5 of cars 1-2
for d in DRIVERS:
    n_car, start = int(d[2]), 15 * 3600.0
    for n, dur in enumerate(laps[d[0]], 1):
        openf1["/laps"].append({"session_key": SESSION, "driver_number": n_car, "lap_number": n,
                                "date_start": f"{RACE_DATE}T{int(start // 3600):02d}:{int(start % 3600 // 60):02d}:{start % 60:09.6f}+00:00",
                                "lap_duration": dur, "is_pit_out_lap": n == pit_lap[d[0]] + 1})
        if n == 5 and n_car in (1, 2):
            for i in range(int(dur * 4)):
                t = i / 4
                phase = (t / dur) * 2 * math.pi * 6  # six braking zones
                speed = 210 + 95 * math.sin(phase) + (n_car - 1) * 3
                sec = start + t
                openf1["/car_data"].append({
                    "session_key": SESSION, "driver_number": n_car,
                    "date": f"{RACE_DATE}T{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:09.6f}+00:00",
                    "speed": round(speed), "throttle": max(0, min(100, int(60 + 60 * math.sin(phase)))),
                    "brake": 100 if math.sin(phase) < -0.85 else 0,
                    "n_gear": max(2, min(8, int(2 + (speed - 100) / 30)))})
        start += dur

# OpenF1 location: a synthetic kidney-shaped loop for every lap of car 1 (any lap can be traced)
openf1["/location"] = []
start = 15 * 3600.0
for n, dur in enumerate(laps["test_alpha"], 1):
    for i in range(int(dur * 3)):
        a = 2 * math.pi * i / (dur * 3)
        x = 4000 * math.cos(a) + 900 * math.cos(3 * a)
        y = 2200 * math.sin(a) - 600 * math.sin(2 * a)
        sec = start + i / 3
        openf1["/location"].append({"session_key": SESSION, "driver_number": 1, "x": round(x), "y": round(y), "z": 0,
                                    "date": f"{RACE_DATE}T{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:09.6f}+00:00"})
    start += dur
# Race control: a safety car laps 6-7, sector yellow on lap 12 (ignored), chequered flag on the last lap
openf1["/race_control"] = [
    {"session_key": SESSION, "lap_number": 1, "category": "Flag", "flag": "GREEN", "scope": "Track", "message": "GREEN LIGHT - PIT EXIT OPEN", "date": RACE_DATE + "T15:00:00+00:00"},
    {"session_key": SESSION, "lap_number": 6, "category": "SafetyCar", "flag": None, "scope": None, "message": "SAFETY CAR DEPLOYED", "date": RACE_DATE + "T15:08:00+00:00"},
    {"session_key": SESSION, "lap_number": 8, "category": "SafetyCar", "flag": None, "scope": None, "message": "SAFETY CAR IN THIS LAP", "date": RACE_DATE + "T15:11:00+00:00"},
    {"session_key": SESSION, "lap_number": 12, "category": "Flag", "flag": "YELLOW", "scope": "Sector", "message": "YELLOW IN TRACK SECTOR 7", "date": RACE_DATE + "T15:18:00+00:00"},
    {"session_key": SESSION, "lap_number": LAPS, "category": "Flag", "flag": "CHEQUERED", "scope": "Track", "message": "CHEQUERED FLAG", "date": RACE_DATE + "T15:31:00+00:00"}]

# Qualifying (Jolpica) for round 1
jolpica[f"/{SEASON}/1/qualifying.json"] = mr(len(DRIVERS), RaceTable={"Races": [{**races[0], "QualifyingResults": [
    {"number": d[2], "position": str(i + 1), "Driver": driver(d), "Constructor": {"name": d[5]},
     "Q1": fmt(91.4 + i * 0.12), "Q2": fmt(91.1 + i * 0.1) if i < 5 else None, "Q3": fmt(90.8 + i * 0.09) if i < 3 else None}
    for i, d in enumerate(DRIVERS)]}]})
# Practice 1 (OpenF1): session 9990 two days before, three timed laps per car
openf1["/sessions"].insert(0, {"session_key": 9990, "session_name": "Practice 1", "year": 2024,
                               "date_start": "2024-02-29T11:30:00+00:00", "date_end": "2024-02-29T12:30:00+00:00"})
for i, d in enumerate(DRIVERS):
    for k in range(3):
        openf1["/laps"].append({"session_key": 9990, "driver_number": int(d[2]), "lap_number": k + 1,
                                "date_start": "2024-02-29T11:40:00+00:00", "lap_duration": round(93.0 + i * 0.2 - k * 0.3, 3),
                                "is_pit_out_lap": k == 0})
openf1["/drivers"] += [{**x, "session_key": 9990} for x in openf1["/drivers"] if x["session_key"] == SESSION]
# Qualifying (OpenF1): session 9991 the day before, 3 runs per car, a red flag mid-session
Q0 = 14 * 3600 + 0.0
def qtime(sec):
    return f"2024-03-01T{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:09.6f}+00:00"
openf1["/sessions"].insert(1, {"session_key": 9991, "session_name": "Qualifying", "year": 2024,
                               "date_start": qtime(Q0), "date_end": qtime(Q0 + 3600)})
for i, d in enumerate(DRIVERS):
    for run, base in enumerate((300, 1500, 2700)):
        st = Q0 + base + i * 25
        openf1["/laps"].append({"session_key": 9991, "driver_number": int(d[2]), "lap_number": run * 2 + 1,
                                "date_start": qtime(st), "lap_duration": 100.0, "is_pit_out_lap": True})
        openf1["/laps"].append({"session_key": 9991, "driver_number": int(d[2]), "lap_number": run * 2 + 2,
                                "date_start": qtime(st + 100), "lap_duration": round(91.6 - run * 0.35 + i * 0.11 + rng.uniform(0, .08), 3),
                                "is_pit_out_lap": False})
openf1["/drivers"] += [{**x, "session_key": 9991} for x in openf1["/drivers"] if x["session_key"] == SESSION]
openf1["/race_control"] += [
    {"session_key": 9991, "lap_number": None, "category": "Flag", "flag": "GREEN", "scope": "Track", "message": "GREEN LIGHT - PIT EXIT OPEN", "date": qtime(Q0)},
    {"session_key": 9991, "lap_number": None, "category": "Flag", "flag": "YELLOW", "scope": "Sector", "message": "YELLOW IN TRACK SECTOR 4", "date": qtime(Q0 + 900)},
    {"session_key": 9991, "lap_number": None, "category": "Flag", "flag": "CLEAR", "scope": "Sector", "message": "CLEAR IN TRACK SECTOR 4", "date": qtime(Q0 + 960)},
    {"session_key": 9991, "lap_number": None, "category": "Flag", "flag": "RED", "scope": "Track", "message": "RED FLAG", "date": qtime(Q0 + 1900)},
    {"session_key": 9991, "lap_number": None, "category": "Flag", "flag": "GREEN", "scope": "Track", "message": "GREEN LIGHT - PIT EXIT OPEN", "date": qtime(Q0 + 2400)},
    {"session_key": 9991, "lap_number": None, "category": "Flag", "flag": "CHEQUERED", "scope": "Track", "message": "CHEQUERED FLAG", "date": qtime(Q0 + 3600)}]

# Track weather station during the race (OpenF1)
openf1["/weather"] = [{"session_key": SESSION, "date": f"{RACE_DATE}T15:{m:02d}:00+00:00", "air_temperature": 24 + m / 30,
                       "track_temperature": 38 + m / 15, "humidity": 55, "rainfall": 0} for m in range(0, 31, 5)]
# Open-Meteo forecast shape (hourly), 3 days
hours = [f"2024-02-{29 if h < 24 else 0:02d}T{h % 24:02d}:00" for h in range(0, 72)]
hours = [(f"2024-02-29T{h:02d}:00" if h < 24 else f"2024-03-0{1 + (h - 24) // 24}T{h % 24:02d}:00") for h in range(72)]
openmeteo = {"/forecast": {"latitude": 10.5, "longitude": 20.25, "hourly": {
    "time": hours, "temperature_2m": [round(22 + 6 * math.sin((h % 24 - 9) / 24 * 2 * math.pi), 1) for h in range(72)],
    "precipitation_probability": [10 if h < 48 else (60 if 60 <= h <= 64 else 20) for h in range(72)],
    "precipitation": [0.0 if h < 60 or h > 64 else 1.2 for h in range(72)],
    "wind_speed_10m": [12.0] * 72, "cloud_cover": [30] * 72}}}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "synthetic.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"_warning": "SYNTHETIC TEST DATA - invented names and times, not real F1 data",
               "jolpica": jolpica, "openf1": openf1, "openmeteo": openmeteo}, fh, indent=1)
print("wrote", out)
