#!/usr/bin/env bash
# Настройка на своей машине — для входа через Steam и выгрузки куки.
#
#   ./scripts/dev-setup.sh
#
# Playwright пока не собирается под Python 3.14, поэтому берём 3.11–3.13.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        case "$version" in
            3.1[0-3]) PY=$candidate; break ;;
        esac
    fi
done
[[ -n "${PY:-}" ]] || { echo "Нужен Python 3.10–3.13, найти не удалось" >&2; exit 1; }
echo "==> Python: $PY ($version)"

[[ -x venv/bin/python ]] || "$PY" -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt
./venv/bin/playwright install chromium

if [[ ! -f .env ]]; then
    cp .env.example .env
    # Локально окно нужно: через него вы входите в Steam.
    sed -i '' 's/^HEADLESS=.*/HEADLESS=0/' .env 2>/dev/null ||
        sed -i 's/^HEADLESS=.*/HEADLESS=0/' .env
    echo "==> создан .env (HEADLESS=0 — окно браузера показывается)"
fi

cat <<'EOF'

Готово. Дальше:
  ./scripts/mr login     вход через Steam (окно браузера, пароль вводите вы)
  ./scripts/mr status    проверить сессию
  ./scripts/mr export-cookies state/cookies.json    выгрузить для переноса на VPS
EOF
