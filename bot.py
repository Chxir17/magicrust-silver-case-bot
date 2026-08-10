#!/usr/bin/env python3
"""
Magic Rust — автооткрытие бесплатного кейса с серебром (product id = 5).

Команды:
    python bot.py login            вход через Steam вручную (откроется окно браузера)
    python bot.py status           состояние сессии и время следующей попытки
    python bot.py run              одна попытка открыть кейс (для systemd/cron)
    python bot.py run --force      попытаться, даже если по таймеру ещё рано
    python bot.py telegram         отвечать на /start и /status в Telegram
    python bot.py telegram --once  разобрать накопившееся и выйти (проверка)
    python bot.py export-cookies [файл]    выгрузить куки (перенос на VPS)
    python bot.py import-cookies <файл>    загрузить куки в профиль

Пароль Steam вводите только вы сами в окне браузера — скрипт его не знает,
не хранит и никуда не отправляет. Сохраняется лишь cookie-сессия сайта.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
PROFILE_DIR = STATE_DIR / "profile"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "bot.log"
# Отдельным файлом, а не в state.json: опрос Telegram крутится постоянно и
# иначе перетирал бы записи, которые в тот же момент делает `run`.
TG_OFFSET_FILE = STATE_DIR / "tg_offset"

SITE = "https://magicrust.gg/ru"
PRODUCT_ID = 5

CARD = f'.products__card[data-product="{PRODUCT_ID}"]'
MODAL = f'[data-modal="product-{PRODUCT_ID}"]'
OPEN_BTN = f"{MODAL} .modal-roulette__btn.modal-product-buy"
AUTH_BTN = f"{MODAL} .auth-btn"
LOGGED_IN = ".header-top-v2__player"
GMOD_BTN = ".products__gmod-btn.change-gmod"

CHROME_MAJOR = 140

# Интервалы (в минутах)
COOLDOWN_MIN = 10 * 60          # кейс раз в 10 часов
COOLDOWN_PAD = 8                # запас, чтобы не стучаться раньше времени
RETRY_ON_COOLDOWN = 25          # ещё рано — попробуем позже
RETRY_ON_ERROR = 20             # непонятная ошибка
RETRY_ON_NO_SESSION = 90        # сессия умерла, нужен ручной re-login

log = logging.getLogger("magicrust")


# --------------------------------------------------------------------------- #
#  Утилиты
# --------------------------------------------------------------------------- #

def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.addHandler(stream)
    log.addHandler(file_handler)


def now() -> datetime:
    return datetime.now(timezone.utc)


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


def schedule_next(minutes: int, jitter: int = 5) -> str:
    """Ставит следующую попытку через N минут (+ случайный разброс)."""
    delay = minutes + random.uniform(0, jitter)
    ts = (now() + timedelta(minutes=delay)).isoformat()
    write_state(next_attempt=ts)
    return ts


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def human_delta(dt: datetime) -> str:
    seconds = int((dt - now()).total_seconds())
    if seconds <= 0:
        return "сейчас"
    hours, rem = divmod(seconds, 3600)
    return f"{hours} ч {rem // 60} мин" if hours else f"{rem // 60} мин"


def local(dt: datetime) -> str:
    """Время в часовом поясе из MR_TZ — сервер обычно живёт по UTC."""
    try:
        from zoneinfo import ZoneInfo

        dt = dt.astimezone(ZoneInfo(os.environ.get("MR_TZ", "Europe/Moscow")))
    except Exception:                                         # noqa: BLE001
        dt = dt.astimezone()
    return dt.strftime("%d.%m %H:%M")


def tg_api(method: str, http_timeout: int = 20, **params):
    """Вызов Telegram Bot API. Возвращает поле result или None при ошибке.

    Таймаут HTTP назван отдельно: у getUpdates есть свой параметр `timeout`,
    и одинаковые имена схлопнулись бы в один аргумент.
    """
    token = os.environ.get("TG_TOKEN")
    if not token:
        return None
    data = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    ).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=http_timeout
        ) as response:
            answer = json.loads(response.read().decode("utf-8"))
        if not answer.get("ok"):
            log.warning("Telegram %s вернул ошибку: %s", method, answer.get("description"))
            return None
        return answer.get("result")
    except Exception as exc:                                  # noqa: BLE001
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


def user_agent() -> str:
    if os.environ.get("MR_UA"):
        return os.environ["MR_UA"]
    if sys.platform == "darwin":
        platform = "Macintosh; Intel Mac OS X 10_15_7"
    elif sys.platform.startswith("win"):
        platform = "Windows NT 10.0; Win64; x64"
    else:
        platform = "X11; Linux x86_64"
    return (
        f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{CHROME_MAJOR}.0.0.0 Safari/537.36"
    )


# --------------------------------------------------------------------------- #
#  Браузер
# --------------------------------------------------------------------------- #

def browser_context(playwright, headless: bool):
    """Постоянный профиль Chromium: куки и localStorage переживают перезапуски."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if os.environ.get("MR_NO_SANDBOX", "1") == "1" and sys.platform.startswith("linux"):
        args.append("--no-sandbox")

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        args=args,
        user_agent=user_agent(),
        locale="ru-RU",
        timezone_id=os.environ.get("MR_TZ", "Europe/Moscow"),
        viewport={"width": 1440, "height": 900},
        ignore_default_args=["--enable-automation"],
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    context.set_default_timeout(30_000)
    return context


