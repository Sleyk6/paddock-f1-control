# Handoff

**State (2026-11-09):** v0.2.0. 34 tests pass. Every tab was checked with Playwright in fixture mode: no page errors, and no horizontal scroll at 390 px.

**Verified on PC:** v0.1.0 ran in live mode on the founder PC (Python 3.14.6) on 2026-11-08, and real data loaded.

**Not verified:** the v0.2 live run on the PC. That covers the projection on real 2026 races, track maps from real OpenF1 location data, and race-control status.

**Next action (founder):** stop and restart `py -m f1control.server`, open http://127.0.0.1:8301, then try Points, Planner, and Telemetry (watch the status light).
