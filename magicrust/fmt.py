from __future__ import annotations

import os
from datetime import datetime, timezone

from .texts import Time


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def human_delta(dt: datetime) -> str:
    seconds = int((dt - now()).total_seconds())
    if seconds <= 0:
        return Time.NOW
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return Time.HOURS_MINUTES.format(hours=hours, minutes=minutes)
    return Time.MINUTES.format(minutes=minutes)


def local(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        dt = dt.astimezone(ZoneInfo(os.environ.get("MR_TZ", "Europe/Moscow")))
    except Exception:                                      
        dt = dt.astimezone()
    return dt.strftime(Time.DATE_FORMAT)


def plural(count: int, one: str, few: str, many: str) -> str:
    tail = abs(int(count)) % 100
    if 11 <= tail <= 14:
        return many
    tail %= 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def amount(value) -> str:
    if value is None:
        return "?"
    number = int(value) if float(value).is_integer() else value
    return f"{number:,}".replace(",", " ") if isinstance(number, int) else str(number)
