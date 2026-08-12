from __future__ import annotations

#Telegram
class Chat:

    GREETING = (
        "Бот открытия кейса с серебром на Magic Rust.\n"
        "Кейс «Бесплатное серебро» открывается раз в 10 часов на вашем аккаунте, "
        "результат приходит в этот чат.\n\n"
        "Начало работы: /cookies — программа для выгрузки куки, "
        "/login — как это сделать другими способами.\n\n"
        "Информация:\n"
        "/status — время следующей попытки и счётчики\n"
        "/last — результат прошлого открытия\n"
        "/stats — история открытий\n\n"
        "Действия:\n"
        "/run — попытка открыть кейс\n"
        "/run force — попытка без учёта расписания\n"
        "/check — проверка сессии через браузер"
    )

    GREETING_ADMIN = GREETING + (
        "\n\nАдминистратор:\n"
        "/users — игроки и заявки на доступ\n"
        "/approve id — выдать доступ\n"
        "/remove id — забрать доступ и стереть сессию\n"
        "/log — последние строки журнала\n"
        "/timer — расписание таймера\n"
        "/restart — перезапуск сервисов\n"
        "/update — обновление кода из репозитория\n"
        "/version — версия бота"
    )

    UNKNOWN = "Команда не найдена. /start — список команд"

    LOGIN_HELP = (
        "Бот открывает кейс от вашего имени, для этого ему нужны куки magicrust.gg.\n\n"
        "Способ 1 — /cookies\n"
        "Бот пришлёт небольшую программу. Запускаете её у себя на компьютере, "
        "входите в Steam в открывшемся окне (или она сама возьмёт куки из Firefox), "
        "рядом появляется cookies.json — присылаете его сюда.\n\n"
        "Способ 2 — расширение для браузера (Cookie-Editor и подобные):\n"
        "1. Войдите на magicrust.gg через Steam в своём браузере.\n"
        "2. Экспортируйте куки сайта в формате JSON.\n"
        "3. Пришлите файл в этот чат.\n\n"
        "Файл содержит ключ доступа к аккаунту и проходит через серверы Telegram. "
        "После импорта он удаляется. Пароль Steam боту не нужен и никуда не передаётся."
    )

    #/cookies
    TOOL_CAPTION = (
        "Программа для выгрузки куки. Запустите у себя на компьютере:\n\n"
        "python3 get-cookies.py\n\n"
        "(на Windows обычно python get-cookies.py)\n\n"
        "Она предложит два пути: войти через Steam в открывшемся окне браузера или "
        "забрать готовые куки из Firefox. Рядом со скриптом появится cookies.json — "
        "пришлите его сюда файлом.\n\n"
        "Нужен установленный Python 3. Пароль Steam программа не видит."
    )
    TOOL_MISSING = "Программа не найдена на сервере. Сообщите администратору: /cookies"
    TOOL_NOT_SENT = "Не удалось отправить файл, попробуйте ещё раз."

    #доступ
    NO_ACCESS = (
        "Доступа к боту нет.\n"
        "Ваш id: {id} — передайте его администратору, заявка уже отправлена."
    )
    ACCESS_REQUEST = (
        "Заявка на доступ: {who}\n"
        "Выдать: /approve {id}"
    )
    ADMIN_ONLY = "Команда доступна только администратору."
    ACCESS_GRANTED = (
        "Доступ выдан. Осталось передать боту куки magicrust.gg: /cookies пришлёт "
        "программу, которая их выгрузит, /login — про другие способы."
    )
    ACCESS_REVOKED = "Доступ к боту закрыт, сессия удалена с сервера."

    #управление игроками
    USAGE_ID = "Укажите id: {command} 123456789"
    BAD_ID = "id состоит из цифр, получено: {value}"
    ADDED = "Доступ выдан: {who}"
    ALREADY_ADDED = "Доступ уже был: {who}"
    REMOVED = "Доступ закрыт, данные удалены: {id}"
    NOT_A_USER = "Игрок {id} не найден."
    SELF_REMOVE = "Себя удалить нельзя — администратор задан в .env"
    USERS_HEAD = "Игроки ({count}):"
    USERS_ROW = "  {who}{admin} — {status}"
    USERS_ADMIN_MARK = " · админ"
    USERS_NO_SESSION = "сессия не передана"
    USERS_IDLE = "готов к попытке"
    USERS_NEXT = "следующая попытка через {left}"
    USERS_OPENS = " · открыто {opens}"
    PENDING_HEAD = "Заявки ({count}):"
    PENDING_ROW = "  {who} — /approve {id}"
    NO_USERS = "Игроков нет."

    #уведомления из фоновой попытки
    PUSH_OPENED = "Magic Rust: кейс открыт — {result}"
    PUSH_SESSION_LOST = (
        "Magic Rust: сессия истекла, нужен повторный вход через Steam. Инструкция — /login"
    )

    #/status
    NO_SESSION_YET = "Сессия не передана — пришлите куки файлом, инструкция /login"
    NEVER_OPENED = "Кейс ещё не открывался"
    LAST_OPEN = "Последнее открытие: {when}"
    NEXT_TRY = "Следующая попытка: {when} (через {left})"
    NEXT_TRY_SOON = "Следующая попытка: при ближайшем срабатывании таймера"
    LAST_SILVER = "Последний результат: {silver} серебра"
    TOTAL_OPENS = "Открыто кейсов: {opens}"
    TOTAL_SILVER = ", собрано {silver} серебра"
    LAST_STATUS = "Итог последней попытки: {status}"

    #/last
    NEVER_OPENED_DOT = "Кейс ещё не открывался."
    LAST_WIN_AT = "{when} — {win}"
    LAST_WIN = "Прошлое открытие: {win}"

    #/stats
    NO_HISTORY = "История пуста."
    HISTORY_HEAD = "Последние {count} {word}:"
    HISTORY_ROW = "  {when} — {value}"
    HISTORY_SILVER = "{silver} серебра"
    HISTORY_UNKNOWN = "количество не определено"
    AVERAGE = "Среднее за открытие: {silver} серебра"
    BEST_WORST = "Максимум: {best}, минимум: {worst}"
    GRAND_TOTAL = "Всего собрано: {silver} серебра за {opens} {word}"

    #/log
    EMPTY_LOG = "Журнал пуст."

    #/version
    VERSION = "Версия: {version}\nДоступные команды: {commands}"

    #подтверждения перед долгими командами
    ACK_RUN = "Попытка открытия запущена."
    ACK_CHECK = "Выполняется проверка сессии."
    ACK_TIMER = "Запрос расписания."
    ACK_RESTART = "Выполняется перезапуск сервисов."
    ACK_UPDATE = "Выполняется обновление кода."

    #/run
    TOO_EARLY = (
        "Ещё рано: следующая попытка {when}, через {left}.\n"
        "Запуск без учёта расписания — /run force"
    )
    OPENED = "Кейс открыт — {win}."
    OPENED_NO_DETAILS = "результат не определён"
    FAILED_SESSION = (
        "Попытка не удалась: сессия истекла, требуется повторный вход. "
        "Инструкция — /login"
    )
    FAILED_COOLDOWN = "Попытка не удалась: кейс на перезарядке."
    FAILED_UNKNOWN = "Попытка не удалась.\n\n{details}"
    FAILED_SILENT = "процесс не вернул вывода"
    NEXT_AFTER = "\nСледующая попытка {when}, через {left}."

    #приём файла с куками
    COOKIES_EXPECTED = "Ожидается файл cookies.json. Инструкция — /login"
    COOKIES_TOO_BIG = "Файл слишком большой для набора куки."
    COOKIES_NOT_FETCHED = "Не удалось получить файл от Telegram."
    COOKIES_UNREADABLE = "Файл не читается: {error}"
    COOKIES_WRONG_SHAPE = "Неверный формат: ожидался список объектов."
    COOKIES_NOT_OURS = (
        "В файле нет куки magicrust.gg — выгрузите куки именно этого сайта. /login"
    )

    #выполнение команд
    NO_PROGRAM = "Программа не найдена: {program}"
    TIMED_OUT = "Команда прервана по таймауту ({minutes} мин)."
    DONE = "Готово."
    EXIT_CODE = "\n\nКоманда завершилась с ошибкой (код {code})."
    NO_GIT = "каталог не подключён к git"
    NEED_ROOT = (
        "Требуются права root, помощник не установлен.\n"
        "Выполните на сервере:\n"
        "sudo /opt/magicrust-bot/scripts/enable-remote-admin.sh"
    )

