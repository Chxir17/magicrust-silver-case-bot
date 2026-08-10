"""
Magic Rust — автооткрытие бесплатного кейса с серебром.

Команды:
    bot.py login            вход через Steam вручную (откроется окно браузера)
    bot.py status           состояние сессии и время следующей попытки
    bot.py run              одна попытка открыть кейс (для systemd/cron)
    bot.py run --force      попытаться, даже если по таймеру ещё рано
    bot.py telegram         отвечать на /start, /status, /stats в Telegram
    bot.py telegram --once  разобрать накопившееся и выйти (проверка)
    bot.py export-cookies [файл]    выгрузить куки (перенос на VPS)
    bot.py import-cookies <файл>    загрузить куки в профиль

Пароль Steam вводите только вы сами в окне браузера — скрипт его не знает,
не хранит и никуда не отправляет. Сохраняется лишь cookie-сессия сайта.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from magicrust.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
