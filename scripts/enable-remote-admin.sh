#!/usr/bin/env bash
# Разрешает Telegram-командам /restart и /update работать от root.
#
#   sudo ./scripts/enable-remote-admin.sh
#
# Ставит root-помощник в /usr/local/sbin и правило sudo ровно на два его
# действия. Без этого скрипта команды отвечают, что помощник не установлен,
# а всё остальное (/run, /status, /timer, приём куки) работает и так.
#
# Отключить: sudo rm /etc/sudoers.d/magicrust /usr/local/sbin/magicrust-admin
set -euo pipefail

DIR=/opt/magicrust-bot
USER_NAME=magicrust
HELPER=/usr/local/sbin/magicrust-admin
RULES=/etc/sudoers.d/magicrust

[[ $(id -u) == 0 ]] || { echo "Запускать через sudo" >&2; exit 1; }
id "$USER_NAME" &>/dev/null || { echo "Нет пользователя $USER_NAME" >&2; exit 1; }

install -o root -g root -m 755 "$DIR/scripts/magicrust-admin" "$HELPER"

cat > "$RULES" <<EOF
# Только два действия и только они: помощник принадлежит root, поэтому
# подменить его содержимое из-под magicrust нельзя.
$USER_NAME ALL=(root) NOPASSWD: $HELPER restart, $HELPER update
EOF
chmod 440 "$RULES"

if ! visudo -cf "$RULES"; then
    rm -f "$RULES"
    echo "Правило sudo отклонено, изменения откачены" >&2
    exit 1
fi

echo "Готово. Проверка:"
sudo -u "$USER_NAME" sudo -n "$HELPER" 2>&1 | tail -1 || true
cat <<'EOF'

Теперь в Telegram работают /restart и /update.

Учтите: каталог /opt/magicrust-bot доступен на запись пользователю magicrust,
и `restart` копирует юниты оттуда в /etc/systemd/system. Тот, кто получит
доступ к боту, сможет через это поднять права до root. На выделенной машине
под один бот это приемлемо; если нет — не включайте, а перезапускайте руками.
EOF