#вывод команд в терминале.
class Cli:
    LOGIN_STEPS = (
        "\nОткроется окно браузера.\n"
        "  1. Нажмите «Войти» → «Войти через Steam».\n"
        "  2. Введите логин, пароль и код Steam Guard.\n"
        "     Пароль скриптом не читается и не сохраняется, остаётся только cookie сайта.\n"
        "  3. Дождитесь возврата на magicrust.gg, окно закроется автоматически.\n"
        "Закройте плашку про cookie кнопкой «Ok»: профиль запомнит это,\n"
        "и она перестанет перекрывать страницу при автозапусках.\n"
    )
    LOGIN_DONE = "\nГотово. Проверка: {mr} status\n"
    LOGIN_TIMEOUT = "вход не завершён за 15 минут"

    SESSION_OK = "Сессия:          активна{nickname}"
    SESSION_NICKNAME = " — {nickname}"
    SESSION_NONE = "Сессия:          нет (требуется {mr} login)"
    STATUS_LAST_OPEN = "Последнее открытие: {when}"
    STATUS_NEVER = "ещё не открывался"
    STATUS_WIN = "Результат:       {win}"
    STATUS_ATTEMPT = "Итог попытки:    {status}"
    STATUS_NEXT = "Следующая проба: {when} (через {left})"

    COOKIES_SAVED = "Сохранено куки: {count} → {path}"
    COOKIES_HINT = "Отправьте файл боту в Telegram или выполните: mr import-cookies cookies.json"
    COOKIES_IMPORTED = "Сессия перенесена."
    COOKIES_GUEST = "Куки загружены, но сессия гостевая — требуется login"
    COOKIES_EMPTY = "В файле нет куки magicrust.gg."
    NO_SUCH_USER = "Игрок {id} не найден в реестре."

