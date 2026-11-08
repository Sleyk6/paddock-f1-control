"""Data sources for PADDOCK F1 CONTROL.

Standard library only. Each call returns an *envelope* that records where the
data came from and whether it was served from cache, so the UI can label it.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Iterable

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
OPENF1_BASE = "https://api.openf1.org/v1"
USER_AGENT = "paddock-f1-control/0.1 (personal, non-commercial)"

# A query parameter is (key, operator, value). Operators: "=", ">=", "<=", ">", "<".
Param = tuple[str, str, str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SourceError(Exception):
    """Raised when a data source cannot provide an answer."""

    def __init__(self, source: str, message: str, status: int | None = None):
        super().__init__(f"{source}: {message}")
        self.source = source
        self.message = message
        self.status = status


def build_query(params: Iterable[Param] | None) -> str:
    """Build a query string. OpenF1 needs raw comparison operators (date>=...)."""
    if not params:
        return ""
    parts = []
    for key, op, value in params:
        if op not in ("=", ">=", "<=", ">", "<"):
            raise ValueError(f"bad operator {op!r}")
        parts.append(f"{urllib.parse.quote(key)}{op}{urllib.parse.quote(str(value), safe=':-.')}")
    return "?" + "&".join(parts)


class DiskCache:
    """JSON file cache. ttl=None means 'keep forever' (finished seasons)."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, hashlib.sha256(key.encode()).hexdigest() + ".json")

    def get(self, key: str, ttl: float | None, allow_stale: bool = False):
        path = self._path(key)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                entry = json.load(fh)
        except (OSError, ValueError):
            return None
        age = time.time() - entry.get("stored", 0)
        if ttl is not None and age > ttl and not allow_stale:
            return None
        return entry

    def set(self, key: str, payload, fetched_at: str) -> None:
        tmp = self._path(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"stored": time.time(), "fetched_at": fetched_at, "payload": payload}, fh)
        os.replace(tmp, self._path(key))


class RateLimiter:
    """Keeps at least `min_interval` seconds between outgoing requests."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def default_fetch(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - fixed https hosts
        return resp.read()


class HttpSource:
    """A cached, rate-limited JSON API."""

    def __init__(self, name: str, base: str, cache: DiskCache, min_interval: float,
                 fetch: Callable[[str, float], bytes] = default_fetch, timeout: float = 20.0):
        self.name = name
        self.base = base
        self.cache = cache
        self.limiter = RateLimiter(min_interval)
        self.fetch = fetch
        self.timeout = timeout
        self.stats = {"requests": 0, "cache_hits": 0, "errors": 0}

    def get(self, path: str, params: Iterable[Param] | None = None, ttl: float | None = 3600) -> dict:
        url = self.base + path + build_query(params)
        entry = self.cache.get(url, ttl)
        if entry is not None:
            self.stats["cache_hits"] += 1
            return {"source": self.name, "url": url, "fetched_at": entry["fetched_at"],
                    "cache": "hit", "data": entry["payload"]}
        self.limiter.wait()
        self.stats["requests"] += 1
        try:
            raw = self.fetch(url, self.timeout)
            payload = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.stats["errors"] += 1
            return self._fallback(url, exc.code, _http_message(exc.code))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.stats["errors"] += 1
            return self._fallback(url, None, f"unreachable ({exc.__class__.__name__})")
        except ValueError:
            self.stats["errors"] += 1
            return self._fallback(url, None, "returned data that is not valid JSON")
        fetched = utc_now_iso()
        self.cache.set(url, payload, fetched)
        return {"source": self.name, "url": url, "fetched_at": fetched, "cache": "miss", "data": payload}

    def _fallback(self, url: str, status: int | None, message: str) -> dict:
        stale = self.cache.get(url, ttl=None, allow_stale=True)
        if stale is not None:
            return {"source": self.name, "url": url, "fetched_at": stale["fetched_at"],
                    "cache": "stale", "warning": message, "data": stale["payload"]}
        raise SourceError(self.name, message, status)


def _http_message(code: int) -> str:
    if code == 404:
        return "no data for this request (404)"
    if code == 429:
        return "rate limit reached (429); wait a minute and retry"
    if code in (401, 403):
        return f"access denied ({code}); this data may need an account"
    return f"HTTP error {code}"


class FixtureSource:
    """Offline synthetic data for tests and demos. Always labelled as fixture."""

    def __init__(self, name: str, table: dict):
        self.name = name
        self.table = table
        self.stats = {"requests": 0, "cache_hits": 0, "errors": 0}

    def get(self, path: str, params: Iterable[Param] | None = None, ttl: float | None = None) -> dict:
        self.stats["requests"] += 1
        endpoint = path.split("?")[0]
        if endpoint not in self.table:
            raise SourceError(self.name, f"no fixture for {endpoint}", 404)
        data = self.table[endpoint]
        if isinstance(data, list) and params:
            data = [row for row in data if all(_match(row, k, op, v) for k, op, v in params)]
        return {"source": f"{self.name} TEST FIXTURE (synthetic)", "url": "fixture:" + endpoint,
                "fetched_at": "fixture", "cache": "fixture", "data": data}


def _match(row: dict, key: str, op: str, value: str) -> bool:
    if key not in row:
        return True
    left, right = str(row[key]), str(value)
    try:
        lnum, rnum = float(left), float(right)
        left, right = lnum, rnum  # type: ignore[assignment]
    except ValueError:
        pass
    return {"=": left == right, ">=": left >= right, "<=": left <= right,
            ">": left > right, "<": left < right}[op]
