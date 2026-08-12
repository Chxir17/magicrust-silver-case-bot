from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import admin, users
from .config import COOKIE_TOOL, LOG_FILE, TG_OFFSET_FILE, log
from .cookies import normalize
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
    target = str(chat_id or "") or next(iter(users.admin_ids()), "")
    if not target:
        return
    tg_api(
        "sendMessage",
        http_timeout=15,
        chat_id=target,
        text=text,
        disable_web_page_preview="true",
    )


def notify_owner(text: str) -> None:
    """Сообщение владельцу того аккаунта, с которым идёт работа сейчас."""
    notify(text, chat_id=users.current().chat_id or None)


def multipart(fields: dict, name: str, blob: bytes, boundary: str) -> bytes:
    """Тело multipart/form-data — sendDocument иначе файл не примет."""
    parts = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
        f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
    )
    parts.append(blob)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts)


def send_file(chat_id: str, path: Path, caption: str = "") -> bool:
    token = os.environ.get("TG_TOKEN")
    if not token:
        return False

    boundary = uuid.uuid4().hex
    try:
        body = multipart(
            {"chat_id": chat_id, "caption": caption},
            path.name,
            path.read_bytes(),
            boundary,
        )
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            answer = json.loads(response.read().decode("utf-8"))
        if not answer.get("ok"):
            log.warning("Telegram не принял файл: %s", answer.get("description"))
            return False
        return True
    except Exception as exc:
        log.warning("не отправил %s: %s", path.name, exc)
        return False


def send_cookie_tool(chat_id: str) -> None:
    if not COOKIE_TOOL.exists():
        log.error("нет файла %s — обновите код", COOKIE_TOOL)
        notify(Chat.TOOL_MISSING, chat_id=chat_id)
        return
    if not send_file(chat_id, COOKIE_TOOL, Chat.TOOL_CAPTION):
        notify(Chat.TOOL_NOT_SENT, chat_id=chat_id)


#  Тексты ответов

def status_text(account: users.Account) -> str:
    state = read_state(account)
    lines = []

    if not account.profile_dir.exists():
        lines.append(Chat.NO_SESSION_YET)

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


def stats_text(account: users.Account) -> str:
    state = read_state(account)
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


def handle_command(text: str, account: users.Account, is_admin: bool) -> str:
    """Быстрые ответы: только чтение состояния, без запуска браузера."""
    parts = text.strip().split()
    command = parts[0].split("@")[0].lower()
    if command in ("/start", "/help"):
        return Chat.GREETING_ADMIN if is_admin else Chat.GREETING
    if command == "/status":
        return status_text(account)
    if command == "/last":
        state = read_state(account)
        win, opened = state.get("last_win"), parse_dt(state.get("last_open"))
        if not win:
            return Chat.NEVER_OPENED_DOT
        return (
            Chat.LAST_WIN_AT.format(when=local(opened), win=win)
            if opened
            else Chat.LAST_WIN.format(win=win)
        )
    if command == "/stats":
        return stats_text(account)
    if command == "/log":
        return tail_log(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15)
    if command == "/login":
        return Chat.LOGIN_HELP
    if command == "/version":
        known = ", ".join(sorted(name for name, _ in Menu.ADMIN))
        return Chat.VERSION.format(version=admin.version(), commands=known)
    return Chat.UNKNOWN


#  Управление доступом

def who(chat_id: str, entry: dict) -> str:
    name = (entry or {}).get("name") or ""
    username = (entry or {}).get("username") or ""
    label = " ".join(part for part in (name, f"@{username}" if username else "") if part)
    return f"{label} · {chat_id}" if label else str(chat_id)


def account_status(account: users.Account) -> str:
    if not account.profile_dir.exists():
        return Chat.USERS_NO_SESSION
    state = read_state(account)
    nxt = parse_dt(state.get("next_attempt"))
    line = (
        Chat.USERS_NEXT.format(left=human_delta(nxt))
        if nxt and nxt > now()
        else Chat.USERS_IDLE
    )
    if state.get("opens"):
        line += Chat.USERS_OPENS.format(opens=state["opens"])
    return line


