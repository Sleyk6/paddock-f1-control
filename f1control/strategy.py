"""Tyre-strategy projection (F1 Manager-style race planner, built from real lap data).

MODEL, NOT FACT. Steps:
1. Fit, per dry compound, a pace offset and a degradation rate (s/lap of tyre age) from the
   real race's clean laps (OpenF1 laps + stints), after removing a fuel-burn effect.
2. Simulate every legal 1- and 2-stop plan the given tyre allocation allows
   (dry race rule: at least two different dry compounds), choosing the best pit laps.
3. Validate: run the winner's real compound sequence through the model and compare with
   their real race time.

Simplifications are stated in the output: no traffic, safety cars, track evolution,
weather or driver differences; linear wear plus a penalty past the longest stint seen.
"""
from __future__ import annotations

import statistics
from itertools import product

DRY = ("SOFT", "MEDIUM", "HARD")


def fit_compounds(laps: list[dict], stints: list[dict], fuel_gain: float) -> dict:
    """laps: OpenF1 laps rows; stints: OpenF1 stints rows. Returns per-compound model."""
    by_driver = {}
    for lap in laps:
        if lap.get("lap_duration") and lap.get("lap_number"):
            by_driver.setdefault(lap["driver_number"], {})[lap["lap_number"]] = lap
    all_times = [lap["lap_duration"] for d in by_driver.values() for lap in d.values()]
    if not all_times:
        return {}
    median_all = statistics.median(all_times)
    groups: dict[str, list[list[tuple[float, float]]]] = {}
    for s in stints:
        comp = str(s.get("compound") or "").upper()
        if comp not in DRY or s.get("lap_start") is None or s.get("lap_end") is None:
            continue
        rows = []
        for n in range(s["lap_start"] + 1, s["lap_end"]):  # skip out-lap and in-lap
            lap = by_driver.get(s["driver_number"], {}).get(n)
            if not lap or lap.get("is_pit_out_lap") or n == 1:
                continue
            t = lap["lap_duration"]
            if t > median_all * 1.07:  # safety car, VSC, traffic, mistakes
                continue
            age = (s.get("tyre_age_at_start") or 0) + (n - s["lap_start"])
            rows.append((age, t + fuel_gain * (n - 1)))  # fuel-corrected time
        if len(rows) >= 4:
            groups.setdefault(comp, []).append((s["driver_number"], rows))
    model = {}
    slopes = {}
    for comp, stint_rows in groups.items():
        num = den = 0.0
        for _, rows in stint_rows:
            ma = statistics.fmean(a for a, _ in rows)
            mt = statistics.fmean(t for _, t in rows)
            num += sum((a - ma) * (t - mt) for a, t in rows)
            den += sum((a - ma) ** 2 for a, _ in rows)
        slopes[comp] = max(num / den, 0.0) if den else 0.0
    # Separate car/driver pace from compound pace: y = driver_effect + compound_base (alternating fit).
    obs = [(drv, comp, t - slopes[comp] * a) for comp, srows in groups.items() for drv, rows in srows for a, t in rows]
    eff = {drv: 0.0 for drv, _, _ in obs}
    base = {}
    for _ in range(25):
        base = {c: statistics.fmean(y - eff[d] for d, cc, y in obs if cc == c) for c in groups}
        eff = {d: statistics.fmean(y - base[c] for dd, c, y in obs if dd == d) for d in eff}
        shift = statistics.fmean(eff.values())
        eff = {d: v - shift for d, v in eff.items()}
    for comp, stint_rows in groups.items():
        rows_only = [rows for _, rows in stint_rows]
        model[comp] = {"base": round(base[comp] + statistics.fmean(eff.values()), 3), "deg": round(slopes[comp], 4),
                       "max_life_seen": max(max(a for a, _ in rows) for rows in rows_only),
                       "stints": len(rows_only), "laps": sum(len(r) for r in rows_only)}
    if model:
        fastest = min(m["base"] for m in model.values())
        for m in model.values():
            m["offset"] = round(m["base"] - fastest, 3)
    return model


