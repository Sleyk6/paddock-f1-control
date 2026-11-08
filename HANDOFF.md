# Handoff

**State (2026-11-08):** v0.1.0 built by Claude in a cloud workspace. 22 tests pass. The UI was checked with Playwright in fixture mode, with no console errors and no horizontal scroll at 390 px width.

**Not verified:** live Jolpica/OpenF1 calls. The build workspace's network allowlist blocked those hosts.

**Next action (founder, main PC):** `py --version` (needs 3.10+), then `py -m f1control.server`, open http://127.0.0.1:8301, and load 2024 round 1. Report any red error box.
