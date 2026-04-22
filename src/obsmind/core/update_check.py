"""Check PyPI for a newer version of obsmind.

Fetches the PyPI JSON API once per 24 hours; result is cached in
~/.obsmind/update-cache.json. Returns a hint string when behind, else None.
Never raises — update check failures are swallowed silently.
"""

import json
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

from .. import __version__

_CACHE_FILE = Path.home() / ".obsmind" / "update-cache.json"
_CACHE_TTL  = 86_400  # 24 hours
_PYPI_URL   = "https://pypi.org/pypi/obsmind/json"


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def check() -> str | None:
    """Return an upgrade hint string if a newer version is available, else None."""
    try:
        return _check()
    except Exception:
        return None


def _check() -> str | None:
    latest = _cached_latest()
    if latest is None:
        latest = _fetch_latest()
        if latest:
            _write_cache(latest)

    if latest is None:
        return None

    if _parse_version(latest) > _parse_version(__version__):
        return (
            f"Update available: {__version__} → {latest}\n"
            f"  Run: pip install --upgrade obsmind"
        )
    return None


def _cached_latest() -> str | None:
    try:
        if not _CACHE_FILE.exists():
            return None
        data = json.loads(_CACHE_FILE.read_text())
        if time.time() - data.get("fetched_at", 0) > _CACHE_TTL:
            return None
        return data.get("latest")
    except Exception:
        return None


def _fetch_latest() -> str | None:
    try:
        with urlopen(_PYPI_URL, timeout=3) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except (URLError, KeyError, json.JSONDecodeError, OSError):
        return None


def _write_cache(latest: str) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps({"latest": latest, "fetched_at": time.time()}))
    except OSError:
        pass
