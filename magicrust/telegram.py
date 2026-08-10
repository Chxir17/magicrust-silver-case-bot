from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from . import admin
from .config import LOG_FILE, STATE_DIR, TG_OFFSET_FILE, log
from .fmt import amount, human_delta, local, now, parse_dt, plural
from .state import attempt_status, read_state
from .texts import Chat, Menu, Time, Words


def tg_api(method: str, http_timeout: int = 20, **params):
    token = os.environ.get("TG_TOKEN")
    if not token:
        return None
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=http_timeout
        ) as response:
            answer = json.loads(response.read().decode("utf-8"))
        if not answer.get("ok"):
            log.warning("Telegram %s вернул ошибку: %s", method, answer.get("description"))
            return None
        return answer.get("result")
    except Exception as exc:
        log.warning("Telegram %s недоступен: %s", method, exc)
        return None


def notify(text: str, chat_id: str | None = None) -> None:
    target = chat_id or os.environ.get("TG_CHAT_ID")
    if not target:
        return
    tg_api(
        "sendMessage",
        http_timeout=15,
        chat_id=target,
        text=text,
        disable_web_page_preview="true",
    )


#  Тексты ответов

def status_text() -> str:
    state = read_state()
    lines = []

    last = parse_dt(state.get("last_open"))
    lines.append(Chat.LAST_OPEN.format(when=local(last)) if last else Chat.NEVER_OPENED)

    nxt = parse_dt(state.get("next_attempt"))
    if nxt:
        lines.append(
            Chat.NEXT_TRY.format(when=local(nxt), left=human_delta(nxt))
            if nxt > now()
            else Chat.NEXT_TRY_SOON
        )
    if state.get("last_silver"):
        lines.append(Chat.LAST_SILVER.format(silver=amount(state["last_silver"])))
    if state.get("opens"):
        line = Chat.TOTAL_OPENS.format(opens=state["opens"])
        if state.get("silver_total"):
            line += Chat.TOTAL_SILVER.format(silver=amount(state["silver_total"]))
        lines.append(line)
    if attempt_status(state):
        lines.append(Chat.LAST_STATUS.format(status=attempt_status(state)))
    return "\n".join(lines)


def stats_text() -> str:
    state = read_state()
    history = state.get("history") or []
    if not history:
        return Chat.NO_HISTORY

    lines = [
        Chat.HISTORY_HEAD.format(
            count=len(history), word=plural(len(history), *Words.OPENINGS)
        )
    ]
    for item in reversed(history):
        opened = parse_dt(item.get("at"))
        silver = item.get("silver")
        lines.append(
            Chat.HISTORY_ROW.format(
                when=local(opened) if opened else Time.UNKNOWN_DATE,
                value=(
                    Chat.HISTORY_SILVER.format(silver=amount(silver))
                    if silver
                    else Chat.HISTORY_UNKNOWN
                ),
            )
        )

    known = [item["silver"] for item in history if item.get("silver")]
    if known:
        lines.append("")
        lines.append(Chat.AVERAGE.format(silver=amount(round(sum(known) / len(known)))))
        lines.append(Chat.BEST_WORST.format(best=amount(max(known)), worst=amount(min(known))))
    if state.get("silver_total"):
        opens = state.get("opens", 0)
        lines.append(
            Chat.GRAND_TOTAL.format(
                silver=amount(state["silver_total"]),
                opens=opens,
                word=plural(opens, *Words.CASES),
            )
        )
    return "\n".join(lines)


def tail_log(lines: int = 15) -> str:
    if not LOG_FILE.exists():
        return Chat.EMPTY_LOG
    tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return "\n".join(tail)[-3500:] or Chat.EMPTY_LOG


def handle_command(text: str) -> str:
    """Быстрые ответы: только чтение состояния, без запуска браузера."""
    parts = text.strip().split()
    command = parts[0].split("@")[0].lower()
    if command in ("/start", "/help"):
        return Chat.GREETING
    if command == "/status":
        return status_text()
    if command == "/last":
        state = read_state()
        win, opened = state.get("last_win"), parse_dt(state.get("last_open"))
        if not win:
            return Chat.NEVER_OPENED_DOT
        return (
            Chat.LAST_WIN_AT.format(when=local(opened), win=win)
            if opened
            else Chat.LAST_WIN.format(win=win)
        )
    if command == "/stats":
        return stats_text()
    if command == "/log":
        return tail_log(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15)
    if command == "/login":
        return Chat.LOGIN_HELP
    if command == "/version":
        known = ", ".join(sorted(name for name, _ in Menu.COMMANDS))
        return Chat.VERSION.format(version=admin.version(), commands=known)
    return Chat.UNKNOWN


