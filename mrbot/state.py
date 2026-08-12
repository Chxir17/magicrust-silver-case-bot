from __future__ import annotations

import fcntl
import json
import random
import time
from contextlib import contextmanager
from datetime import timedelta

from . import users
from .config import HISTORY_LEN, STATE_DIR, log
from .fmt import now


@contextmanager
def single_run(wait: int = 0):
    """Один Chromium на весь бот: остальные ждут `wait` секунд или уходят."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(STATE_DIR / "run.lock", "w")
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                raise RuntimeError("другая попытка уже выполняется") from None
            time.sleep(2)
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def read_state(account: users.Account | None = None) -> dict:
    path = (account or users.current()).state_file
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("state.json повреждён, начинаю с чистого состояния")
    return {}


def write_state(**updates) -> dict:
    account = users.current()
    state = read_state(account)
    state.update(updates)
    account.dir.mkdir(parents=True, exist_ok=True)
    account.state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
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