def target_id(args: list[str], command: str) -> tuple[str, str]:
    if not args:
        return "", Chat.USAGE_ID.format(command=command)
    value = args[0].lstrip("@")
    if not value.lstrip("-").isdigit():
        return "", Chat.BAD_ID.format(value=value[:32])
    return value, ""


def list_users(args: list[str], chat_id: str) -> str:
    registry = users.read_registry()
    people, waiting = registry["users"], registry["pending"]

    lines = []
    if people:
        lines.append(Chat.USERS_HEAD.format(count=len(people)))
        for uid, entry in people.items():
            lines.append(
                Chat.USERS_ROW.format(
                    who=who(uid, entry),
                    admin=Chat.USERS_ADMIN_MARK if users.is_admin(uid) else "",
                    status=account_status(users.Account(uid, entry.get("name", ""))),
                )
            )
    else:
        lines.append(Chat.NO_USERS)

    if waiting:
        lines.append("")
        lines.append(Chat.PENDING_HEAD.format(count=len(waiting)))
        for uid, entry in waiting.items():
            lines.append(Chat.PENDING_ROW.format(who=who(uid, entry), id=uid))
    return "\n".join(lines)


def approve_user(args: list[str], chat_id: str) -> str:
    target, problem = target_id(args, "/approve")
    if problem:
        return problem

    entry = users.pending().get(target, {})
    label = who(target, entry)
    if not users.add(target, entry.get("name", ""), entry.get("username", ""), by=chat_id):
        return Chat.ALREADY_ADDED.format(who=label)

    publish_menu()
    notify(Chat.ACCESS_GRANTED, chat_id=target)
    notify(Chat.LOGIN_HELP, chat_id=target)
    return Chat.ADDED.format(who=label)


def remove_user(args: list[str], chat_id: str) -> str:
    target, problem = target_id(args, "/remove")
    if problem:
        return problem
    if users.is_admin(target):
        return Chat.SELF_REMOVE
    if not users.remove(target):
        return Chat.NOT_A_USER.format(id=target)

    forget_menu(target)
    notify(Chat.ACCESS_REVOKED, chat_id=target)
    return Chat.REMOVED.format(id=target)


MANAGE = {
    "/users": list_users,
    "/approve": approve_user,
    "/remove": remove_user,
}


#  Меню команд

def chat_scope(chat_id: str) -> str | None:
    try:
        return json.dumps({"type": "chat", "chat_id": int(chat_id)})
    except ValueError:
        return None


def menu_json(commands) -> str:
    return json.dumps([{"command": name, "description": text} for name, text in commands])


def publish_menu() -> None:
    """Каждому чату — свой набор подсказок, посторонним не видно ничего."""
    tg_api("setMyCommands", commands="[]", scope=json.dumps({"type": "all_private_chats"}))

    shown = 0
    for account in users.accounts():
        scope = chat_scope(account.chat_id)
        if not scope:
            continue
        commands = Menu.ADMIN if users.is_admin(account.chat_id) else Menu.USER
        if tg_api("setMyCommands", commands=menu_json(commands), scope=scope) is not None:
            shown += 1
    log.info("меню команд обновлено для %d чатов", shown)


def forget_menu(chat_id: str) -> None:
    scope = chat_scope(chat_id)
    if scope:
        tg_api("deleteMyCommands", scope=scope)


#  Долгие команды

def run_ack(args: list[str], account: users.Account) -> str | None:
    if any(word.lower() in admin.FORCE_WORDS for word in args):
        return Chat.ACK_RUN
    nxt = parse_dt(read_state(account).get("next_attempt"))
    if nxt and nxt > now():
        return None
    return Chat.ACK_RUN