def publish_menu(owner: str) -> None:
    commands = json.dumps(
        [{"command": name, "description": text} for name, text in Menu.COMMANDS]
    )
    try:
        scope = json.dumps({"type": "chat", "chat_id": int(owner)})
    except ValueError:
        scope = None

    if scope and tg_api("setMyCommands", commands=commands, scope=scope) is not None:
        tg_api(
            "setMyCommands",
            commands="[]",
            scope=json.dumps({"type": "all_private_chats"}),
        )
        log.info("меню команд обновлено (%d команд)", len(Menu.COMMANDS))
        return

    log.warning("не удалось задать меню для владельца, ставлю общее")
    tg_api("setMyCommands", commands=commands)


def run_ack(args: list[str]) -> str | None:
    if any(word.lower() in admin.FORCE_WORDS for word in args):
        return Chat.ACK_RUN
    nxt = parse_dt(read_state().get("next_attempt"))
    if nxt and nxt > now():
        return None
    return Chat.ACK_RUN


SLOW_COMMANDS = {
    "/run": (run_ack, admin.attempt),
    "/check": (Chat.ACK_CHECK, lambda args: admin.check()),
    "/timer": (Chat.ACK_TIMER, lambda args: admin.timer()),
    "/restart": (Chat.ACK_RESTART, lambda args: admin.restart()),
    "/update": (Chat.ACK_UPDATE, lambda args: admin.update()),
}


#опрос

def poll(once: bool = False) -> int:
    """Опрашивает Telegram и отвечает на команды."""
    if not os.environ.get("TG_TOKEN"):
        log.error("TG_TOKEN не задан в .env")
        return 1

    owner = str(os.environ.get("TG_CHAT_ID") or "").strip()
    if not owner:
        log.error("TG_CHAT_ID не задан — без него бот отвечал бы кому угодно")
        return 1

    me = tg_api("getMe")
    if not me:
        log.error("Telegram не принял токен — проверьте TG_TOKEN")
        return 1
    log.info("слушаю Telegram как @%s, отвечаю только chat_id %s", me.get("username"), owner)
    publish_menu(owner)

    offset = read_offset()
    poll_seconds = 0 if once else 50

    while True:
        updates = tg_api(
            "getUpdates", http_timeout=poll_seconds + 20, offset=offset, timeout=poll_seconds
        )
        if updates is None:
            time.sleep(10)
            if once:
                return 1
            continue

        for update in updates:
            offset = update["update_id"] + 1
            answer_update(update, owner)

        if offset:
            TG_OFFSET_FILE.write_text(str(offset), encoding="utf-8")
        if once:
            log.info("обработано обновлений: %d", len(updates))
            return 0


def read_offset() -> int | None:
    if not TG_OFFSET_FILE.exists():
        return None
    try:
        return int(TG_OFFSET_FILE.read_text().strip() or 0) or None
    except ValueError:
        log.warning("tg_offset повреждён, начинаю с текущих сообщений")
        return None


def answer_update(update: dict, owner: str) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if chat_id != owner:
        log.warning("сообщение от чужого чата %s пропущено", chat_id)
        return

    if message.get("document"):
        notify(accept_cookies(message["document"]), chat_id=chat_id)
        return

    text = (message.get("text") or "").strip()
    if not text:
        return

    parts = text.split()
    command = parts[0].split("@")[0].lower()
    log.info("команда из Telegram: %s", text[:80])

    if command in SLOW_COMMANDS:
        ack, action = SLOW_COMMANDS[command]
        args = parts[1:]
        message_text = ack(args) if callable(ack) else ack
        if message_text:
            notify(message_text, chat_id=chat_id)
        notify(action(args), chat_id=chat_id)
        return

    notify(handle_command(text), chat_id=chat_id)


def accept_cookies(document: dict) -> str:
    name = document.get("file_name") or ""
    if not name.endswith(".json"):
        return Chat.COOKIES_EXPECTED
    if (document.get("file_size") or 0) > 1_000_000:
        return Chat.COOKIES_TOO_BIG

    info = tg_api("getFile", file_id=document["file_id"])
    if not info or not info.get("file_path"):
        return Chat.COOKIES_NOT_FETCHED

    token = os.environ.get("TG_TOKEN")
    url = f"https://api.telegram.org/file/bot{token}/{info['file_path']}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read().decode("utf-8")
        cookies = json.loads(raw)
    except Exception as exc:
        return Chat.COOKIES_UNREADABLE.format(error=exc)

    if not isinstance(cookies, list) or not all(isinstance(c, dict) for c in cookies):
        return Chat.COOKIES_WRONG_SHAPE

    target = STATE_DIR / "cookies.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(raw, encoding="utf-8")
    target.chmod(0o600)
    log.info("получен файл куки из Telegram: %d записей", len(cookies))

    try:
        return admin.import_cookies(str(target))
    finally:
        target.unlink(missing_ok=True)
