"""AI VTuber - Single reusable timezone-aware time utility.

Airi operates on Indian local time.  All "what time is it" style logic
must come from this module - never hardcode UTC offsets like ``UTC+5:30``;
always resolve the zone through :class:`zoneinfo.ZoneInfo`.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, time as _time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

INDIA_TZ_NAME = "Asia/Kolkata"

try:
    INDIA_TZ = ZoneInfo(INDIA_TZ_NAME)
except Exception:  # pragma: no cover - tzdata missing on exotic systems
    logger.warning("[Time] zoneinfo %s unavailable; falling back to UTC",
                   INDIA_TZ_NAME)
    INDIA_TZ = ZoneInfo("UTC")


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