def gmod() -> str:
    """Режим игры в магазине.

    Бесплатный кейс есть только в `modded` и `vanillax2plus` — в `vanillax2`
    и `vanilla` карточка скрыта. Серебро начисляется в выбранном режиме,
    поэтому ставьте тот, на котором играете.
    """
    return os.environ.get("MR_GMOD", "modded")


def open_site(context):
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(SITE, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_selector(GMOD_BTN, timeout=30_000)
    dismiss_promo(page)
    select_gmod(page)
    return page


def dismiss_promo(page) -> None:
    """Закрывает рекламный поп-ап со скидкой, если он перекрывает страницу.

    Плашку про cookie бот не трогает: согласия за вас никто не даёт —
    нажмите «Ok» сами один раз во время `bot.py login`, профиль это запомнит.
    """
    close = page.locator(".cohort-popup__close")
    try:
        if close.count() and close.first.is_visible():
            close.first.click(timeout=3000)
            page.wait_for_timeout(300)
    except Exception:                                
        pass                                              


def select_gmod(page) -> None:
    target = gmod()
    button = page.locator(f'{GMOD_BTN}[data-gmod="{target}"]')
    if button.count() == 0:
        available = page.locator(GMOD_BTN).evaluate_all(
            "els => els.map(e => e.dataset.gmod)"
        )
        raise RuntimeError(f"режим {target!r} не найден, доступны: {available}")

    if "active" not in (button.first.get_attribute("class") or ""):
        button.first.click()
        page.wait_for_timeout(800)

    try:
        page.wait_for_selector(CARD, state="visible", timeout=15_000)
    except PWTimeout as exc:
        raise RuntimeError(
            f"кейс (product {PRODUCT_ID}) не виден в режиме {target!r} — "
            f"попробуйте MR_GMOD=vanillax2plus"
        ) from exc


def is_logged_in(page) -> bool:
    return page.locator(LOGGED_IN).count() > 0


def find_silver(node, depth: int = 0):
    if depth > 6:
        return None
    if isinstance(node, dict):
        for key, value in node.items():
            if re.search(r"silver|amount|value|count|sum|win", str(key), re.I):
                if isinstance(value, (int, float)) and value > 0:
                    return value
                if isinstance(value, str) and value.strip().isdigit():
                    return int(value)
            found = find_silver(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_silver(item, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, str):
        match = re.search(r"(\d+)\s*(?:silver|серебр)", node, re.I)
        if match:
            return int(match.group(1))
    return None


COOLDOWN_WORDS = re.compile(
    r"подожд|недоступ|уже\s+(получ|открыл|забра)|попробуйте\s+позже|осталось|"
    r"доступен\s+кажд|кажд\w*\s+\d+\s*час|раз\s+в\s+\d+\s*час|"
    r"cooldown|too\s+many|not\s+available|every\s+\d+\s*hour",
    re.I,
)


def payload_is_error(payload) -> bool:
    """Ответ 200, но внутри отказ — такое встречается у Laravel-бэкендов."""
    if not isinstance(payload, dict):
        return False
    for key in ("success", "status", "ok", "result"):
        value = payload.get(key)
        if value is False or (isinstance(value, str) and value.lower() == "error"):
            return True
    return bool(payload.get("error") or payload.get("errors"))


# --------------------------------------------------------------------------- #
#  Команды
# --------------------------------------------------------------------------- #

def cmd_login(_args) -> int:
    print(
        "\nОткроется окно браузера.\n"
        "  1. Нажмите «Войти» → «Войти через Steam».\n"
        "  2. Введите логин, пароль и код Steam Guard — сами, в окне браузера.\n"
        "     Скрипт пароль не видит и не сохраняет: остаётся только cookie сайта.\n"
        "  3. Дождитесь возврата на magicrust.gg — окно закроется само.\n"
        "Заодно нажмите «Ok» в плашке про cookie: профиль это запомнит,\n"
        "и она перестанет перекрывать страницу при автозапусках.\n"
    )
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SITE, wait_until="domcontentloaded", timeout=60_000)
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            try:
                if is_logged_in(page):
                    log.info("вход выполнен, сессия сохранена в %s", PROFILE_DIR)
                    write_state(logged_in_at=now().isoformat())
                    page.wait_for_timeout(2000)
                    context.close()
                    print("\nГотово. Проверьте: python bot.py status\n")
                    return 0
            except Exception:                                 
                pass                                          
            time.sleep(2)
        context.close()
    log.error("вход не завершён за 15 минут")
    return 1


def cmd_status(_args) -> int:
    state = read_state()
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        page = open_site(context)
        authorized = is_logged_in(page)
        nickname = ""
        if authorized:
            lines = page.locator(LOGGED_IN).first.inner_text().splitlines()
            nickname = next((ln.strip() for ln in lines if ln.strip()), "")
        context.close()

    print(f"Сессия:          {'активна — ' + nickname if authorized else 'НЕТ (нужен python bot.py login)'}")
    last = parse_dt(state.get("last_open"))
    print(f"Последний кейс:  {last.astimezone().strftime('%d.%m %H:%M') if last else 'ещё не открывали'}")
    if state.get("last_result"):
        print(f"Результат:       {state['last_result']}")
    nxt = parse_dt(state.get("next_attempt"))
    if nxt:
        print(f"Следующая проба: {nxt.astimezone().strftime('%d.%m %H:%M')} (через {human_delta(nxt)})")
    return 0 if authorized else 1


def cmd_run(args) -> int:
    state = read_state()
    nxt = parse_dt(state.get("next_attempt"))
    if nxt and now() < nxt and not args.force:
        log.info("ещё рано, следующая попытка через %s", human_delta(nxt))
        return 0

    if not headless_flag():
        log.warning("HEADLESS=0 — окно браузера видимое, не закрывайте его до конца прогона")

    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        try:
            return attempt_open(context)
        finally:
            context.close()


def attempt_open(context) -> int:
    page = open_site(context)

    if not is_logged_in(page):
        log.error("сессия недействительна — нужен повторный вход (python bot.py login)")
        write_state(last_result="сессия истекла")
        schedule_next(RETRY_ON_NO_SESSION)
        notify("Magic Rust: сессия истекла, нужен повторный вход через Steam")
        return 2

    card = page.locator(CARD).first
    card.scroll_into_view_if_needed()
    try:
        card.click(timeout=10_000)
    except PWTimeout:
        log.warning("обычный клик по карточке не прошёл, пробую dispatch_event")
        card.dispatch_event("click")
    page.wait_for_selector(f"{MODAL}.modal-on", timeout=15_000)
    page.wait_for_timeout(1200)                               

    if page.locator(AUTH_BTN).count() > 0:
        log.error("в модалке кнопка входа — сессия протухла")
        write_state(last_result="сессия истекла")
        schedule_next(RETRY_ON_NO_SESSION)
        notify("Magic Rust: сессия истекла, нужен повторный вход через Steam")
        return 2

    button = page.locator(OPEN_BTN).first
    if button.count() == 0:
        text = page.locator(MODAL).inner_text().strip()
        log.error("кнопка «Открыть кейс» не найдена. Текст модалки:\n%s", text[:500])
        page.screenshot(path=str(STATE_DIR / "last_error.png"), full_page=False)
        write_state(last_result="кнопка не найдена")
        schedule_next(RETRY_ON_ERROR)
        return 3

    log.info("нажимаю «%s»", button.inner_text().strip())

    body, status = "", None
    try:
        with page.expect_response(
            lambda r: "product-buy" in r.url and "product-buy-state" not in r.url,
            timeout=45_000,
        ) as info:
            button.click()
        response = info.value
        status = response.status
        try:
            body = response.text()
        except Exception:                                    
            body = ""
    except PWTimeout:
        log.warning("ответ от /product-buy не пришёл за 45 с — смотрю по странице")

    payload = None
    if body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            pass
    message = str(payload.get("message") or "").strip() if isinstance(payload, dict) else ""
    log.info("HTTP %s | ответ: %s", status, (body or "—")[:600])
    if message:
        log.info("сообщение сайта: %s", message)

    modal_text = ""
    try:
        page.wait_for_timeout(9000)                        
        modal_text = " ".join(page.locator(MODAL).inner_text().split())
        page.screenshot(path=str(STATE_DIR / "last_open.png"))
        log.info("модалка: %s", modal_text[:300])
    except Exception as exc:                                
        log.warning("страница закрылась до конца анимации (%s) — сужу по ответу сервера", type(exc).__name__)

    if status == 200 and payload is not None and not payload_is_error(payload):
        silver = find_silver(payload)
        result = f"выпало {silver} серебра" if silver else "кейс открыт"
        log.info("УСПЕХ: %s", result)
        write_state(
            last_open=now().isoformat(),
            last_result=result,
            last_payload=payload,
            opens=read_state().get("opens", 0) + 1,
        )
        schedule_next(COOLDOWN_MIN + COOLDOWN_PAD, jitter=10)
        notify(f"Magic Rust: кейс открыт — {result}")
        return 0

    if COOLDOWN_WORDS.search(f"{message} {body} {modal_text}") or status in (403, 419, 429):
        write_state(last_result=f"перезарядка: {message}" if message else "перезарядка")
        last = parse_dt(read_state().get("last_open"))
        target = last + timedelta(minutes=COOLDOWN_MIN + COOLDOWN_PAD) if last else None
        if target and target > now():
            write_state(next_attempt=target.isoformat())
            log.info("кейс на перезарядке, следующая попытка через %s", human_delta(target))
        else:
            schedule_next(RETRY_ON_COOLDOWN)
            log.info("кейс на перезарядке, повтор через ~%s мин", RETRY_ON_COOLDOWN)
        return 0

    log.error("непонятный результат (HTTP %s), скриншот: %s", status, STATE_DIR / "last_open.png")
    write_state(last_result=f"ошибка HTTP {status}")
    schedule_next(RETRY_ON_ERROR)
    return 3


# --------------------------------------------------------------------------- #
#  Telegram
# --------------------------------------------------------------------------- #

GREETING = (
    "Бот кейса Magic Rust на связи.\n"
    "Открываю «Бесплатное серебро» раз в 10 часов и пишу сюда результат.\n\n"
    "/status — когда следующая попытка\n"
    "/last — что выпало в прошлый раз\n"
    "/log — последние строки журнала"
)


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
    if state.get("opens"):
        lines.append(f"Всего открыто: {state['opens']}")
    if state.get("last_result"):
        lines.append(f"Статус: {state['last_result']}")
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
        result = read_state().get("last_result")
        return f"Прошлый результат: {result}" if result else "Кейс ещё не открывали."
    if command == "/log":
        return tail_log()
    return "Не знаю такой команды. /start — список того, что умею."


def cmd_telegram(args) -> int:
    """Опрашивает Telegram и отвечает на команды. Работает как отдельный сервис."""
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

    offset = None
    if TG_OFFSET_FILE.exists():
        try:
            offset = int(TG_OFFSET_FILE.read_text().strip() or 0) or None
        except ValueError:
            log.warning("tg_offset повреждён, начинаю с текущих сообщений")

    # При --once ждать полминуты незачем: забираем что накопилось и выходим.
    poll = 0 if args.once else 50

    while True:
        # Длинный poll: соединение висит до 50 с и рвётся сразу, как придёт сообщение.
        updates = tg_api("getUpdates", http_timeout=poll + 20, offset=offset, timeout=poll)
        if updates is None:
            time.sleep(10)                                    # сеть отвалилась — не долбим API
            if args.once:
                return 1
            continue

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message") or {}
            text = (message.get("text") or "").strip()
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if not text:
                continue
            if chat_id != owner:
                # Токен знает только владелец, но бот открыт всем, кто найдёт его в поиске.
                log.warning("сообщение от чужого чата %s пропущено: %r", chat_id, text[:50])
                continue
            log.info("команда из Telegram: %s", text[:80])
            notify(handle_command(text), chat_id=chat_id)

        if offset:
            TG_OFFSET_FILE.write_text(str(offset), encoding="utf-8")
        if args.once:
            log.info("обработано обновлений: %d", len(updates))
            return 0


def cmd_export_cookies(args) -> int:
    target = Path(args.file or STATE_DIR / "cookies.json")
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        open_site(context)
        cookies = context.cookies()
        context.close()
    keep = [c for c in cookies if "magicrust" in c.get("domain", "")]
    target.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Сохранено {len(keep)} куки → {target}")
    print("Перенесите файл на VPS и выполните: python bot.py import-cookies cookies.json")
    return 0


def cmd_import_cookies(args) -> int:
    cookies = json.loads(Path(args.file).read_text(encoding="utf-8"))
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        context.add_cookies(cookies)
        page = open_site(context)
        ok = is_logged_in(page)
        context.close()
    print("Сессия перенесена ✔" if ok else "Куки загружены, но сайт считает вас гостем — нужен login")
    return 0 if ok else 1


def headless_flag() -> bool:
    return os.environ.get("HEADLESS", "1") != "0"


def main() -> int:
    load_env()
    setup_logging()

    parser = argparse.ArgumentParser(description="Бот открытия бесплатного кейса Magic Rust")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="разовый вход через Steam")
    sub.add_parser("status", help="состояние сессии и таймера")

    run_parser = sub.add_parser("run", help="одна попытка открыть кейс")
    run_parser.add_argument("--force", action="store_true", help="игнорировать локальный таймер")

    tg_parser = sub.add_parser("telegram", help="отвечать на команды в Telegram")
    tg_parser.add_argument(
        "--once", action="store_true", help="разобрать накопившееся и выйти (для проверки)"
    )

    export_parser = sub.add_parser("export-cookies", help="выгрузить куки для переноса на VPS")
    export_parser.add_argument("file", nargs="?")

    import_parser = sub.add_parser("import-cookies", help="загрузить куки в профиль")
    import_parser.add_argument("file")

    args = parser.parse_args()
    handlers = {
        "login": cmd_login,
        "status": cmd_status,
        "run": cmd_run,
        "telegram": cmd_telegram,
        "export-cookies": cmd_export_cookies,
        "import-cookies": cmd_import_cookies,
    }
    try:
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:                            
        log.exception("сбой: %s", exc)
        if args.cmd == "run":
            schedule_next(RETRY_ON_ERROR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
