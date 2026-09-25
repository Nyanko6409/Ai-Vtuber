"""AI VTuber - Single reusable timezone-aware time utility.

Airi operates on Indian local time.  All "what time is it" style logic
must come from this module - never hardcode UTC offsets like ``UTC+5:30``;
always resolve the zone through :class:`zoneinfo.ZoneInfo`.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, time as _time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

INDIA_TZ_NAME = "Asia/Kolkata"


def _resolve_zone(name: str) -> Optional[ZoneInfo]:
    """Resolve a named timezone, trying several sources in order.

    On Windows the system IANA tz database is usually absent, so
    ``zoneinfo`` needs the ``tzdata`` PyPI package.  If it is not
    installed we attempt a lazy install (pip may be blocked by an
    externally-managed environment, hence the try/except) and retry.
    Returns ``None`` only if every strategy fails.
    """
    try:
        return ZoneInfo(name)
    except Exception:
        pass

    # Try to auto-install the tzdata package, then retry.
    try:
        import importlib
        import subprocess
        import sys

        logger.info(
            "[Time] IANA tz database missing; attempting `pip install tzdata`"
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "tzdata"],
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        importlib.invalidate_caches()
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    except Exception as exc:  # pip blocked, offline, externally-managed...
        logger.debug("[Time] tzdata auto-install failed: %s", exc)

    return None


def _fixed_offset_fallback() -> Any:
    """Last-resort tzinfo for India when no IANA data exists anywhere.

    India has had a constant UTC+05:30 offset since 1962 (no DST), so a
    ``datetime.timezone`` is exact for wall-clock purposes.  This path is
    only taken on systems where even the ``tzdata`` PyPI package cannot be
    installed, and it still returns timezone-aware datetimes.
    """
    from datetime import timezone

    return timezone(timedelta(hours=5, minutes=30), name=INDIA_TZ_NAME)


try:
    INDIA_TZ = _resolve_zone(INDIA_TZ_NAME)
except Exception:  # pragma: no cover - defensive (e.g. no UTC zone either)
    INDIA_TZ = None

if INDIA_TZ is None:  # pragma: no cover - truly exotic systems
    logger.warning(
        "[Time] Could not load IANA zone %s (missing system tz database and "
        "`tzdata` package). Falling back to fixed IST offset. "
        "Fix with: pip install tzdata",
        INDIA_TZ_NAME,
    )
    INDIA_TZ = _fixed_offset_fallback()
else:
    logger.info("[Time] Current timezone: %s", INDIA_TZ_NAME)


def now_india() -> datetime:
    """Current time as a timezone-aware datetime in Asia/Kolkata."""
    return datetime.now(INDIA_TZ)


# Friendly aliases -------------------------------------------------------
current_india_datetime = now_india


def current_india_date() -> _date:
    """Today's calendar date in India."""
    return now_india().date()


def current_india_time() -> _time:
    """Current wall-clock time in India."""
    return now_india().time()


def india_timestamp(dt: datetime | None = None) -> str:
    """'YYYY-MM-DD HH:MM:SS' wall-clock stamp in India time."""
    return (dt or now_india()).strftime("%Y-%m-%d %H:%M:%S")


def india_time_of_day_phrase(dt: datetime | None = None) -> str:
    """Coarse phrase: morning / afternoon / evening / night."""
    h = (dt or now_india()).hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 21:
        return "evening"
    return "night"


def build_current_time_block(dt: datetime | None = None) -> str:
    """Dynamic CURRENT TIME block injected into the LLM context.

    Generated fresh per turn - never written permanently into soul.md.
    Gives Airi reliable awareness of the Indian date/time so questions
    like "What time is it?" / "Is it morning?" / "What did we talk about
    yesterday?" can be answered without trusting model priors.
    """
    dt = dt or now_india()
    return (
        "CURRENT TIME\n"
        f"Timezone: {INDIA_TZ_NAME}\n"
        f"Date: {dt.strftime('%A, %B %d, %Y')}\n"
        f"Time: {dt.strftime('%H:%M:%S')}\n"
        f"It is currently {india_time_of_day_phrase(dt)} in India."
    )


__all__ = [
    "INDIA_TZ",
    "INDIA_TZ_NAME",
    "now_india",
    "current_india_datetime",
    "current_india_date",
    "current_india_time",
    "india_timestamp",
    "india_time_of_day_phrase",
    "build_current_time_block",
]
