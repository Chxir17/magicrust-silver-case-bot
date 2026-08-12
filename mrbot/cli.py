from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import users
from .browser import browser_context, goto_site, is_logged_in, nickname_of, open_site
from .case import attempt_open
from .config import (
    RETRY_ON_ERROR,
    headless_flag,
    launcher,
    load_env,
    log,
    setup_logging,
)
from .cookies import normalize
from .fmt import human_delta, local, now, parse_dt
from .state import attempt_status, read_state, schedule_next, single_run, write_state
from .telegram import poll
from .texts import Cli

# Сколько ждать чужой Chromium, прежде чем сдаться (браузер один на весь бот).
WAIT_FOR_LOCK = 150


def chosen(args) -> users.Account | None:
    """Игрок из --user, иначе владелец бота."""
    wanted = getattr(args, "user", None)
    if not wanted:
        return users.default()
    account = users.resolve(wanted)
    if account is None:
        log.error(Cli.NO_SUCH_USER.format(id=wanted))
    return account


def cmd_login(args) -> int:
    account = chosen(args)
    if account is None:
        return 1

    print(Cli.LOGIN_STEPS)
    with users.use(account), single_run(WAIT_FOR_LOCK), sync_playwright() as playwright:
        context = browser_context(playwright, headless=False)
        page = goto_site(context)
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            try:
                if is_logged_in(page):
                    log.info("вход выполнен, сессия сохранена в %s", account.profile_dir)
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


def cmd_status(args) -> int:
    account = chosen(args)
    if account is None:
        return 1

    with users.use(account):
        state = read_state()
        with single_run(WAIT_FOR_LOCK), sync_playwright() as playwright:
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
    if args.user:
        account = chosen(args)
        if account is None:
            return 1
        everyone = [account]
    else:
        # Тем, кто ещё не прислал куки, автоматика не пишет — только по /run.
        everyone = [
            account
            for account in (users.accounts() or [users.default()])
            if account.profile_dir.exists()
        ]

    # Отбор до запуска Playwright: чаще всего срабатывание таймера холостое.
    queue = [account for account in everyone if is_due(account, args.force)]
    if not queue:
        return 0
    if not headless_flag():
        log.warning("HEADLESS=0 — окно браузера видимое, не закрывайте его до конца прогона")

    try:
        with single_run():
            return run_queue(queue)
    except RuntimeError as exc:
        log.warning("%s — пропускаю запуск", exc)
        return 0


def is_due(account: users.Account, force: bool) -> bool:
    nxt = parse_dt(read_state(account).get("next_attempt"))
    if not force and nxt and now() < nxt:
        log.info("%s: ещё рано, следующая попытка через %s", account.title, human_delta(nxt))
        return False
    return True


def run_queue(queue: list[users.Account]) -> int:
    """Игроки обходятся по очереди: Chromium тяжёлый, параллелить нечем."""
    code = 0
    with sync_playwright() as playwright:
        for account in queue:
            if len(queue) > 1:
                log.info("очередь: %s", account.title)
            with users.use(account):
                code = run_one(playwright) or code
    return code


def run_one(playwright) -> int:
    try:
        context = browser_context(playwright, headless=headless_flag())
        try:
            return attempt_open(context)
        finally:
            context.close()
    except Exception as exc:
        log.exception("сбой у %s: %s", users.current().title, exc)
        schedule_next(RETRY_ON_ERROR)
        return 1


def cmd_telegram(args) -> int:
    return poll(once=args.once)


def cmd_export_cookies(args) -> int:
    account = chosen(args)
    if account is None:
        return 1

    target = Path(args.file or account.dir / "cookies.json")
    with users.use(account), single_run(WAIT_FOR_LOCK), sync_playwright() as playwright:
        context = browser_context(playwright, headless=headless_flag())
        open_site(context)
        cookies = context.cookies()
        context.close()

    keep = normalize(cookies)
    if not keep:
        print(Cli.COOKIES_EMPTY)
        return 1
    target.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(Cli.COOKIES_SAVED.format(count=len(keep), path=target))
    print(Cli.COOKIES_HINT)
    return 0


def cmd_import_cookies(args) -> int:
    account = chosen(args)
    if account is None:
        return 1

    cookies = normalize(json.loads(Path(args.file).read_text(encoding="utf-8")))
    if not cookies:
        print(Cli.COOKIES_EMPTY)
        return 1

    with users.use(account), single_run(WAIT_FOR_LOCK), sync_playwright() as playwright:
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

    def with_user(command):
        command.add_argument("--user", help="chat_id игрока (по умолчанию — владелец бота)")
        return command

    with_user(sub.add_parser("login", help="разовый вход через Steam"))
    with_user(sub.add_parser("status", help="состояние сессии и таймера"))

    run_parser = with_user(sub.add_parser("run", help="попытка открыть кейс"))
    run_parser.add_argument("--force", action="store_true", help="игнорировать локальный таймер")

    tg_parser = sub.add_parser("telegram", help="отвечать на команды в Telegram")
    tg_parser.add_argument(
        "--once", action="store_true", help="разобрать накопившееся и выйти (для проверки)"
    )

    export_parser = with_user(
        sub.add_parser("export-cookies", help="выгрузить куки для переноса на VPS")
    )
    export_parser.add_argument("file", nargs="?")

    import_parser = with_user(sub.add_parser("import-cookies", help="загрузить куки в профиль"))
    import_parser.add_argument("file")
    return parser


def main() -> int:
    load_env()
    setup_logging()
    args = build_parser().parse_args()
    users.bootstrap()
    try:
        return HANDLERS[args.cmd](args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        log.exception("сбой: %s", exc)
        if args.cmd == "run":
            schedule_next(RETRY_ON_ERROR)
        return 1
