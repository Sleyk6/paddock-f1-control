# Changelog

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
