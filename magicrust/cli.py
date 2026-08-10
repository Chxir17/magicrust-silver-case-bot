from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from .browser import browser_context, goto_site, is_logged_in, nickname_of, open_site
from .case import attempt_open
from .config import (
    PROFILE_DIR,
    RETRY_ON_ERROR,
    STATE_DIR,
    headless_flag,
    launcher,
    load_env,
    log,
    setup_logging,
)
from .fmt import human_delta, local, now, parse_dt
from .state import attempt_status, read_state, schedule_next, single_run, write_state
from .telegram import poll
from .texts import Cli


def cmd_login(_args) -> int:
    print(Cli.LOGIN_STEPS)
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=False)
        page = goto_site(context)
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            try:
                if is_logged_in(page):
                    log.info("вход выполнен, сессия сохранена в %s", PROFILE_DIR)
                    write_state(logged_in_at=now().isoformat())
                    page.wait_for_timeout(2000)
                    context.close()
                    print(Cli.LOGIN_DONE.format(mr=launcher()))
                    return 0
            except Exception:                                 
                pass
            time.sleep(2)
        context.close()
    log.error(Cli.LOGIN_TIMEOUT)
    return 1


def cmd_status(_args) -> int:
    state = read_state()
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        page = open_site(context)
        authorized = is_logged_in(page)
        nickname = nickname_of(page)
        context.close()

    if authorized:
        suffix = Cli.SESSION_NICKNAME.format(nickname=nickname) if nickname else ""
        print(Cli.SESSION_OK.format(nickname=suffix))
    else:
        print(Cli.SESSION_NONE.format(mr=launcher()))

    last = parse_dt(state.get("last_open"))
    print(Cli.STATUS_LAST_OPEN.format(when=local(last) if last else Cli.STATUS_NEVER))
    if state.get("last_win"):
        print(Cli.STATUS_WIN.format(win=state["last_win"]))
    if attempt_status(state):
        print(Cli.STATUS_ATTEMPT.format(status=attempt_status(state)))
    nxt = parse_dt(state.get("next_attempt"))
    if nxt:
        print(Cli.STATUS_NEXT.format(when=local(nxt), left=human_delta(nxt)))
    return 0 if authorized else 1


def cmd_run(args) -> int:
    nxt = parse_dt(read_state().get("next_attempt"))
    if nxt and now() < nxt and not args.force:
        log.info("ещё рано, следующая попытка через %s", human_delta(nxt))
        return 0

    if not headless_flag():
        log.warning("HEADLESS=0 — окно браузера видимое, не закрывайте его до конца прогона")

    try:
        with single_run(), sync_playwright() as playwright:
            context = browser_context(playwright, headless=headless_flag())
            try:
                return attempt_open(context)
            finally:
                context.close()
    except RuntimeError as exc:
        log.warning("%s — пропускаю запуск", exc)
        return 0


def cmd_telegram(args) -> int:
    return poll(once=args.once)


def cmd_export_cookies(args) -> int:
    target = Path(args.file or STATE_DIR / "cookies.json")
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        open_site(context)
        cookies = context.cookies()
        context.close()
    keep = [c for c in cookies if "magicrust" in c.get("domain", "")]
    target.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(Cli.COOKIES_SAVED.format(count=len(keep), path=target))
    print(Cli.COOKIES_HINT)
    return 0


def cmd_import_cookies(args) -> int:
    cookies = json.loads(Path(args.file).read_text(encoding="utf-8"))
    with sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        context.add_cookies(cookies)
        page = open_site(context)
        ok = is_logged_in(page)
        context.close()
    print(Cli.COOKIES_IMPORTED if ok else Cli.COOKIES_GUEST)
    return 0 if ok else 1


HANDLERS = {
    "login": cmd_login,
    "status": cmd_status,
    "run": cmd_run,
    "telegram": cmd_telegram,
    "export-cookies": cmd_export_cookies,
    "import-cookies": cmd_import_cookies,
}


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def main() -> int:
    load_env()
    setup_logging()
    args = build_parser().parse_args()
    try:
        return HANDLERS[args.cmd](args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:                                 
        log.exception("сбой: %s", exc)
        if args.cmd == "run":
            schedule_next(RETRY_ON_ERROR)
        return 1
