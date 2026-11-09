# Changelog

## 0.5.0 (2026-11-09)
- **Car tracker:** in Live drill, every car is a team-coloured dot with its code, moving around the track map from OpenF1 position data (1 fix per second, smoothed; loaded 2 minutes at a time). Cars in the garage disappear.
- Live drill can also replay the Race and Sprint.

## 0.4.0 (2026-11-09)
- **Live drill:** replays a finished qualifying or practice session on a simulated clock (10x-120x). Timing tower updates as laps finish (new bests flash purple), race-control feed, and the track map flashes yellow/red/green with track status. Always labelled SIMULATION.

## 0.3.0 (2026-11-09)
- **Weekend tab:** session list, practice best laps with gaps (OpenF1), qualifying Q1/Q2/Q3 (Jolpica), Open-Meteo weather forecast for the weekend (temperature, rain chance, race-start conditions), measured track and air temperature for finished races.
- Clear "server is not running" message instead of "Failed to fetch".

## 0.2.2 (2026-11-09)
- Auto-retry when a data source rate-limits (429) or hiccups (502-504), honouring Retry-After; OpenF1 spacing 0.6 s.

## 0.2.1 (2026-11-09)
- Results detail: driver nationality flags, places gained/lost from grid, purple fastest lap, per-driver tyre stint strip, team-colour row accents and chips. More simplified flags (Thailand, Denmark, Finland, New Zealand, Argentina and others). No team logos or driver photos (trademarks / real-person images).

## 0.2.0 (2026-11-09)
- **Cinematic HUD redesign:** glass panels, glow, scanlines, a one-time intro animation (off for reduced motion), Bahnschrift display font.
- **Strategy Planner:** fits tyre wear and compound pace from the race's real laps (with a driver-pace correction), simulates every legal 1- and 2-stop plan for your tyre allocation, ranks them, and checks the model against the winner's real race time.
- **Points tracker:** points by round for the top 10, gap to the leader, max points left, and who can still mathematically win.
- **Hero track mini-map** traced from OpenF1 car positions (races not yet run use the last race at that circuit), plus a simplified country flag.
- **Track-status light:** green / yellow / SC / VSC / red / chequered from race-control messages, for the selected lap (replay; real-time needs paid OpenF1 access), and a lap-by-lap status strip.
- **Driver cards:** car-number plates in team colours (no photos), podium cards.
- **Clocks:** Zulu (UTC), local and Washington DC.
- Opens on the current season by default (2026), not 2024.
- Tests: 34.

## 0.1.0 (2026-11-08)
- First prototype: calendar, standings, results, compare, strategy, telemetry.
- Disk cache with TTL and stale fallback; rate limiting; data-kind labels.
- Synthetic fixture mode for offline demos and tests; 22 unit/integration tests.