SLOW_COMMANDS = {
    "/run": (run_ack, admin.attempt),
    "/check": (Chat.ACK_CHECK, lambda args, account: admin.check(account)),
    "/timer": (Chat.ACK_TIMER, lambda args, account: admin.timer()),
    "/restart": (Chat.ACK_RESTART, lambda args, account: admin.restart()),
    "/update": (Chat.ACK_UPDATE, lambda args, account: admin.update()),
}

# Команды, которые управляют сервером и чужими данными.
ADMIN_ONLY = set(MANAGE) | {"/timer", "/restart", "/update", "/log", "/version"}


#опрос

def poll(once: bool = False) -> int:
    """Опрашивает Telegram и отвечает на команды."""
    if not os.environ.get("TG_TOKEN"):
        log.error("TG_TOKEN не задан в .env")
        return 1

    admins = users.admin_ids()
    if not admins:
        log.error("TG_CHAT_ID не задан — без него некому управлять доступом")
        return 1

    me = tg_api("getMe")
    if not me:
        log.error("Telegram не принял токен — проверьте TG_TOKEN")
        return 1

    log.info(
        "слушаю Telegram как @%s: администраторов %d, игроков %d",
        me.get("username"),
        len(admins),
        len(users.accounts()),
    )
    publish_menu()

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
            answer_update(update)

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


def answer_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return

    account = users.resolve(chat_id)
    if account is None:
        # В группы и каналы, куда бота просто добавили, не отвечаем.
        if chat.get("type") == "private":
            ask_access(message, chat_id)
        return

    if message.get("document"):
        notify(accept_cookies(message["document"], account), chat_id=chat_id)
        return

    text = (message.get("text") or "").strip()
    if not text:
        return

    parts = text.split()
    command = parts[0].split("@")[0].lower()
    args = parts[1:]
    is_admin = users.is_admin(chat_id)
    log.info("команда от %s: %s", account.title, text[:80])

    if command in ADMIN_ONLY and not is_admin:
        log.warning("%s просит админскую команду %s — отказано", account.title, command)
        notify(Chat.ADMIN_ONLY, chat_id=chat_id)
        return

    if command == "/cookies":
        send_cookie_tool(chat_id)
        return

    if command in MANAGE:
        notify(MANAGE[command](args, chat_id), chat_id=chat_id)
        return

    if command in SLOW_COMMANDS:
        ack, action = SLOW_COMMANDS[command]
        message_text = ack(args, account) if callable(ack) else ack
        if message_text:
            notify(message_text, chat_id=chat_id)
        notify(action(args, account), chat_id=chat_id)
        return

    notify(handle_command(text, account, is_admin), chat_id=chat_id)


def ask_access(message: dict, chat_id: str) -> None:
    """Незнакомцу — отказ, администратору — заявка (по одной на человека)."""
    sender = message.get("from") or {}
    name = " ".join(
        part for part in (sender.get("first_name"), sender.get("last_name")) if part
    )
    username = sender.get("username") or ""

    fresh = users.remember_request(chat_id, name, username)
    notify(Chat.NO_ACCESS.format(id=chat_id), chat_id=chat_id)
    if not fresh:
        return

    request = Chat.ACCESS_REQUEST.format(
        who=who(chat_id, {"name": name, "username": username}), id=chat_id
    )
    for admin_id in users.admin_ids():
        notify(request, chat_id=admin_id)


def accept_cookies(document: dict, account: users.Account) -> str:
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
        payload = json.loads(raw)
    except Exception as exc:
        return Chat.COOKIES_UNREADABLE.format(error=exc)

    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        return Chat.COOKIES_WRONG_SHAPE
    if not normalize(payload):
        return Chat.COOKIES_NOT_OURS

    account.dir.mkdir(parents=True, exist_ok=True)
    target = account.dir / "cookies.json"
    target.write_text(raw, encoding="utf-8")
    target.chmod(0o600)
    log.info("получены куки от %s: %d записей", account.title, len(payload))

    try:
        return admin.import_cookies(str(target), account)
    finally:
        target.unlink(missing_ok=True)
