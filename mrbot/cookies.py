from __future__ import annotations

import json
import re

# Расширения-экспортёры пишут sameSite по-своему, Playwright принимает три значения.
SAME_SITE = {
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
    "no_restriction": "None",
}

SESSION = "magicrust_session"          # без него сессии нет
DOMAIN = "magicrust.gg"

# Как эти куки выставляет сам сайт. XSRF-TOKEN обязан быть читаемым для скриптов
# страницы, иначе не уйдёт заголовок с токеном и кнопка перестанет работать.
HTTP_ONLY = {SESSION, "lang", "currency", "visitor_id"}

COOKIE_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


def normalize(raw) -> list[dict]:
    """Куки magicrust.gg из любого экспорта — в формат Playwright."""
    if not isinstance(raw, list):
        return []

    ready = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name, value = item.get("name"), item.get("value")
        domain = str(item.get("domain") or "").strip()
        if not name or value is None or "magicrust" not in domain:
            continue

        cookie = {
            "name": str(name),
            "value": str(value),
            "domain": domain,
            "path": str(item.get("path") or "/"),
            "httpOnly": bool(item.get("httpOnly")),
            "secure": bool(item.get("secure")),
        }

        # expirationDate — из расширений, expires — из нашего export-cookies.
        expires = item.get("expires", item.get("expirationDate"))
        if isinstance(expires, (int, float)) and expires > 0 and not item.get("session"):
            cookie["expires"] = int(expires)

        same_site = SAME_SITE.get(str(item.get("sameSite") or "").lower())
        if same_site:
            cookie["sameSite"] = same_site

        ready.append(cookie)
    return ready


def from_text(text: str) -> list[dict]:
    """Куки, вставленные сообщением: JSON, пары name=value или одно значение."""
    text = text.strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            return normalize(json.loads(text))
        except json.JSONDecodeError:
            return []

    ready = []
    for chunk in re.split(r"[;\n]+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sign, value = chunk.partition("=")
        # Значение куки — длинная строка без пробелов; именем такое быть не может.
        if sign and value.strip() and COOKIE_NAME.match(name.strip()):
            name, value = name.strip(), value.strip()
        else:
            name, value = SESSION, chunk
        if " " in value:
            continue
        ready.append(
            {
                "name": name,
                "value": value,
                "domain": DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": name in HTTP_ONLY,
            }
        )
    return ready


def has_session(cookies: list[dict]) -> bool:
    return any(cookie.get("name") == SESSION for cookie in cookies)
