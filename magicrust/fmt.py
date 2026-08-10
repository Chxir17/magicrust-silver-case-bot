from __future__ import annotations

import os
from datetime import datetime, timezone


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
        return "сейчас"
    hours, rem = divmod(seconds, 3600)
    return f"{hours} ч {rem // 60} мин" if hours else f"{rem // 60} мин"


def local(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        dt = dt.astimezone(ZoneInfo(os.environ.get("MR_TZ", "Europe/Moscow")))
    except Exception:                                      
        dt = dt.astimezone()
    return dt.strftime("%d.%m %H:%M")


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
