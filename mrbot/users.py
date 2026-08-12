from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .config import STATE_DIR, USERS_DIR, USERS_FILE, log
from .fmt import now


@dataclass(frozen=True)
class Account:
    """Один игрок: свой профиль браузера, своё состояние, свой чат."""

    chat_id: str = ""
    name: str = ""

    @property
    def dir(self) -> Path:
        # Без chat_id — одиночный режим на своей машине (state/ как раньше).
        return USERS_DIR / self.chat_id if self.chat_id else STATE_DIR

    @property
    def profile_dir(self) -> Path:
        return self.dir / "profile"

    @property
    def state_file(self) -> Path:
        return self.dir / "state.json"

    @property
    def title(self) -> str:
        if not self.chat_id:
            return "локальный профиль"
        return f"{self.name} ({self.chat_id})" if self.name else self.chat_id


#  Реестр доступа

def read_registry() -> dict:
    """{"users": {chat_id: {...}}, "pending": {chat_id: {...}}}"""
    if USERS_FILE.exists():
        try:
            data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("users", {})
                data.setdefault("pending", {})
                return data
            log.warning("users.json не похож на реестр, начинаю с пустого списка")
        except json.JSONDecodeError:
            log.warning("users.json повреждён, начинаю с пустого списка")
    return {"users": {}, "pending": {}}


def write_registry(registry: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    USERS_FILE.chmod(0o600)


def admin_ids() -> list[str]:
    """TG_CHAT_ID из .env: один id или несколько через запятую."""
    raw = (os.environ.get("TG_CHAT_ID") or "").replace(";", ",")
    return [part.strip() for part in raw.split(",") if part.strip()]


def is_admin(chat_id) -> bool:
    return str(chat_id) in admin_ids()


def accounts() -> list[Account]:
    registry = read_registry()
    return [
        Account(chat_id, entry.get("name", ""))
        for chat_id, entry in registry["users"].items()
    ]


def resolve(chat_id) -> Account | None:
    """Аккаунт по chat_id или None, если доступа нет."""
    chat_id = str(chat_id)
    entry = read_registry()["users"].get(chat_id)
    if entry is not None:
        return Account(chat_id, entry.get("name", ""))
    # Админ из конфига имеет доступ, даже если реестр ещё не создан.
    return Account(chat_id, "администратор") if is_admin(chat_id) else None


def default() -> Account:
    """Кого берут команды в терминале, если не указан --user."""
    ids = admin_ids()
    return Account(ids[0], "администратор") if ids else Account()


def add(chat_id, name: str = "", username: str = "", by: str = "") -> bool:
    """Выдаёт доступ. False — если доступ уже был."""
    chat_id = str(chat_id)
    registry = read_registry()
    known = chat_id in registry["users"]
    if not known:
        registry["users"][chat_id] = {
            "name": name,
            "username": username,
            "added_at": now().isoformat(),
            "added_by": str(by),
        }
    registry["pending"].pop(chat_id, None)
    write_registry(registry)
    Account(chat_id, name).dir.mkdir(parents=True, exist_ok=True)
    if not known:
        log.info("доступ выдан: %s (пригласил %s)", chat_id, by or "конфиг")
    return not known


def remove(chat_id) -> bool:
    """Забирает доступ и стирает сессию игрока. False — если такого не было."""
    chat_id = str(chat_id)
    registry = read_registry()
    if chat_id not in registry["users"] and chat_id not in registry["pending"]:
        return False
    registry["users"].pop(chat_id, None)
    registry["pending"].pop(chat_id, None)
    write_registry(registry)

    folder = Account(chat_id).dir
    if chat_id and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    log.info("доступ отозван: %s, данные удалены", chat_id)
    return True


def remember_request(chat_id, name: str, username: str) -> bool:
    """Записывает заявку. True — если она новая и о ней стоит сообщить админу."""
    chat_id = str(chat_id)
    registry = read_registry()
    fresh = chat_id not in registry["pending"]
    registry["pending"][chat_id] = {
        "name": name,
        "username": username,
        "at": now().isoformat(),
    }
    write_registry(registry)
    if fresh:
        log.info("заявка на доступ: %s %s", chat_id, name)
    return fresh


def pending() -> dict:
    return read_registry()["pending"]


#  Текущий аккаунт

_current: Account | None = None


def current() -> Account:
    return _current if _current is not None else default()


@contextmanager
def use(account: Account):
    """Внутри блока состояние, профиль и уведомления принадлежат этому игроку."""
    global _current
    previous = _current
    _current = account
    account.dir.mkdir(parents=True, exist_ok=True)
    try:
        yield account
    finally:
        _current = previous


#  Подготовка каталога state/

def bootstrap() -> None:
    registry = read_registry()
    changed = False
    for chat_id in admin_ids():
        if chat_id not in registry["users"]:
            registry["users"][chat_id] = {
                "name": "администратор",
                "username": "",
                "added_at": now().isoformat(),
                "added_by": "конфиг",
            }
            changed = True
    if changed:
        write_registry(registry)
    migrate_legacy()


def migrate_legacy() -> None:
    """Переносит состояние старого одиночного бота в аккаунт администратора."""
    ids = admin_ids()
    if not ids:
        return
    owner = Account(ids[0], "администратор")
    moves = [
        (STATE_DIR / "state.json", owner.state_file),
        (STATE_DIR / "profile", owner.profile_dir),
    ]
    if not any(source.exists() and not target.exists() for source, target in moves):
        return

    owner.dir.mkdir(parents=True, exist_ok=True)
    for source, target in moves:
        if not source.exists() or target.exists():
            continue
        try:
            shutil.move(str(source), str(target))
        except OSError as exc:
            # Второй процесс мог успеть первым — это не беда.
            log.warning("не перенёс %s: %s", source.name, exc)
            continue
        log.info("перенёс %s в аккаунт администратора %s", source.name, owner.chat_id)
