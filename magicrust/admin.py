"""Операции, которые бот выполняет по команде из Telegram.

Обычные действия (`run`, `status`, `timer`) выполняются от имени magicrust.
Привилегированные (`restart`, `update`) уходят через `sudo magicrust-admin` —
отдельный root-скрипт с двумя разрешёнными действиями. Пока не выполнен
scripts/enable-remote-admin.sh, они возвращают понятный отказ.

Ответы отсюда идут человеку в чат, а не в журнал: служебные префиксы строк
срезаются, код возврата показывается только при ошибке.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from .config import ROOT, log
from .fmt import human_delta, local, now, parse_dt
from .state import attempt_status, read_state

BOT = str(ROOT / "bot.py")
ADMIN = "/usr/local/sbin/magicrust-admin"
LIMIT = 3500                                    # запас до предела сообщения Telegram

# «2026-08-11 01:17:59  INFO    текст» -> «текст»
LOG_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+\w+\s+", re.M)

# Как только не напишут «сделай всё равно»: принимаем любой из вариантов.
FORCE_WORDS = {"force", "--force", "-f", "now", "сейчас", "давай"}

# Строки прогресса, которые полезны в журнале, но не в переписке.
NOISE = re.compile(r"^(запускаю Chromium|HEADLESS=0)")


def strip_log_prefix(text: str) -> str:
    return LOG_PREFIX.sub("", text).strip()


def execute(argv: list[str], timeout: int = 600) -> tuple[int | None, str]:
    """Запускает команду и возвращает код возврата и очищенный вывод.

    Код возврата — надёжнее разбора текста: bot.py возвращает 0 при успехе или
    перезарядке, 2 если сессия умерла, 3 при непонятном ответе сайта.
    """
    log.info("выполняю по команде из Telegram: %s", " ".join(argv))
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT)
        )
    except FileNotFoundError:
        return None, f"Не нашёл программу {argv[0]}"
    except subprocess.TimeoutExpired:
        return None, f"Команда не уложилась в {timeout // 60} мин и была прервана."

    output = strip_log_prefix(done.stdout + done.stderr)
    if len(output) > LIMIT:
        output = "…\n" + output[-LIMIT:]
    return done.returncode, output


def run_command(argv: list[str], timeout: int = 600) -> str:
    """То же, но одной строкой для чата: код показываем только при ошибке."""
    code, output = execute(argv, timeout)
    output = output or "Готово."
    if code:
        output += f"\n\nКоманда завершилась с ошибкой (код {code})."
    return output


def attempt(args: list[str]) -> str:
    """Попытка открыть кейс. Итог берём из состояния, а не из вывода процесса."""
    force = any(word.lower() in FORCE_WORDS for word in args)

    state = read_state()
    nxt = parse_dt(state.get("next_attempt"))
    if not force and nxt and nxt > now():
        return (
            f"Ещё рано: следующая попытка {local(nxt)}, через {human_delta(nxt)}.\n"
            "Открыть прямо сейчас — /run force"
        )

    was_open = state.get("last_open")
    code, raw = execute([sys.executable, BOT, "run"] + (["--force"] if force else []))
    fresh = read_state()

    following = parse_dt(fresh.get("next_attempt"))
    when = (
        f"\nСледующая попытка {local(following)}, через {human_delta(following)}."
        if following and following > now()
        else ""
    )

    if fresh.get("last_open") != was_open:
        return f"Кейс открыт — {fresh.get('last_win', 'без подробностей')}." + when
    if code == 2:
        return "Не вышло: сессия истекла, нужен повторный вход. Как это сделать — /login"
    if code == 0 and "перезарядка" in attempt_status(fresh).lower():
        return "Не вышло: кейс ещё на перезарядке." + when

    # Что-то незнакомое — показываем, что сказал сам бот.
    details = raw or "процесс ничего не написал"
    return f"Не вышло, кейс не открылся.\n\n{details}" + when


def check() -> str:
    """Полная проверка сессии: поднимает браузер и открывает сайт."""
    output = run_command([sys.executable, BOT, "status"])
    # Служебная строка про запуск браузера нужна в журнале, но не в чате.
    lines = [line for line in output.splitlines() if not NOISE.match(line)]
    # В терминале колонки выровнены пробелами, в чате это выглядит рвано.
    return re.sub(r":[ ]{2,}", ": ", "\n".join(lines).strip())


def timer() -> str:
    output = run_command(
        ["systemctl", "list-timers", "magicrust-case.timer", "--no-pager"], timeout=30
    )
    # Последняя строка «1 timers listed…» в чате не нужна.
    lines = [line for line in output.splitlines() if "timers listed" not in line]
    return "\n".join(lines).strip() or output


def version() -> str:
    """Какая ревизия развёрнута — чтобы не гадать, доехало ли обновление."""
    code, output = execute(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%h %s (%cd)", "--date=short"],
        timeout=30,
    )
    if code:
        return "каталог не подключён к git"
    return output


def restart() -> str:
    return privileged("restart")


def update() -> str:
    return privileged("update")


def privileged(action: str) -> str:
    """Действие через root-помощник. Без него — инструкция, а не ошибка."""
    if not os.path.exists(ADMIN):
        return (
            "Для этой команды нужны права root, а помощник не установлен.\n"
            "Выполните на сервере:\n"
            "sudo /opt/magicrust-bot/scripts/enable-remote-admin.sh"
        )
    return run_command(["sudo", "-n", ADMIN, action])


def import_cookies(path: str) -> str:
    return run_command([sys.executable, BOT, "import-cookies", path])