#подсказка, которую Telegram показывает при вводе «/»
class Menu:

    USER = [
        ("status", "Время следующей попытки и счётчики"),
        ("last", "Результат прошлого открытия"),
        ("stats", "История открытий"),
        ("run", "Попытка открыть кейс"),
        ("check", "Проверка сессии через браузер"),
        ("cookies", "Прислать программу для выгрузки куки"),
        ("login", "Перенос сессии Steam"),
        ("help", "Список команд"),
    ]

    ADMIN = USER + [
        ("users", "Игроки и заявки на доступ"),
        ("approve", "Выдать доступ по id"),
        ("remove", "Забрать доступ по id"),
        ("timer", "Расписание таймера"),
        ("log", "Последние строки журнала"),
        ("restart", "Перезапуск сервисов"),
        ("update", "Обновление кода из репозитория"),
        ("version", "Развёрнутая версия"),
    ]


class Words:
    OPENINGS = ("открытие", "открытия", "открытий")
    CASES = ("кейс", "кейса", "кейсов")


class Time:
    NOW = "сейчас"
    HOURS_MINUTES = "{hours} ч {minutes} мин"
    MINUTES = "{minutes} мин"
    UNKNOWN_DATE = "—"
    DATE_FORMAT = "%H:%M %d.%m"
