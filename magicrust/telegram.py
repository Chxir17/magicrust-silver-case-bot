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

GREETING = (
    "Бот кейса Magic Rust на связи.\n"
    "Открываю «Бесплатное серебро» раз в 10 часов и пишу сюда результат.\n\n"
    "Что показать:\n"
    "/status — когда следующая попытка и сколько собрано\n"
    "/last — что выпало в прошлый раз\n"
    "/stats — история последних открытий\n"
    "/log — последние строки журнала\n"
    "/timer — расписание таймера\n\n"
    "Что сделать:\n"
    "/run — попытаться открыть кейс сейчас\n"
    "/run force — то же, не глядя на расписание\n"
    "/check — полная проверка сессии через браузер\n"
    "/restart — перечитать юниты и перезапустить\n"
    "/update — обновить код из репозитория\n"
    "/login — как перенести сессию Steam"
)

LOGIN_HELP = (
    "Вход в Steam делается на вашем компьютере"
    "1. ./scripts/mr login\n"
    "2. ./scripts/mr export-cookies state/cookies.json\n"
    "3. Пришлите cookies.json сюда файлом — я его подключу.\n\n"
    "Файл содержит ключ доступа к аккаунту на сайте. Он пройдёт через серверы\n"
    "Telegram, и после импорта я его удалю. Если это нежелательно — переносите\n"
    "файл через scp, как описано в README."
)


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
    lines.append(f"Последний кейс: {local(last)}" if last else "Кейс ещё не открывали")

    nxt = parse_dt(state.get("next_attempt"))
    if nxt:
        lines.append(
            f"Следующая попытка: {local(nxt)} (через {human_delta(nxt)})"
            if nxt > now()
            else "Следующая попытка: при ближайшем запуске таймера"
        )
    if state.get("last_silver"):
        lines.append(f"Последний раз выпало: {amount(state['last_silver'])} серебра")
    if state.get("opens"):
        total = state.get("silver_total")
        line = f"Всего открыто кейсов: {state['opens']}"
        if total:
            line += f", собрано {amount(total)} серебра"
        lines.append(line)
    if attempt_status(state):
        lines.append(f"Итог последней попытки: {attempt_status(state)}")
    return "\n".join(lines)


def stats_text() -> str:
    state = read_state()
    history = state.get("history") or []
    if not history:
        return "Открытий пока не было."

    lines = [
        f"Последние {len(history)} "
        f"{plural(len(history), 'открытие', 'открытия', 'открытий')}:"
    ]
    for item in reversed(history):
        opened = parse_dt(item.get("at"))
        silver = item.get("silver")
        when = local(opened) if opened else "—"
        lines.append(f"  {when} — {amount(silver) + ' серебра' if silver else 'без числа в ответе'}")

    known = [item["silver"] for item in history if item.get("silver")]
    if known:
        lines.append("")
        lines.append(f"Среднее за открытие: {amount(round(sum(known) / len(known)))} серебра")
        lines.append(f"Лучшее: {amount(max(known))}, худшее: {amount(min(known))}")
    if state.get("silver_total"):
        opens = state.get("opens", 0)
        lines.append(
            f"Всего собрано: {amount(state['silver_total'])} серебра "
            f"за {opens} {plural(opens, 'кейс', 'кейса', 'кейсов')}"
        )
    return "\n".join(lines)


def tail_log(lines: int = 15) -> str:
    if not LOG_FILE.exists():
        return "Журнал пока пуст."
    tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return "\n".join(tail)[-3500:] or "Журнал пока пуст."


def handle_command(text: str) -> str:
    """Быстрые ответы: только чтение состояния, без запуска браузера."""
    parts = text.strip().split()
    command = parts[0].split("@")[0].lower()
    if command in ("/start", "/help"):
        return GREETING
    if command == "/status":
        return status_text()
    if command == "/last":
        state = read_state()
        win, opened = state.get("last_win"), parse_dt(state.get("last_open"))
        if not win:
            return "Кейс ещё не открывали."
        return f"{local(opened)} — {win}" if opened else f"Прошлый раз: {win}"
    if command == "/stats":
        return stats_text()
    if command == "/log":
        return tail_log(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15)
    if command == "/login":
        return LOGIN_HELP
    return "Не знаю такой команды. /start — список того, что умею."

COMMAND_MENU = [
    ("status", "Когда следующая попытка и сколько собрано"),
    ("last", "Что выпало в прошлый раз"),
    ("stats", "История последних открытий"),
    ("run", "Попытаться открыть кейс сейчас"),
    ("check", "Полная проверка сессии через браузер"),
    ("timer", "Расписание таймера"),
    ("log", "Последние строки журнала"),
    ("restart", "Перечитать юниты и перезапустить"),
    ("update", "Обновить код из репозитория"),
    ("login", "Как перенести сессию Steam"),
    ("help", "Список команд"),
]


def publish_menu(owner: str) -> None:
    """Публикует подсказку по командам.

    Меню показывается только владельцу: команды всё равно выполняются лишь для
    него, а посторонним, наткнувшимся на бота в поиске, показывать нечего.
    Если адресный вызов не прошёл, ставим общее меню — лучше так, чем никакого.
    """
    commands = json.dumps(
        [{"command": name, "description": text} for name, text in COMMAND_MENU]
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
        log.info("меню команд обновлено (%d команд)", len(COMMAND_MENU))
        return

    log.warning("не удалось задать меню для владельца, ставлю общее")
    tg_api("setMyCommands", commands=commands)


SLOW_COMMANDS = {
    "/run": ("Запускаю попытку, это займёт до минуты…", lambda args: admin.attempt("force" in args)),
    "/check": ("Проверяю сессию через браузер…", lambda args: admin.status()),
    "/timer": ("Смотрю расписание…", lambda args: admin.timer()),
    "/restart": ("Перечитываю юниты…", lambda args: admin.restart()),
    "/update": ("Обновляю код…", lambda args: admin.update()),
}

#  Опрос

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
        notify(ack, chat_id=chat_id)
        notify(action(parts[1:]), chat_id=chat_id)
        return

    notify(handle_command(text), chat_id=chat_id)


def accept_cookies(document: dict) -> str:
    name = document.get("file_name") or ""
    if not name.endswith(".json"):
        return "Жду файл cookies.json. Как его получить — /login"
    if (document.get("file_size") or 0) > 1_000_000:
        return "Файл слишком большой для набора куки."

    info = tg_api("getFile", file_id=document["file_id"])
    if not info or not info.get("file_path"):
        return "Не удалось забрать файл у Telegram."

    token = os.environ.get("TG_TOKEN")
    url = f"https://api.telegram.org/file/bot{token}/{info['file_path']}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read().decode("utf-8")
        cookies = json.loads(raw)
    except Exception as exc:                                
        return f"Файл не читается: {exc}"

    if not isinstance(cookies, list) or not all(isinstance(c, dict) for c in cookies):
        return "Это не похоже на выгрузку куки: ожидался список объектов."

    target = STATE_DIR / "cookies.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(raw, encoding="utf-8")
    target.chmod(0o600)
    log.info("получен файл куки из Telegram: %d записей", len(cookies))

    try:
        return admin.import_cookies(str(target))
    finally:
        target.unlink(missing_ok=True)