def stint_time(m: dict, first_lap: int, n_laps: int, fuel_gain: float, cliff_factor: float) -> tuple[float, list]:
    total, trace = 0.0, []
    for i in range(n_laps):
        age = i + 1
        wear = m["deg"] * age
        over = age - m["max_life_seen"]
        if over > 0:  # beyond anything observed: assume wear accelerates
            wear += m["deg"] * cliff_factor * over
        lap = first_lap + i
        t = m["base"] + wear - fuel_gain * (lap - 1)
        total += t
        trace.append(round(t, 3))
    return total, trace


def simulate(seq: tuple, stops: tuple, race_laps: int, model: dict, pit_loss: float, fuel_gain: float,
             cliff_factor: float) -> tuple[float, list]:
    bounds = (0,) + stops + (race_laps,)
    total, trace = 0.0, []
    for i, comp in enumerate(seq):
        t, tr = stint_time(model[comp], bounds[i] + 1, bounds[i + 1] - bounds[i], fuel_gain, cliff_factor)
        total += t
        trace += tr
    return total + pit_loss * len(stops), trace


def legal_sequences(allocation: dict, max_stops: int = 2) -> list[tuple]:
    out = []
    for n in range(2, max_stops + 2):
        for seq in product(DRY, repeat=n):
            if len(set(seq)) < 2:
                continue  # dry race rule: two different compounds
            if any(seq.count(c) > allocation.get(c, 0) for c in DRY):
                continue  # not enough sets of that compound
            out.append(seq)
    return out


def best_stops(seq: tuple, race_laps: int, model: dict, pit_loss: float, fuel_gain: float,
               cliff_factor: float, min_stint: int = 5):
    # The fuel term is identical for every plan, so the search uses wear-only stint costs
    # (prefix sums, O(1) per candidate); the final total is recomputed in full by simulate().
    cost = {}
    for comp in set(seq):
        cum, acc = [0.0], 0.0
        for length in range(1, race_laps + 1):
            acc += stint_time(model[comp], 1, 1, 0.0, cliff_factor)[0] + _wear_extra(model[comp], length, cliff_factor)
            cum.append(acc)
        cost[comp] = cum
    best = None
    if len(seq) == 2:
        candidates = ((a,) for a in range(min_stint, race_laps - min_stint + 1))
    else:
        candidates = ((a, b) for a in range(min_stint, race_laps) for b in range(a + min_stint, race_laps - min_stint + 1))
    for stops in candidates:
        bounds = (0,) + stops + (race_laps,)
        total = sum(cost[c][bounds[i + 1] - bounds[i]] for i, c in enumerate(seq))
        if best is None or total < best[0]:
            best = (total, stops)
    if best is None:
        return None
    return simulate(seq, best[1], race_laps, model, pit_loss, fuel_gain, cliff_factor)[0], best[1]


def _wear_extra(m: dict, age: int, cliff_factor: float) -> float:
    """Wear at tyre age `age` minus the wear at age 1 (so lap costs add up correctly)."""
    def wear(a):
        w = m["deg"] * a
        if a > m["max_life_seen"]:
            w += m["deg"] * cliff_factor * (a - m["max_life_seen"])
        return w
    return wear(age) - wear(1)


def project(model: dict, race_laps: int, allocation: dict, pit_loss: float, fuel_gain: float,
            cliff_factor: float = 2.0, top: int = 8) -> list[dict]:
    plans = []
    for seq in legal_sequences(allocation):
        if any(c not in model for c in seq):
            continue
        found = best_stops(seq, race_laps, model, pit_loss, fuel_gain, cliff_factor)
        if not found:
            continue
        total, stops = found
        _, trace = simulate(seq, stops, race_laps, model, pit_loss, fuel_gain, cliff_factor)
        bounds = (0,) + stops + (race_laps,)
        plans.append({"sequence": list(seq), "stops": len(stops), "pit_laps": list(stops), "total": round(total, 3),
                      "stints": [{"compound": c, "from": bounds[i] + 1, "to": bounds[i + 1],
                                  "laps": bounds[i + 1] - bounds[i]} for i, c in enumerate(seq)],
                      "trace": trace})
    plans.sort(key=lambda p: p["total"])
    if plans:
        for p in plans:
            p["delta"] = round(p["total"] - plans[0]["total"], 3)
    return plans[:top]
