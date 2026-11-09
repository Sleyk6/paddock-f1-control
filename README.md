# PADDOCK F1 CONTROL

A personal Formula 1 data dashboard that runs on your own computer. It shows the race calendar, standings, results, a two-driver lap comparison, tyre strategy and pit stops, and single-lap telemetry (speed, throttle, brake, gear).

**Status:** v0.2.0. Live data verified on the founder PC with v0.1.0; v0.2 features are tested with synthetic data. See CHANGELOG.

## Requirements
- Python 3.10 or newer. Nothing to `pip install`: it uses the standard library only.
- An internet connection, for the free public APIs [Jolpica-F1](https://github.com/jolpica/jolpica-f1) and [OpenF1](https://openf1.org).

## Run it (Windows PowerShell, inside this folder)
```powershell
py -m f1control.server
```
Then open http://127.0.0.1:8301 in your browser. Press Ctrl+C in PowerShell to stop it.

Offline demo with invented data (a red banner says so):
```powershell
py -m f1control.server --fixtures
```

Run the tests:
```powershell
py -m unittest discover -s tests -v
```

## How the data is labelled
Every page shows chips saying where the data came from and how fresh it is:
- **HISTORICAL**: a finished season. Cached forever, because it never changes.
- **RECENT**: the current season. Cached for 1 hour, and may still change.
- **cached / fresh / STALE**: whether it came from the local cache, a new request, or an old cache copy used because the source was down.
- **TEST FIXTURE**: synthetic data, never real.

Nothing is shown as **live**. Real-time timing from OpenF1 needs a paid or sponsored token, which this version does not use.

## Data coverage
| Feature | Source | Seasons |
|---|---|---|
| Calendar, standings, results, lap times, pit stops | Jolpica-F1 | 1950 onward (lap times from 1996) |
| Tyre stints, telemetry | OpenF1 | 2023 onward |

Unofficial personal project, not affiliated with Formula 1 companies. No F1 logos or official graphics are used.
Built with AI assistance (Claude), reviewed and run by the founder.
