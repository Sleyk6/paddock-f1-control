# Changelog

## 0.6.3 (2026-11-09)
- **Stays current by itself.** The page opens on the most recent race that has happened, instead of round 1.
- Every hour (and when you come back to the tab after an hour away) it re-pulls the calendar, countdown and the page you are on, and moves to the newest race if one has finished. The footer shows "updated <day> <time>".
- Picking a race yourself turns the auto-jump off until you reload, so it never yanks you away mid-analysis; a running Live drill replay is never interrupted.
- The server now follows the clock for "current season", so leaving it running over New Year needs no restart.

## 0.6.2 (2026-11-09)
- Drivers who switched teams mid-season are now shown with the team from their latest race (standings data alone could list the old team).
- Status chips grouped by source, with a request count and the newest fetch time.
- Long driver names no longer clip on the podium cards.

## 0.6.1 (2026-11-09)
- Team colours everywhere (standings, constructors, points, results): official OpenF1 colours for the season's latest session, built-in fallback otherwise.
- Points chart: teammates share a colour, second driver dashed.
- Cross-check: flags a driver whose team differs between Jolpica results and the latest OpenF1 session.

## 0.6.0 (2026-11-09)
- Countdown bar to the next real session (practice, sprint, qualifying, race) with flag and lights-out time; flashes LIVE during a session.
- Calendar API now includes each weekend's session times.

## 0.5.1 (2026-11-09)
- Tyre icons (original design: tyre with compound-coloured ring and S/M/H/I/W letter) with stint lengths in Results; also in the Planner tyre model table.

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
