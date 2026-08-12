#!/usr/bin/env python3
"""Выгрузка куки magicrust.gg в cookies.json — для бота бесплатного кейса.

Запуск:  python3 get-cookies.py       (на Windows обычно  python get-cookies.py)

Два пути на выбор:
  1. Вход через Steam — откроется окно браузера, вы входите как обычно.
  2. Готовые куки из Firefox, если вы уже вошли на сайт в нём.

Пароль Steam скрипт не видит и никуда не передаёт: сохраняются только куки
сайта magicrust.gg. Получившийся cookies.json отправьте боту в Telegram.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SITE = "https://magicrust.gg/ru"
LOGGED_IN = ".header-top-v2__player"       # блок с ником — виден только после входа
WAIT_MINUTES = 15

FIREFOX_SAME_SITE = {0: "None", 1: "Lax", 2: "Strict"}


def out_file() -> Path:
    """Кладём рядом со скриптом, а если туда нельзя — в текущий каталог."""
    beside = Path(__file__).resolve().parent / "cookies.json"
    return beside if os.access(beside.parent, os.W_OK) else Path("cookies.json").resolve()


def ask(question: str) -> bool:
    return input(question).strip().lower() in ("", "y", "yes", "д", "да")


def keep_ours(cookies: list[dict]) -> list[dict]:
    return [c for c in cookies if "magicrust" in (c.get("domain") or "")]


#  Путь 1: вход через Steam

def ensure_playwright() -> None:
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass

    print("\nДля входа через браузер нужен пакет playwright (~50 МБ) и Chromium (~150 МБ).")
    if not ask("Установить сейчас? [Y/n] "):
        sys.exit("Отменено. Можно воспользоваться выгрузкой из Firefox.")

    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)


def install_browser() -> None:
    print("\nСкачиваю Chromium, это разовая операция…")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def from_login() -> list[dict]:
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=False)
        except Exception:
            install_browser()
            browser = playwright.chromium.launch(headless=False)

        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        page.goto(SITE, wait_until="domcontentloaded", timeout=60_000)

        print(
            "\nОткрылось окно браузера.\n"
            "  1. Нажмите «Войти» → «Войти через Steam».\n"
            "  2. Введите логин, пароль и код Steam Guard.\n"
            "  3. Дождитесь возврата на magicrust.gg — окно закроется само.\n"
            f"Жду до {WAIT_MINUTES} минут. Чтобы прервать — Ctrl+C.\n"
        )

        deadline = time.time() + WAIT_MINUTES * 60
        while time.time() < deadline:
            try:
                if page.locator(LOGGED_IN).count() > 0:
                    page.wait_for_timeout(2000)          # даём сайту дописать куки
                    cookies = keep_ours(context.cookies())
                    browser.close()
                    return cookies
            except Exception:
                print("Окно браузера закрылось раньше времени — вход не завершён.")
                return []
            time.sleep(2)

        browser.close()
    print(f"Вход не завершён за {WAIT_MINUTES} минут.")
    return []


#  Путь 2: готовые куки из Firefox

def firefox_databases() -> list[Path]:
    home = Path.home()
    roots = [
        home / "Library/Application Support/Firefox/Profiles",   # macOS
        home / ".mozilla/firefox",                               # Linux
        Path(os.environ.get("APPDATA", "")) / "Mozilla/Firefox/Profiles",  # Windows
    ]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found += sorted(root.glob("*/cookies.sqlite"))
    return found


def read_firefox(database: Path) -> list[dict]:
    """Firefox держит базу открытой, поэтому читаем копию."""
    workdir = Path(tempfile.mkdtemp(prefix="mr-cookies-"))
    try:
        copy = workdir / "cookies.sqlite"
        shutil.copy2(database, copy)
        for suffix in ("-wal", "-shm"):                  # свежие записи лежат здесь
            extra = database.with_name(database.name + suffix)
            if extra.exists():
                shutil.copy2(extra, copy.with_name(copy.name + suffix))

        connection = sqlite3.connect(copy)
        try:
            rows = connection.execute(
                "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite "
                "FROM moz_cookies WHERE host LIKE ?",
                ("%magicrust%",),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        print(f"  не смог прочитать {database.parent.name}: {exc}")
        return []
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    cookies = []
    for name, value, host, path, expiry, secure, http_only, same_site in rows:
        cookie = {
            "name": name,
            "value": value,
            "domain": host,
            "path": path or "/",
            "secure": bool(secure),
            "httpOnly": bool(http_only),
        }
        if expiry:
            cookie["expires"] = int(expiry)
        if same_site in FIREFOX_SAME_SITE:
            cookie["sameSite"] = FIREFOX_SAME_SITE[same_site]
        cookies.append(cookie)
    return cookies


def from_firefox() -> list[dict]:
    databases = firefox_databases()
    if not databases:
        print("\nПрофиль Firefox не найден. Подойдёт вход через Steam (пункт 1).")
        return []

    print(f"\nНашёл профилей Firefox: {len(databases)}")
    best: list[dict] = []
    for database in databases:
        cookies = read_firefox(database)
        print(f"  {database.parent.name}: куки magicrust.gg — {len(cookies)}")
        if len(cookies) > len(best):
            best = cookies

    if not best:
        print(
            "\nВ Firefox нет куки magicrust.gg. Войдите на сайт в этом браузере "
            "и повторите, либо выберите вход через Steam (пункт 1)."
        )
    return best


#  Точка входа

MENU = """
Как достать куки magicrust.gg?

  1 — войти через Steam в отдельном окне браузера (подойдёт всем)
  2 — взять готовые из Firefox (если вы уже вошли на сайт в нём)

Выбор [1/2]: """


def main() -> int:
    print(__doc__.split("Запуск:")[0].strip())

    choice = input(MENU).strip()
    if choice == "2":
        cookies = from_firefox()
    elif choice == "1":
        cookies = from_login()
    else:
        print("Нужно выбрать 1 или 2.")
        return 1

    if not cookies:
        return 1

    target = out_file()
    target.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass

    print(f"\nГотово: сохранено куки — {len(cookies)}")
    print(f"Файл: {target}")
    print(
        "\nОтправьте этот файл боту в Telegram обычным вложением (скрепка → Файл).\n"
        "В нём ключ доступа к вашему аккаунту на сайте — не выкладывайте его больше никуда.\n"
        "После импорта бот удаляет файл со своей стороны; удалите и свою копию."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("\nПрервано.")
