from __future__ import annotations

import os
import sys

from playwright.sync_api import TimeoutError as PWTimeout

from .config import (
    CARD,
    GMOD_BTN,
    LOGGED_IN,
    PRODUCT_ID,
    PROFILE_DIR,
    SITE,
    gmod,
    log,
    scaled,
    user_agent,
)


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

    log.info("запускаю Chromium (headless=%s)", headless)
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
    context.set_default_timeout(scaled(30_000))
    return context


def goto_site(context):
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(SITE, wait_until="domcontentloaded", timeout=scaled(60_000))
    return page


def open_site(context):
    page = goto_site(context)
    page.wait_for_selector(GMOD_BTN, timeout=scaled(30_000))
    dismiss_promo(page)
    select_gmod(page)
    return page


def dismiss_promo(page) -> None:
    targets = [".cohort-popup__close"]
    if os.environ.get("MR_ACCEPT_COOKIE") == "1":
        targets.append(".magic-cookie .accept-cookie")

    for selector in targets:
        element = page.locator(selector)
        try:
            if element.count() and element.first.is_visible():
                element.first.click(timeout=3000)
                page.wait_for_timeout(300)
        except Exception:                                   
            pass                                            


def click_element(locator, what: str, timeout: int | None = None) -> None:
    timeout = timeout if timeout is not None else scaled(10_000)
    try:
        locator.scroll_into_view_if_needed(timeout=timeout)
    except Exception:                                       
        pass
    try:
        locator.click(timeout=timeout)
    except PWTimeout:
        log.warning("клик по %s перекрыт, шлю событие напрямую", what)
        locator.dispatch_event("click")


def select_gmod(page) -> None:
    target = gmod()
    button = page.locator(f'{GMOD_BTN}[data-gmod="{target}"]')
    if button.count() == 0:
        available = page.locator(GMOD_BTN).evaluate_all("els => els.map(e => e.dataset.gmod)")
        raise RuntimeError(f"режим {target!r} не найден, доступны: {available}")

    if "active" not in (button.first.get_attribute("class") or ""):
        button.first.click()
        page.wait_for_timeout(800)

    try:
        page.wait_for_selector(CARD, state="visible", timeout=scaled(15_000))
    except PWTimeout as exc:
        raise RuntimeError(
            f"кейс (product {PRODUCT_ID}) не виден в режиме {target!r} — "
            f"попробуйте MR_GMOD=vanillax2plus"
        ) from exc


def is_logged_in(page) -> bool:
    return page.locator(LOGGED_IN).count() > 0


def nickname_of(page) -> str:
    if not is_logged_in(page):
        return ""
    lines = page.locator(LOGGED_IN).first.inner_text().splitlines()
    return next((line.strip() for line in lines if line.strip()), "")
