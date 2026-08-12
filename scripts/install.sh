#!/usr/bin/env bash
# Установка бота на сервер. Идемпотентно — можно запускать повторно.
#
#   sudo ./scripts/install.sh https://github.com/USER/REPO.git
#
# Если репозиторий уже подключён, ссылку можно не указывать.
# Скрипт НЕ трогает .env, state/ и сессию сайта.
set -euo pipefail

# Тело завёрнуто в функцию намеренно: скрипт делает git reset в каталоге,
# из которого запущен, а bash читает файл по мере выполнения. Внутри функции
# он разбирает весь текст сразу, и подмена файла на ходу уже не страшна.
main() {

    DIR=/opt/magicrust-bot
    USER_NAME=magicrust
    BRANCH=${BRANCH:-master}
    REPO=${1:-}

    step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
    die() { echo "Ошибка: $*" >&2; exit 1; }

    [[ $(id -u) == 0 ]] || die "запускать через sudo"

    step "Пакеты"
    apt-get update -qq
    apt-get install -y -qq python3-venv git

    step "Пользователь $USER_NAME"
    if id "$USER_NAME" &>/dev/null; then
        echo "уже есть"
    else
        adduser --system --group --home "$DIR" "$USER_NAME"
    fi
    mkdir -p "$DIR"
    chown "$USER_NAME:$USER_NAME" "$DIR"

    step "Код"
    # Все git-команды от имени magicrust: иначе файлы окажутся с чужим владельцем,
    # а git будет ругаться на dubious ownership.
    as_bot() { sudo -u "$USER_NAME" -H "$@"; }

    if [[ -d "$DIR/.git" ]]; then
        echo "репозиторий уже подключён"
    else
        [[ -n "$REPO" ]] || die "первый запуск: укажите ссылку на репозиторий аргументом"
        as_bot git -C "$DIR" init -q
        as_bot git -C "$DIR" remote add origin "$REPO"
    fi
    if [[ -n "$REPO" ]]; then
        as_bot git -C "$DIR" remote set-url origin "$REPO"
    fi
    as_bot git -C "$DIR" fetch --depth 1 origin "$BRANCH"
    as_bot git -C "$DIR" reset --hard "origin/$BRANCH"

    step "Python и Chromium"
    [[ -x "$DIR/venv/bin/python" ]] || as_bot python3 -m venv "$DIR/venv"
    as_bot "$DIR/venv/bin/pip" install -q --upgrade pip
    as_bot "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
    # install-deps ставит системные библиотеки, поэтому от root; сам браузер — от
    # magicrust с -H, иначе он уедет в домашний каталог того, кто набрал sudo.
    "$DIR/venv/bin/playwright" install-deps chromium
    as_bot "$DIR/venv/bin/playwright" install chromium

    step "Настройки"
    if [[ -f "$DIR/.env" ]]; then
        echo ".env уже есть, не трогаю"
    else
        install -o "$USER_NAME" -g "$USER_NAME" -m 600 "$DIR/.env.example" "$DIR/.env"
        echo "создан $DIR/.env — впишите TG_TOKEN и TG_CHAT_ID"
    fi
    # На сервере окно рисовать негде.
    sed -i 's/^HEADLESS=.*/HEADLESS=1/' "$DIR/.env"
    install -o "$USER_NAME" -g "$USER_NAME" -m 700 -d "$DIR/state"

    step "systemd"
    cp "$DIR/systemd/magicrust-case.service" "$DIR/systemd/magicrust-case.timer" /etc/systemd/system/
    if [[ -f "$DIR/systemd/magicrust-telegram.service" ]]; then
        cp "$DIR/systemd/magicrust-telegram.service" /etc/systemd/system/
    fi
    systemctl daemon-reload
    systemctl enable --now magicrust-case.timer

    install -m 755 "$DIR/scripts/mr" /usr/local/bin/mr

    cat <<EOF

Готово. Дальше:
  1. Впишите TG_TOKEN и свой TG_CHAT_ID: nano $DIR/.env
  2. Включите ответы в Telegram:  systemctl enable --now magicrust-telegram.service
  3. Пришлите боту куки файлом (подскажет /login) или: mr import-cookies /tmp/cookies.json
  4. Проверьте:                   mr status

Остальных игроков добавляйте из чата: они пишут боту /start, вы — /approve id

Расписание: mr timer      Журнал: mr logs
EOF
}

main "$@"
