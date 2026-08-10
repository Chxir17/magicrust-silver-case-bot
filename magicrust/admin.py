"""Операции, которые бот выполняет по команде из Telegram.

Обычные действия (`run`, `status`, `timer`) выполняются от имени magicrust.
Привилегированные (`restart`, `update`) уходят через `sudo magicrust-admin` —
отдельный root-скрипт с двумя разрешёнными действиями. Пока не выполнен
scripts/enable-remote-admin.sh, они возвращают понятный отказ.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .config import ROOT, log

BOT = str(ROOT / "bot.py")
ADMIN = "/usr/local/sbin/magicrust-admin"
LIMIT = 3500                                    # запас до предела сообщения Telegram


def run_command(argv: list[str], timeout: int = 600) -> str:
    """Запускает команду и возвращает её вывод в виде текста для чата."""
    log.info("выполняю по команде из Telegram: %s", " ".join(argv))
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT)
        )
    except FileNotFoundError:
        return f"Не найдено: {argv[0]}"
    except subprocess.TimeoutExpired:
        return f"Команда не уложилась в {timeout} с и была прервана."

    output = (done.stdout + done.stderr).strip() or "(без вывода)"
    if len(output) > LIMIT:
        output = "…\n" + output[-LIMIT:]
    return f"{output}\n\nКод возврата: {done.returncode}"


def attempt(force: bool) -> str:
    argv = [sys.executable, BOT, "run"] + (["--force"] if force else [])
    return run_command(argv)


def status() -> str:
    return run_command([sys.executable, BOT, "status"])


def timer() -> str:
    return run_command(
        ["systemctl", "list-timers", "magicrust-case.timer", "--no-pager"], timeout=30
    )


def restart() -> str:
    return privileged("restart")


def update() -> str:
    return privileged("update")


def privileged(action: str) -> str:
    """Действие через root-помощник. Без него — инструкция, а не ошибка."""
    if not os.path.exists(ADMIN):
        return (
            "Команда требует прав root, помощник не установлен.\n"
            "Выполните на сервере:\n"
            "sudo /opt/magicrust-bot/scripts/enable-remote-admin.sh"
        )
    return run_command(["sudo", "-n", ADMIN, action])


def import_cookies(path: str) -> str:
    return run_command([sys.executable, BOT, "import-cookies", path])
