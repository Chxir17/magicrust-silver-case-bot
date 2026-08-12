from __future__ import annotations

# Расширения-экспортёры пишут sameSite по-своему, Playwright принимает три значения.
SAME_SITE = {
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
    "no_restriction": "None",
}


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
