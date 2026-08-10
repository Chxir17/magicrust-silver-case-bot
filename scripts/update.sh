#!/usr/bin/env bash
# Обновление кода на сервере из git.
#
#   sudo ./scripts/update.sh        (или просто: mr update)
#
# Сам решает, что нужно переустановить: зависимости — только если менялся
# requirements.txt, юниты — только если менялась папка systemd.
set -euo pipefail

# Тело завёрнуто в функцию намеренно: скрипт делает git reset в каталоге,
# из которого запущен, а bash читает файл по мере выполнения. Внутри функции
# он разбирает весь текст сразу, и подмена файла на ходу уже не страшна.
main() {

    DIR=/opt/magicrust-bot
    USER_NAME=magicrust
    BRANCH=${BRANCH:-master}

    step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
    die() { echo "Ошибка: $*" >&2; exit 1; }

    [[ $(id -u) == 0 ]] || die "запускать через sudo"
    [[ -d "$DIR/.git" ]] || die "$DIR не подключён к git — сначала scripts/install.sh"

    as_bot() { sudo -u "$USER_NAME" -H "$@"; }

    before=$(as_bot git -C "$DIR" rev-parse HEAD)

    step "Забираю $BRANCH"
    as_bot git -C "$DIR" fetch --depth 1 origin "$BRANCH"
    as_bot git -C "$DIR" reset --hard "origin/$BRANCH"
    after=$(as_bot git -C "$DIR" rev-parse HEAD)

    if [[ "$before" == "$after" ]]; then
        echo "уже последняя версия ($(as_bot git -C "$DIR" log -1 --oneline))"
        exit 0
    fi

    changed=$(as_bot git -C "$DIR" diff --name-only "$before" "$after")
    echo "изменилось файлов: $(wc -l <<<"$changed")"

    if grep -q '^requirements.txt$' <<<"$changed"; then
        step "Зависимости"
        as_bot "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
    fi

    if grep -q '^systemd/' <<<"$changed"; then
        step "Юниты systemd"
        cp "$DIR/systemd/magicrust-case.service" "$DIR/systemd/magicrust-case.timer" /etc/systemd/system/
        if [[ -f "$DIR/systemd/magicrust-telegram.service" ]]; then
            cp "$DIR/systemd/magicrust-telegram.service" /etc/systemd/system/
        fi
        systemctl daemon-reload
        systemctl restart magicrust-case.timer
    fi

    if grep -q '^scripts/mr$' <<<"$changed"; then
        install -m 755 "$DIR/scripts/mr" /usr/local/bin/mr
    fi

    # magicrust-case это oneshot: он подхватит новый код на следующем тике таймера.
    # А опрос Telegram висит постоянно, поэтому его перезапускаем всегда.
    if systemctl is-active --quiet magicrust-telegram.service; then
        step "Перезапуск Telegram-сервиса"
        systemctl restart magicrust-telegram.service
    fi

    step "Готово: $(as_bot git -C "$DIR" log -1 --oneline)"
    systemctl list-timers magicrust-case.timer --no-pager
}

main "$@"
