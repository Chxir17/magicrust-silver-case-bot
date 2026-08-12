from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

# Корень проекта
ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
USERS_DIR = STATE_DIR / "users"          # по каталогу на игрока
USERS_FILE = STATE_DIR / "users.json"    # реестр доступа
LOG_FILE = STATE_DIR / "bot.log"
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
COOLDOWN_PAD = 8                # запас
RETRY_ON_COOLDOWN = 25          # ретрай при неудаче
RETRY_ON_ERROR = 20             # ретрай при непонятной ошибке
RETRY_ON_NO_SESSION = 90        # сессия умерла, нужен ручной re-login

HISTORY_LEN = 10                # сколько последних открытий помним для /stats

log = logging.getLogger("mrbot")


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


def launcher() -> str:
    return "mr" if shutil.which("mr") else "./scripts/mr"


def headless_flag() -> bool:
    return os.environ.get("HEADLESS", "1") != "0"


def gmod() -> str:
    return os.environ.get("MR_GMOD", "modded")


def scaled(ms: int) -> int:
    try:
        factor = max(1.0, float(os.environ.get("MR_TIMEOUT_SCALE", "1")))
    except ValueError:
        factor = 1.0
    return int(ms * factor)


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
