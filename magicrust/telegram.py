from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from .config import LOG_FILE, TG_OFFSET_FILE, log
from .fmt import amount, human_delta, local, now, parse_dt, plural
from .state import attempt_status, read_state

GREETING = (
    "Бот кейса Magic Rust на связи.\n"
    "Открываю «Бесплатное серебро» раз в 10 часов и пишу сюда результат.\n\n"
    "/status — когда следующая попытка и сколько собрано\n"
    "/last — что выпало в прошлый раз\n"
    "/stats — история последних открытий\n"
    "/log — последние строки журнала"
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
    """Сообщение в Telegram, если заданы TG_TOKEN и TG_CHAT_ID."""
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
    command = text.strip().split()[0].split("@")[0].lower()
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
        return tail_log()
    return "Не знаю такой команды. /start — список того, что умею."


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
    text = (message.get("text") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if not text:
        return
    if chat_id != owner:
        log.warning("сообщение от чужого чата %s пропущено: %r", chat_id, text[:50])
        return
    log.info("команда из Telegram: %s", text[:80])
    notify(handle_command(text), chat_id=chat_id)
