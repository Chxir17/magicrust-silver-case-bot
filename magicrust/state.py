"""Состояние бота в state/state.json.

Ключи:
    last_open     — когда кейс открылся в последний раз
    last_win      — что выпало
    last_status   — итог последней попытки: успех, перезарядка, ошибка
    last_silver   — число из последнего успешного открытия
    silver_total  — сумма за всё время
    history       — последние HISTORY_LEN открытий для /stats
    opens         — счётчик успешных открытий
    next_attempt  — следующая попытка 
"""

from __future__ import annotations

import json
import random
from datetime import timedelta

from .config import HISTORY_LEN, STATE_DIR, STATE_FILE, log
from .fmt import now


def read_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("state.json повреждён, начинаю с чистого состояния")
    return {}


def write_state(**updates) -> dict:
    state = read_state()
    state.update(updates)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def attempt_status(state: dict) -> str:
    return state.get("last_status") or state.get("last_result") or ""


def schedule_next(minutes: int, jitter: int = 5) -> str:
    delay = minutes + random.uniform(0, jitter)
    ts = (now() + timedelta(minutes=delay)).isoformat()
    write_state(next_attempt=ts)
    return ts


def schedule_at(moment) -> None:
    write_state(next_attempt=moment.isoformat())


def record_open(silver, result: str, payload) -> None:
    state = read_state()
    history = (state.get("history") or [])[-(HISTORY_LEN - 1):]
    history.append({"at": now().isoformat(), "silver": silver})
    write_state(
        last_open=now().isoformat(),
        last_win=result,
        last_status=result,
        last_silver=silver,
        silver_total=(state.get("silver_total") or 0) + (silver or 0),
        history=history,
        last_payload=payload,
        opens=state.get("opens", 0) + 1,
    )
