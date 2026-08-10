from __future__ import annotations

#Telegram
class Chat:

    GREETING = (
        "Бот открытия кейса с серебром на Magic Rust.\n"
        "Кейс «Бесплатное серебро» открывается раз в 10 часов, "
        "результат приходит в этот чат.\n\n"
        "Информация:\n"
        "/status — время следующей попытки и счётчики\n"
        "/last — результат прошлого открытия\n"
        "/stats — история открытий\n"
        "/log — последние строки журнала\n"
        "/timer — расписание таймера\n\n"
        "Действия:\n"
        "/run — попытка открыть кейс\n"
        "/run force — попытка без учёта расписания\n"
        "/check — проверка сессии через браузер\n"
        "/restart — перезапуск сервисов\n"
        "/update — обновление кода из репозитория\n"
        "/login — перенос сессии Steam"
    )

    UNKNOWN = "Команда не найдена. /start — список команд"

    LOGIN_HELP = (
        "Вход в Steam выполняется на компьютере\n"
        "1. ./scripts/mr login\n"
        "2. ./scripts/mr export-cookies state/cookies.json\n"
        "3. Отправьте cookies.json в этот чат файлом.\n\n"
        "Файл содержит ключ доступа к аккаунту и проходит через серверы Telegram.\n"
        "После импорта он удаляется. Альтернатива — перенос через scp, см. README."
    )

    #/status
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
    COOKIES_HINT = "Перенесите файл на сервер и выполните: mr import-cookies cookies.json"
    COOKIES_IMPORTED = "Сессия перенесена."
    COOKIES_GUEST = "Куки загружены, но сессия гостевая — требуется login"

#подсказка, которую Telegram показывает при вводе «/»
class Menu:

    COMMANDS = [
        ("status", "Время следующей попытки и счётчики"),
        ("last", "Результат прошлого открытия"),
        ("stats", "История открытий"),
        ("run", "Попытка открыть кейс"),
        ("check", "Проверка сессии через браузер"),
        ("timer", "Расписание таймера"),
        ("log", "Последние строки журнала"),
        ("restart", "Перезапуск сервисов"),
        ("update", "Обновление кода из репозитория"),
        ("login", "Перенос сессии Steam"),
        ("version", "Развёрнутая версия"),
        ("help", "Список команд"),
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
