# Magic Rust — бот бесплатного кейса с серебром

Открывает бесплатный кейс «Бесплатное серебро» на [magicrust.gg](https://magicrust.gg/ru)
раз в 10 часов. Работает через настоящий браузер (Playwright + Chromium), кликая по тем же
кнопкам, что и человек, поэтому не зависит от внутреннего API сайта.

Вход в Steam вы делаете **один раз и сами**, в открытом окне браузера. Скрипт пароль
не запрашивает, не хранит и никуда не передаёт — сохраняется только cookie-сессия сайта
в каталоге `state/profile/`.

---

## Как это устроено

| Шаг | Что происходит |
|-----|----------------|
| 1 | Chromium открывает `magicrust.gg/ru` с сохранённым профилем |
| 2 | Переключает магазин на нужный режим игры (`modded` по умолчанию) |
| 3 | Кликает карточку `data-product="5"` — «Бесплатное серебро» |
| 4 | В открывшейся модалке жмёт «Открыть кейс» |
| 5 | Ловит ответ `/product-buy`, достаёт результат, пишет в лог и Telegram |
| 6 | Ставит следующую попытку на +10 ч 08 мин |

Состояние хранится в `state/state.json`, лог — в `state/bot.log`, скриншот последнего
открытия — `state/last_open.png`.

Что отвечает `/product-buy` (проверено на живом аккаунте):

| Ответ | Значение |
|-------|----------|
| `{"success":true, ...}` | кейс открыт, серебро начислено |
| `{"success":false,"message":"Товар доступен каждые 10 часов"}` | перезарядка ещё идёт |

Оба приходят с кодом **HTTP 200**, так что решает поле `success`, а не статус. Сколько
осталось до конца перезарядки, сайт не сообщает и в интерфейсе таймера не показывает —
бот считает время сам от последнего успешного открытия.

**Важно:** серебро начисляется в том режиме игры, который выбран в магазине.
Бесплатный кейс существует только в режимах `modded` и `vanillax2plus` — в `vanillax2`
и `vanilla` карточка скрыта. Выставьте `MR_GMOD` под тот режим, где вы играете.

---

## 1. Установка локально (для входа в Steam)

Нужен Python 3.10–3.13 (на 3.14 у Playwright ещё нет колёс).

```bash
cd ~/magicrust
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
cp .env.example .env
```

Вход:

```bash
./venv/bin/python bot.py login
```

Откроется окно браузера. Нажмите «Войти» → «Войти через Steam», введите данные Steam
сами. Заодно закройте плашку про cookie кнопкой «Ok» — профиль это запомнит.
Как только сайт покажет ваш ник, окно закроется само.

Проверка:

```bash
./venv/bin/python bot.py status
```

Разовый прогон вручную (откроет кейс прямо сейчас, если он доступен):

```bash
./venv/bin/python bot.py run --force
```

---

## 2. Перенос на VPS

Подойдёт любой Debian/Ubuntu с 1 ГБ RAM.

### 2.1. Подготовка сервера

```bash
sudo adduser --system --group --home /opt/magicrust-bot magicrust
sudo apt update && sudo apt install -y python3-venv rsync
```

Дальше нужно доставить код на сервер — любым из двух способов.

#### Вариант А: из git-репозитория

Удобнее для обновлений: правки уезжают через `git push`, а на сервере подтягиваются
одной командой. Секреты в репозиторий не попадают — `.env` и `state/` перечислены
в `.gitignore`, так что их всё равно переносим отдельно.

```bash
sudo apt install -y git
sudo -u magicrust -H git clone {REPO} /opt/magicrust-bot
```

`git clone` требует пустой каталог. Если `/opt/magicrust-bot` уже создан и не пуст
(например, `adduser` положил туда файлы из `/etc/skel` или код уже переносили через
rsync), подключите репозиторий к существующему каталогу:

```bash
sudo -u magicrust -H git -C /opt/magicrust-bot init
sudo -u magicrust -H git -C /opt/magicrust-bot remote add origin {REPO}
sudo -u magicrust -H git -C /opt/magicrust-bot fetch --depth 1 origin main
sudo -u magicrust -H git -C /opt/magicrust-bot reset --hard origin/main
```

`reset --hard` затрагивает только файлы из репозитория: `.env`, `state/` и `venv/`
он не тронет, потому что они в `.gitignore`.

Обновление кода потом:

```bash
sudo -u magicrust -H git -C /opt/magicrust-bot pull
sudo systemctl restart magicrust-telegram.service
```

Перезапуск нужен только сервису Telegram — он висит постоянно. `magicrust-case`
отрабатывает по таймеру и подхватит новый код на следующем запуске сам.

Команды идут от имени `magicrust`, чтобы файлы остались с правильным владельцем,
а git не ругался на `dubious ownership`. Для приватного репозитория понадобится
deploy key: сгенерируйте ключ через `sudo -u magicrust -H ssh-keygen -t ed25519`
и добавьте `/opt/magicrust-bot/.ssh/id_ed25519.pub` в настройки репозитория.
Для публичного достаточно `https://`-ссылки.

#### Вариант Б: копированием по SSH

Если репозитория нет. Если сервер описан в `~/.ssh/config`, указывайте имя алиаса,
а не IP: блок `Host` срабатывает только на алиас, поэтому с голым адресом rsync уйдёт
на порт 22 и оборвётся на `kex_exchange_identification`.

```bash
rsync -av --exclude venv --exclude state --exclude .env --exclude __pycache__ \
  ~/magicrust/ {HOST}:/tmp/magicrust-bot/
```

`.env` исключён намеренно: в `/tmp` он был бы доступен всем пользователям сервера.
Его переносим отдельно, уже в конце установки.

```bash
sudo cp -rT /tmp/magicrust-bot /opt/magicrust-bot
sudo chown -R magicrust:magicrust /opt/magicrust-bot
```

#### Дальше одинаково для обоих вариантов

```bash
sudo -u magicrust -H python3 -m venv /opt/magicrust-bot/venv
sudo -u magicrust -H /opt/magicrust-bot/venv/bin/pip install -r /opt/magicrust-bot/requirements.txt
sudo /opt/magicrust-bot/venv/bin/playwright install-deps chromium
sudo -u magicrust -H /opt/magicrust-bot/venv/bin/playwright install chromium
```

Теперь `.env` — прямо в конечный каталог, минуя `/tmp`, и с правами `600`
(в нём токен Telegram-бота):

```bash
scp ~/magicrust/.env {HOST}:~/.env.magicrust
ssh {HOST} 'sudo install -o magicrust -g magicrust -m 600 ~/.env.magicrust /opt/magicrust-bot/.env && shred -u ~/.env.magicrust'
```

**На сервере обязательно `HEADLESS=1`** — локально ноль нужен для входа через Steam,
но на VPS без графики Chromium с окном не стартует:

```bash
sudo sed -i 's/^HEADLESS=.*/HEADLESS=1/' /opt/magicrust-bot/.env
```

### 2.2. Перенос сессии

На локальной машине:

```bash
./venv/bin/python bot.py export-cookies state/cookies.json
scp state/cookies.json USER@VPS:/tmp/cookies.json
```

На сервере:

```bash
sudo install -o magicrust -g magicrust -m 600 ~/mr-transfer/cookies.json /opt/magicrust-bot/state/cookies.json
sudo -u magicrust -H /opt/magicrust-bot/venv/bin/python /opt/magicrust-bot/bot.py import-cookies /opt/magicrust-bot/state/cookies.json
sudo -u magicrust -H /opt/magicrust-bot/venv/bin/python /opt/magicrust-bot/bot.py status   # должно показать ваш ник
sudo shred -u /opt/magicrust-bot/state/cookies.json ~/mr-transfer/cookies.json
```

Куки — это ключ от аккаунта на сайте: не выкладывайте файл никуда и удалите после переноса.

**Если сайт не признал перенесённую сессию** (привязка к IP), войдите прямо на VPS через
графический браузер по VNC:

```bash
sudo apt install -y xvfb x11vnc
Xvfb :99 -screen 0 1440x900x24 &
x11vnc -display :99 -localhost -nopw -forever &
# с локальной машины: ssh -L 5900:localhost:5900 USER@VPS
# затем подключитесь VNC-клиентом к localhost:5900
sudo -u magicrust -H env DISPLAY=:99 HEADLESS=0 /opt/magicrust-bot/venv/bin/python /opt/magicrust-bot/bot.py login
```

### 2.3. Автозапуск

```bash
# Файлы перечислены явно: маску раскрывает ваш шелл, а он каталог magicrust не читает.
sudo cp /opt/magicrust-bot/systemd/magicrust-case.service \
        /opt/magicrust-bot/systemd/magicrust-case.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now magicrust-case.timer
```

Таймер будит бота каждые 20 минут; сам бот проверяет свой счётчик и реально жмёт кнопку
только когда 10 часов прошли. Так кейс забирается почти сразу после перезарядки, даже если
VPS перезагружался.

Проверка:

```bash
systemctl list-timers magicrust-case.timer
sudo journalctl -u magicrust-case.service -n 50
```

---

## 3. Уведомления в Telegram (необязательно)

Создайте бота у [@BotFather](https://t.me/BotFather), узнайте свой chat id у
[@userinfobot](https://t.me/userinfobot) и впишите в `.env`:

```
TG_TOKEN=123456:AA...
TG_CHAT_ID=123456789
```

Придут сообщения о каждом открытом кейсе и о том, что сессия протухла и нужен повторный вход.

### Ответы на команды

Уведомления работают в одну сторону и никакого сервиса не требуют. Чтобы бот ещё и
отвечал на `/start`, нужен постоянный опрос Telegram — это отдельная команда:

```bash
python bot.py telegram
```

| Команда | Ответ |
|---------|-------|
| `/start`, `/help` | приветствие и список команд |
| `/status` | когда следующая попытка, сколько кейсов открыто |
| `/last` | что выпало в последний раз и когда |
| `/log` | последние 15 строк журнала |

Разовая проверка без запуска сервиса — напишите боту `/start` в Telegram, затем:

```bash
python bot.py telegram --once
```

Он разберёт накопившиеся сообщения, ответит и выйдет.

**Бот отвечает только на `TG_CHAT_ID` из `.env`.** Токен знаете вы, но сам бот виден в
поиске Telegram: любой может ему написать. Сообщения с чужих chat id пишутся в журнал
и игнорируются.

Автозапуск опроса:

```bash
sudo cp /opt/magicrust-bot/systemd/magicrust-telegram.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now magicrust-telegram.service
```

Это `Type=simple` с `Restart=always` — процесс висит постоянно и переживает разрыв сети,
в отличие от `magicrust-case`, который отрабатывает по таймеру и завершается.

---

## Команды

```bash
python bot.py login                      # разовый вход через Steam
python bot.py status                     # сессия + время следующей попытки
python bot.py run                        # одна попытка (её вызывает systemd)
python bot.py run --force                # игнорировать локальный таймер
python bot.py telegram                   # отвечать на команды в Telegram
python bot.py telegram --once            # разобрать накопившееся и выйти
python bot.py export-cookies FILE        # выгрузить сессию для переноса
python bot.py import-cookies FILE        # загрузить сессию в профиль
```

Переменные окружения (`.env`): `MR_GMOD`, `HEADLESS`, `MR_TZ`, `MR_UA`, `TG_TOKEN`, `TG_CHAT_ID`.

---

## Если что-то сломалось

| Симптом | Что делать |
|---------|-----------|
| `сессия истекла` | `bot.py login` заново (или заново перенести куки) |
| `кейс не виден в режиме ...` | поставить `MR_GMOD=vanillax2plus` |
| `кнопка «Открыть кейс» не найдена` | сайт поменял вёрстку — смотрите `state/last_error.png` и текст модалки в логе |
| `ответ от /product-buy не пришёл` | смотрите `state/last_open.png`: бот всё равно решит по тексту модалки |
| Chromium не стартует на VPS | `sudo playwright install-deps chromium`, проверьте `HEADLESS=1` в `.env` |
| `kex_exchange_identification` при ssh/rsync | используете IP вместо алиаса из `~/.ssh/config` — порт не 22 |
| `cd: /opt/magicrust-bot: Permission denied` | каталог принадлежит `magicrust` (750): не заходите в него, вызывайте `bot.py` по абсолютному пути через `sudo -u magicrust -H` |
| `cannot stat '/opt/magicrust-bot/...*'` | маску раскрывает ваш шелл, а не `sudo` — перечислите файлы полными именами |
| `Trigger: n/a`, `active (elapsed)` у таймера | таймер больше не сработает: обновите юнит на версию с `OnCalendar=` и сделайте `daemon-reload` + `restart` |

Селекторы, на которых всё держится, собраны в начале `bot.py` — если сайт обновят,
менять нужно только их.

---

## Про правила

Бот работает с одним вашим аккаунтом, забирает ровно один бесплатный кейс раз в 10 часов
и не создаёт лишней нагрузки на сайт.
