from __future__ import annotations

import os
import re
import subprocess
import sys

from . import users
from .config import ROOT, log
from .fmt import human_delta, local, now, parse_dt
from .state import attempt_status, read_state
from .texts import Chat

BOT = str(ROOT / "bot.py")
ADMIN = "/usr/local/sbin/magicrust-admin"
LIMIT = 3500

LOG_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+\w+\s+", re.M)

FORCE_WORDS = {"force", "--force", "-f", "now", "сейчас", "давай"}

NOISE = re.compile(r"^(запускаю Chromium|HEADLESS=0)")


def strip_log_prefix(text: str) -> str:
    return LOG_PREFIX.sub("", text).strip()


def execute(argv: list[str], timeout: int = 600) -> tuple[int | None, str]:
    log.info("выполняю по команде из Telegram: %s", " ".join(argv))
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT)
        )
    except FileNotFoundError:
        return None, Chat.NO_PROGRAM.format(program=argv[0])
    except subprocess.TimeoutExpired:
        return None, Chat.TIMED_OUT.format(minutes=timeout // 60)

    output = strip_log_prefix(done.stdout + done.stderr)
    if len(output) > LIMIT:
        output = "…\n" + output[-LIMIT:]
    return done.returncode, output


def run_command(argv: list[str], timeout: int = 600) -> str:
    code, output = execute(argv, timeout)
    output = output or Chat.DONE
    if code:
        output += Chat.EXIT_CODE.format(code=code)
    return output


def whose(account: users.Account) -> list[str]:
    """Аргументы, которыми дочерний процесс выбирает нужного игрока."""
    return ["--user", account.chat_id] if account.chat_id else []


def attempt(args: list[str], account: users.Account) -> str:
    force = any(word.lower() in FORCE_WORDS for word in args)

    state = read_state(account)
    nxt = parse_dt(state.get("next_attempt"))
    if not force and nxt and nxt > now():
        return Chat.TOO_EARLY.format(when=local(nxt), left=human_delta(nxt))

    was_open = state.get("last_open")
    code, raw = execute(
        [sys.executable, BOT, "run"] + whose(account) + (["--force"] if force else [])
    )
    fresh = read_state(account)

    following = parse_dt(fresh.get("next_attempt"))
    when = (
        Chat.NEXT_AFTER.format(when=local(following), left=human_delta(following))
        if following and following > now()
        else ""
    )

    if fresh.get("last_open") != was_open:
        win = fresh.get("last_win") or Chat.OPENED_NO_DETAILS
        return Chat.OPENED.format(win=win) + when
    if code == 2:
        return Chat.FAILED_SESSION
    if code == 0 and "перезарядка" in attempt_status(fresh).lower():
        return Chat.FAILED_COOLDOWN + when
    return Chat.FAILED_UNKNOWN.format(details=raw or Chat.FAILED_SILENT) + when


def check(account: users.Account) -> str:
    output = run_command([sys.executable, BOT, "status"] + whose(account))
    lines = [line for line in output.splitlines() if not NOISE.match(line)]
    return re.sub(r":[ ]{2,}", ": ", "\n".join(lines).strip())


def timer() -> str:
    output = run_command(
        ["systemctl", "list-timers", "magicrust-case.timer", "--no-pager"], timeout=30
    )
    lines = [line for line in output.splitlines() if "timers listed" not in line]
    return "\n".join(lines).strip() or output


def version() -> str:
    code, output = execute(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%h %s (%cd)", "--date=short"],
        timeout=30,
    )
    return Chat.NO_GIT if code else output


def restart() -> str:
    return privileged("restart")


def update() -> str:
    return privileged("update")


def privileged(action: str) -> str:
    if not os.path.exists(ADMIN):
        return Chat.NEED_ROOT
    return run_command(["sudo", "-n", ADMIN, action])


def import_cookies(path: str, account: users.Account) -> str:
    return run_command([sys.executable, BOT, "import-cookies", path] + whose(account))
