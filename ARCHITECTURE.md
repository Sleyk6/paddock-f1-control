# Architecture

```
Browser (static/index.html, app.js, style.css: plain JS + SVG charts)
   |  HTTP on 127.0.0.1:8301 (local only)
f1control/server.py   routes /api/*, input validation, security headers, timing
f1control/service.py  turns raw API JSON into small UI-ready shapes; labels data kind
f1control/sources.py  HttpSource (rate limit + disk cache + stale fallback) | FixtureSource (tests)
   |  HTTPS
Jolpica-F1 (schedule, standings, results, laps, pit stops)   OpenF1 (sessions, stints, laps, car_data)
```

## Design choices
- **Standard library only:** no dependency installs and no supply-chain risk, and it runs anywhere with Python 3.10+.
- **The server is a proxy plus cache:** the browser never calls the APIs directly. This avoids CORS problems, respects rate limits (Jolpica 4 req/s burst / 500 per hour) and makes repeat views instant.
- **Cache policy:** finished seasons are cached forever, the current season for 1 hour. If a source is down, the old copy is served and marked STALE.
- **Every response has `meta`:** data_kind, sources (with url, fetched_at and cache state), notes and server_ms.
- **Telemetry:** finds the OpenF1 race session by matching the race date, gets that lap's start time and duration, then requests `car_data` in that time window. The result is downsampled to 400 points or fewer.

## API
| Endpoint | Params |
|---|---|
| `/api/health` | none |
| `/api/calendar` | season |
| `/api/standings` | season |
| `/api/results` | season, round |
| `/api/compare` | season, round, a, b (Jolpica driver ids) |
| `/api/strategy` | season, round |
| `/api/telemetry` | season, round, driver (car number), lap |

JARVIS uses these same endpoints (see paddock-jarvis).
