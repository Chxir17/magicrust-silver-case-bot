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
sudo apt update && sudo apt install -y python3-venv git
```

### 2.2. Код на сервер из git

Основной способ: правки уезжают через `git push`, на сервере подтягиваются одной
командой, и всегда видно, какая версия там развёрнута. Секреты в репозиторий не
попадают — `.env` и `state/` перечислены в `.gitignore`, поэтому их переносим отдельно.

```bash
sudo apt install -y git
sudo -u magicrust -H git clone {REPO} /opt/magicrust-bot
```

Команды идут от имени `magicrust`, иначе файлы окажутся с чужим владельцем, сервис не
сможет их прочитать, а git выругается на `dubious ownership`. Флаг `-H` подставляет
`HOME=/opt/magicrust-bot`, без него git и Playwright полезут в домашний каталог того,
кто набрал `sudo`.

`git clone` требует пустой каталог. Если `/opt/magicrust-bot` уже создан и не пуст
(`adduser` положил туда файлы из `/etc/skel`, или код уже переносили через rsync),
подключите репозиторий к существующему каталогу:

```bash
sudo -u magicrust -H git -C /opt/magicrust-bot init
sudo -u magicrust -H git -C /opt/magicrust-bot remote add origin {REPO}
sudo -u magicrust -H git -C /opt/magicrust-bot fetch --depth 1 origin master
sudo -u magicrust -H git -C /opt/magicrust-bot reset --hard origin/master
```

Ветка здесь `master` — подставьте свою, если в репозитории она называется иначе;
`git branch -r` покажет список.

`reset --hard` трогает только файлы из репозитория: `.env`, `state/` и `venv/` он не
видит, они в `.gitignore`. Так что сессия сайта и расписание переживают обновление.

Чтобы GitHub не спрашивал логин и токен на каждый `fetch`, заведите deploy key:

```bash
sudo -u magicrust -H ssh-keygen -t ed25519 -N '' -f /opt/magicrust-bot/.ssh/id_ed25519
sudo cat /opt/magicrust-bot/.ssh/id_ed25519.pub
```

Содержимое добавьте в Deploy keys репозитория, затем переключите remote на SSH:

```bash
sudo -u magicrust -H git -C /opt/magicrust-bot remote set-url origin git@github.com:USER/REPO.git
```

### 2.3. Окружение и секреты

```bash
sudo -u magicrust -H python3 -m venv /opt/magicrust-bot/venv
sudo -u magicrust -H /opt/magicrust-bot/venv/bin/pip install -r /opt/magicrust-bot/requirements.txt
sudo /opt/magicrust-bot/venv/bin/playwright install-deps chromium
sudo -u magicrust -H /opt/magicrust-bot/venv/bin/playwright install chromium
```

`.env` в репозиторий не попадает — переносим его отдельно, прямо в конечный каталог
и с правами `600` (в нём токен Telegram-бота):

```bash
scp ~/magicrust/.env {HOST}:~/.env.magicrust
ssh {HOST} 'sudo install -o magicrust -g magicrust -m 600 ~/.env.magicrust /opt/magicrust-bot/.env && shred -u ~/.env.magicrust'
```

**На сервере обязательно `HEADLESS=1`** — локально ноль нужен для входа через Steam,
но на VPS без графики Chromium с окном не стартует:

```bash
sudo sed -i 's/^HEADLESS=.*/HEADLESS=1/' /opt/magicrust-bot/.env
```

### 2.4. Перенос сессии

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

### 2.5. Автозапуск

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

В колонке `NEXT` должно стоять конкретное время. Если там `n/a`, а `systemctl status`
показывает `active (elapsed)` — таймер больше не сработает, см. таблицу в конце.

### 2.6. Запасной вариант: копирование по SSH

Если репозитория нет. Обновлять потом придётся вручную тем же способом, поэтому вариант
с git удобнее. Когда сервер описан в `~/.ssh/config`, указывайте имя алиаса, а не IP:
блок `Host` срабатывает только на алиас, поэтому с голым адресом rsync уйдёт на порт 22
и оборвётся на `kex_exchange_identification`.

```bash
rsync -av --exclude venv --exclude state --exclude .env --exclude __pycache__ \
  ~/magicrust/ {HOST}:/tmp/magicrust-bot/
```

`.env` исключён намеренно: в `/tmp` он был бы доступен всем пользователям сервера.

```bash
sudo cp -rT /tmp/magicrust-bot /opt/magicrust-bot
sudo chown -R magicrust:magicrust /opt/magicrust-bot
```

Дальше — те же шаги 2.3–2.5, что и при установке из git.

---

## 3. Обновление кода

### На своей машине

Сначала проверьте, что уходит в коммит: `.env` и `state/` перечислены в `.gitignore`,
токен и сессия остаться должны за бортом.

```bash
cd ~/magicrust && git status --short
```

```bash
cd ~/magicrust && git add -A && git commit -m "что изменилось" && git push origin master
```

### На сервере

Не `pull`, а `fetch` + `reset --hard`: серверу не нужны слияния, нужно точное совпадение
с репозиторием. Заодно это обходит `no tracking information`, если репозиторий
подключался через `init`, а не `clone`.

```bash
sudo -u magicrust -H git -C /opt/magicrust-bot fetch --depth 1 origin master && sudo -u magicrust -H git -C /opt/magicrust-bot reset --hard origin/master
```

Что делать после, зависит от того, что менялось в коммите:

| Что менялось | Что сделать |
|---|---|
| только код `bot.py` | ничего, таймер подхватит на следующем тике |
| `systemd/*` | скопировать юниты в `/etc/systemd/system/` и `sudo systemctl daemon-reload` |
| `requirements.txt` | `sudo -u magicrust -H /opt/magicrust-bot/venv/bin/pip install -r /opt/magicrust-bot/requirements.txt` |
| логика Telegram-бота | `sudo systemctl restart magicrust-telegram.service` |

Юниты одной командой, если они менялись:

```bash
sudo cp /opt/magicrust-bot/systemd/magicrust-case.service /opt/magicrust-bot/systemd/magicrust-case.timer /opt/magicrust-bot/systemd/magicrust-telegram.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart magicrust-case.timer
```

`magicrust-case` перезапускать не нужно — это `oneshot`, он завершается сам и
на следующем тике таймера стартует уже с новым кодом. А `magicrust-telegram` висит
постоянно, поэтому новый код увидит только после `restart`.

---

## 4. Уведомления в Telegram (необязательно)

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
| `/stats` | история последних открытий: сколько выпало каждый раз, среднее, лучшее и худшее, сумма за всё время |
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
| `клик по ... перекрыт` в логе | непринятая плашка cookie закрывает низ страницы; поставьте `MR_ACCEPT_COOKIE=1` или нажмите «Ok» вручную при `bot.py login` |
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
