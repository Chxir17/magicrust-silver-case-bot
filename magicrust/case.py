from __future__ import annotations

import json
import re
from datetime import timedelta

from playwright.sync_api import TimeoutError as PWTimeout

from .browser import click_element, is_logged_in, open_site
from .config import (
    AUTH_BTN,
    CARD,
    COOLDOWN_MIN,
    COOLDOWN_PAD,
    MODAL,
    OPEN_BTN,
    RETRY_ON_COOLDOWN,
    RETRY_ON_ERROR,
    RETRY_ON_NO_SESSION,
    STATE_DIR,
    log,
    scaled,
)
from .fmt import amount, human_delta, now, parse_dt
from .state import read_state, record_open, schedule_at, schedule_next, write_state
from .telegram import notify

COOLDOWN_WORDS = re.compile(
    r"подожд|недоступ|уже\s+(получ|открыл|забра)|попробуйте\s+позже|осталось|"
    r"доступен\s+кажд|кажд\w*\s+\d+\s*час|раз\s+в\s+\d+\s*час|"
    r"cooldown|too\s+many|not\s+available|every\s+\d+\s*hour",
    re.I,
)

STATIC_FILES = re.compile(r"\.(png|jpe?g|gif|svg|css|js|woff2?|ico)(\?|$)", re.I)


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


def payload_is_error(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("success", "status", "ok", "result"):
        value = payload.get(key)
        if value is False or (isinstance(value, str) and value.lower() == "error"):
            return True
    return bool(payload.get("error") or payload.get("errors"))


def session_lost(reason: str) -> int:
    log.error("%s — нужен повторный вход (bot.py login)", reason)
    write_state(last_status="сессия истекла")
    schedule_next(RETRY_ON_NO_SESSION)
    notify("Magic Rust: сессия истекла, нужен повторный вход через Steam")
    return 2


def attempt_open(context) -> int:
    page = open_site(context)

    if not is_logged_in(page):
        return session_lost("сессия недействительна")

    click_element(page.locator(CARD).first, "карточке кейса")
    page.wait_for_selector(f"{MODAL}.modal-on", timeout=scaled(15_000))
    page.wait_for_timeout(1200)                  

    if page.locator(AUTH_BTN).count() > 0:
        return session_lost("в модалке кнопка входа")

    button = page.locator(OPEN_BTN).first
    if button.count() == 0:
        text = page.locator(MODAL).inner_text().strip()
        log.error("кнопка «Открыть кейс» не найдена. Текст модалки:\n%s", text[:500])
        page.screenshot(path=str(STATE_DIR / "last_error.png"), full_page=False)
        write_state(last_status="кнопка не найдена")
        schedule_next(RETRY_ON_ERROR)
        return 3

    log.info("нажимаю «%s»", button.inner_text().strip())
    status, body = click_and_capture(page, button)
    payload = parse_payload(body)
    message = str(payload.get("message") or "").strip() if isinstance(payload, dict) else ""

    log.info("HTTP %s | ответ: %s", status, (body or "—")[:600])
    if message:
        log.info("сообщение сайта: %s", message)

    modal_text = settle_and_snapshot(page)

    if status == 200 and payload is not None and not payload_is_error(payload):
        return on_success(payload)
    if COOLDOWN_WORDS.search(f"{message} {body} {modal_text}") or status in (403, 419, 429):
        return on_cooldown(message)

    log.error("непонятный результат (HTTP %s), скриншот: %s", status, STATE_DIR / "last_open.png")
    write_state(last_status=f"ошибка HTTP {status}")
    schedule_next(RETRY_ON_ERROR)
    return 3


def click_and_capture(page, button) -> tuple[int | None, str]:
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))

    try:
        with page.expect_response(
            lambda r: "product-buy" in r.url and "product-buy-state" not in r.url,
            timeout=scaled(45_000),
        ) as info:
            click_element(button, "кнопке «Открыть кейс»")
        response = info.value
        try:
            return response.status, response.text()
        except Exception:                                
            return response.status, ""
    except PWTimeout:
        log.warning("ответ от /product-buy не пришёл — смотрю по странице")
        interesting = [url for url in requests if not STATIC_FILES.search(url)]
        if interesting:
            log.warning(
                "запросы после клика (%d): %s", len(interesting), "; ".join(interesting[-10:])
            )
        else:
            log.warning("после клика страница не сделала ни одного запроса — клик не сработал")
        return None, ""


def parse_payload(body: str):
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def settle_and_snapshot(page) -> str:
    try:
        page.wait_for_timeout(9000)
        modal_text = " ".join(page.locator(MODAL).inner_text().split())
        page.screenshot(path=str(STATE_DIR / "last_open.png"))
        log.info("модалка: %s", modal_text[:300])
        return modal_text
    except Exception as exc:                              
        log.warning(
            "страница закрылась до конца анимации (%s) — сужу по ответу сервера",
            type(exc).__name__,
        )
        return ""


def on_success(payload) -> int:
    silver = find_silver(payload)
    result = f"выпало {amount(silver)} серебра" if silver else "кейс открыт"
    log.info("УСПЕХ: %s", result)
    record_open(silver, result, payload)
    schedule_next(COOLDOWN_MIN + COOLDOWN_PAD, jitter=10)
    notify(f"Magic Rust: кейс открыт — {result}")
    return 0


def on_cooldown(message: str) -> int:
    write_state(last_status=f"перезарядка: {message}" if message else "перезарядка")
    last = parse_dt(read_state().get("last_open"))
    target = last + timedelta(minutes=COOLDOWN_MIN + COOLDOWN_PAD) if last else None
    if target and target > now():
        schedule_at(target)
        log.info("кейс на перезарядке, следующая попытка через %s", human_delta(target))
    else:
        schedule_next(RETRY_ON_COOLDOWN)
        log.info("кейс на перезарядке, повтор через ~%s мин", RETRY_ON_COOLDOWN)
    return 0
