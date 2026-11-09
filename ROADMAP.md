# Roadmap

## Done
- v0.1: calendar, standings, results, lap compare, stints and pit stops, telemetry, data labels, cache, tests.
- v0.2.x: HUD redesign, Planner (tyre projection), Points tracker, track mini-map, flags, race-control status light (replay), results detail, clocks, retries.

## Now: verify on the founder PC
- [ ] Planner, Results detail and Telemetry status light confirmed on a finished 2026 race (Round 19 or earlier)
- [ ] Friendlier "server not running" message instead of "Failed to fetch"

## Founder requirement (2026-11-08): LIVE WEEKEND MODE
When a session is live, the page must:
- [ ] **Flash the track-status colour on the track map** (green / yellow / SC / VSC / red / chequered) as the status changes
- [ ] **Show practice and qualifying times** (FP1-FP3, sprint qualifying, qualifying: best laps, gaps, sector times)
- [ ] **Show a weather projection** for the session and race (forecast plus current track and air temperature, rain chance)

Data notes:
- True real-time status and timing needs paid OpenF1 access (founder decision; costs money). The free tier publishes after each session, so the free build polls and updates as soon as data appears.
- Practice and qualifying come from OpenF1 sessions/laps; Jolpica also has qualifying results.
- Track weather comes from OpenF1 `weather`. The forecast needs a free weather API (e.g. Open-Meteo, no key) using the circuit's coordinates.

## Next
- [ ] SPORTSCARS tab (WEC/ELMS/IMSA) from the open tobil/imsa dataset, via a one-time import script the founder runs
- [ ] Sector times and a lap-by-lap position chart; two-driver telemetry overlay
- [ ] Optional team image slot (founder-supplied files only)
- [ ] Optional FastF1 module (main PC only)

## Later
- [ ] NASCAR / IndyCar if a paid data key is approved
- [ ] Host on paddock in its own small container after the main-PC version is verified
