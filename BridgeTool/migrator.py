"""
Клієнт для BridgeTool.epf + com_query.ps1.

Архітектура (за вимогою користувача): BridgeTool має доступ ЛИШЕ до своєї
власної (DEV) бази і НІКОЛИ не встановлює зовнішніх з'єднань. Джерело даних
(TEST_SKI_HIRE) читається виключно через окремий процес (com_query.ps1,
COM), який керується звідси, з Python. Тобто:

    BridgeTool (DEV, локально) <-> цей Python-скрипт <- COM -> TEST_SKI_HIRE

BridgeTool сам не знає нічого про конкретні довідники/документи - лише
"виконати вираз" (call_expression) і два універсальних примітиви поверх
нього (query/write_items).
"""

import datetime
import json
import subprocess
import time
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
COM_QUERY_SCRIPT = TOOL_DIR / "com_query.ps1"
POWERSHELL_32BIT = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
# Тимчасовий файл для query_via_com() - НЕ частина протоколу обміну з
# BridgeTool (це окремий процес com_query.ps1), тому лишається в самому
# інструменті, а не в папці обміну конкретного завдання.
COM_QUERY_SCRATCH = TOOL_DIR / "_com_query_result.json"
# Bootstrap-файл: єдиний ЗАХАРДКОЖЕНИЙ (і в Python, і в BSL) шлях у всій
# системі - через нього BridgeTool дізнається СВОЮ папку обміну і папку
# логу при кожному запуску (ЗапускПараметр() недоступна зовнішнім
# обробкам, тому командний рядок як канал передачі не підходить).
LAUNCH_CONFIG_FILE = TOOL_DIR / "_launch_config.txt"


def _running_1c_client_pids() -> list[str]:
    """PID-и всіх запущених 1cv8.exe (товстий клієнт), якщо є."""
    proc = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq 1cv8.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True,
    )
    pids = []
    for line in proc.stdout.strip().splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "1cv8.exe":
            pids.append(parts[1])
    return pids


def ensure_no_running_clients() -> None:
    """
    Перевіряє, що немає вже запущених 1cv8.exe, ПЕРШ НІЖ запускати новий -
    щоб одразу побачити конфлікт (наприклад, недозавершену попередню сесію
    чи ручний тест користувача), а не отримати незрозумілу помилку
    "The application is unavailable" чи таймаут пізніше.
    """
    pids = _running_1c_client_pids()
    if pids:
        raise RuntimeError(
            f"Уже запущено {len(pids)} процес(и) 1cv8.exe (PID: {', '.join(pids)}). "
            "Закрийте їх (або зачекайте завершення попередньої сесії) перед новим запуском - "
            "паралельні сесії проти файлової бази можуть спричиняти конфлікти доступу."
        )


class Bridge1C:
    """
    Одна база = одна ціль виконання (шлях/версія платформи + як підключатись).

    BridgeTool тепер ЗАПУСКАЄТЬСЯ ОДИН РАЗ (start()) і сам стежить за новими
    запитами у циклі (ПодключитьОбработчикОжидания у формі) - не треба
    перезапускати 1cv8.exe (~20-30 сек) на кожен виклик. Використовуйте як
    контекстний менеджер:

        with DEV:
            DEV.write_items(...)
            DEV.write_items(...)  # той самий процес, без повторного запуску
    """

    def __init__(self, platform_exe: str, connect_args: list[str], exchange_dir: str | None = None):
        """
        platform_exe   - шлях до 1cv8.exe (версія платформи, що ВІДПОВІДАЄ цій базі)
        connect_args   - аргументи підключення для 1cv8.exe, наприклад:
                          ["/F", r"D:\\Bukovel\\EDT_BASE\\SKI"]                (файлова база)
                          ["/S", "REN-SER-DB1\\TEST_SKI_HIRE"]                  (серверна база)
        exchange_dir   - папка обміну (ready.txt/request.json/stop.txt) - НЕ
                         захардкожена в BridgeTool, а передається йому при
                         запуску через параметр командного рядка (ЗапускПараметр()).
                         Кожне завдання переносу може мати свою власну папку
                         обміну - тому це поле, а не константа. Можна змінити
                         в будь-який момент ДО start()/call_expression().
        """
        self.platform_exe = platform_exe
        self.connect_args = connect_args
        self.epf_path = str(TOOL_DIR / "BridgeTool.epf")
        self.exchange_dir = Path(exchange_dir) if exchange_dir else TOOL_DIR / "bridge"
        self._proc: subprocess.Popen | None = None
        # Опціонально: шлях до лог-файлу ЖИТТЄВОГО ЦИКЛУ запуску (спроба
        # старту / готовність / таймаут) - визначає той, ХТО ВИКЛИКАЄ
        # (кожне завдання переносу - свій лог у своїй папці), щоб було видно
        # прогрес навіть якщо BridgeTool так і не стартував (до появи
        # ready.txt), а не тільки після успішного підключення. Це пише сам
        # Python (зовнішнє спостереження), а не BridgeTool.
        self.session_log: Path | None = None
        # Опціонально: папка, куди САМ BridgeTool (BSL, зсередини) пише
        # bridge_startup.log - передається йому через /C, так само як
        # exchange_dir. Якщо не задано - BridgeTool не веде цей лог.
        self.bridge_log_dir: Path | None = None

    def _log(self, message: str) -> None:
        if not self.session_log:
            return
        try:
            Path(self.session_log).parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.session_log, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} {message}\n")
        except OSError:
            pass

    def _build_launch_command(self) -> str:
        """
        Повертає ГОТОВИЙ рядок команди (не список!) - той самий, що вводиться
        вручну в PowerShell. subprocess.Popen зі СПИСКОМ аргументів на Windows
        пропускає кожен елемент через list2cmdline(), яка екранує лапки, що
        вже є ВСЕРЕДИНІ елемента (наприклад /F"...") зворотним слешем -
        1cv8.exe отримує спотворену команду. Рядок Popen використовує "як є".
        """
        parts = [f'"{self.platform_exe}"', "ENTERPRISE"]
        i = 0
        while i < len(self.connect_args):
            flag = self.connect_args[i]
            if flag == "/F":
                parts.append(f'/F"{self.connect_args[i + 1]}"')
                i += 2
            elif flag == "/S":
                parts += ["/S", self.connect_args[i + 1]]
                i += 2
            else:
                parts.append(flag)
                i += 1
        parts.append(f'/Execute"{self.epf_path}"')
        # BridgeTool - технічний автоматизований клієнт, не повинен брати на
        # себе виконання регламентних завдань бази (у файловому режимі це
        # робить ПЕРШИЙ клієнт, що підключився) - інакше він конкурує за
        # внутрішні блокування (ACTIVEUSERS/DATAZONEOBJECTLOCKS) з іншими
        # сесіями і це спричиняє довгі затримки/зависання при старті.
        parts.append("/AllowExecuteScheduledJobs -off")
        return " ".join(parts)

    def start(self, ready_timeout: int = 150) -> None:
        """Запустити BridgeTool один раз і дочекатись, поки він почне відповідати."""
        if self._proc is not None and self._proc.poll() is None:
            return  # вже запущено

        ensure_no_running_clients()
        self.exchange_dir.mkdir(parents=True, exist_ok=True)

        ready_file = self.exchange_dir / "ready.txt"
        if ready_file.exists():
            ready_file.unlink()

        launch_config_lines = [str(self.exchange_dir)]
        if self.bridge_log_dir:
            launch_config_lines.append(str(self.bridge_log_dir))
        LAUNCH_CONFIG_FILE.write_text("\n".join(launch_config_lines), encoding="utf-8-sig")

        self._log(f"Спроба запуску BridgeTool (epf={self.epf_path}, exchange={self.exchange_dir})")
        launch_time = time.monotonic()
        self._proc = subprocess.Popen(self._build_launch_command())
        self._log(f"Процес 1cv8.exe запущено (PID={self._proc.pid}), чекаю ready.txt (таймаут {ready_timeout}с)")

        # Чекаємо ready.txt (пишеться формою одразу при відкритті) - це
        # точний момент, коли застосунок готовий, БЕЗ часу на обробку
        # самого запиту. Дає чіткий діагноз: чи взагалі стартував застосунок.
        elapsed = 0
        poll_interval = 1
        while not ready_file.exists() and elapsed < ready_timeout and self._proc.poll() is None:
            time.sleep(poll_interval)
            elapsed += poll_interval

        if not ready_file.exists():
            exited = self._proc.poll() is not None
            self._log(
                f"ПОМИЛКА: ready.txt не з'явився за {elapsed}с "
                f"(процес {'завершився сам' if exited else 'ще виконується, буде примусово завершено'})"
            )
            self.stop()
            raise TimeoutError(
                f"BridgeTool не подав ознак життя (ready.txt) за {elapsed} сек "
                f"(процес {'завершився сам' if exited else 'ще виконується, примусово завершено'}). "
                "Найімовірніша причина: застосунок показав діалог помилки "
                "('The application is unavailable...') замість запуску - "
                "перевірте Активні користувачі / застарілі сесії в базі."
            )

        startup_time = time.monotonic() - launch_time
        self._log(f"BridgeTool готовий за {startup_time:.1f} сек")
        print(f"[BridgeTool готовий за {startup_time:.1f} сек]")

        # Ще один "пінг" через повний цикл запит/відповідь - переконатись,
        # що цикл очікування (ПодключитьОбработчикОжидания) справді працює,
        # а не лише що форма відкрилась.
        try:
            self.call_expression("1+1", timeout=30)
        except Exception:
            self.stop()
            raise

    def stop(self, graceful_timeout: int = 15) -> None:
        """
        Завершити BridgeTool ШТАТНО (сигнал stop.txt -> ЗавершитьРаботуСистемы
        зсередини самої 1С-сесії) - так база коректно звільняє блокування.
        Примусове завершення процесу - лише запасний варіант, якщо штатне
        не спрацювало за graceful_timeout секунд.
        """
        if self._proc is None or self._proc.poll() is not None:
            self._proc = None
            return

        stop_file = self.exchange_dir / "stop.txt"
        try:
            stop_file.write_text("stop", encoding="utf-8")
        except OSError:
            pass

        elapsed = 0
        while self._proc.poll() is None and elapsed < graceful_timeout:
            time.sleep(1)
            elapsed += 1

        if self._proc.poll() is None:
            # Штатне завершення не спрацювало вчасно - запасний варіант.
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

        self._proc = None

    def __enter__(self) -> "Bridge1C":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def call_expression(self, expression: str, timeout: int = 90) -> dict:
        """
        Виконує один 1С-вираз у вже запущеному BridgeTool і повертає
        розпарсений результат: {"ok": True, "value": ...} або {"ok": False, "error": "..."}.
        Якщо BridgeTool ще не запущений - запускає його автоматично (одноразово).
        """
        if self._proc is None or self._proc.poll() is not None:
            self.start()
            if expression == "1+1":
                # start() вже виконав саме цей вираз як "пінг" - не дублюємо виклик.
                return {"ok": True, "value": 2}

        request_file = self.exchange_dir / "request.json"
        result_file = self.exchange_dir / "request.json.result.json"

        if result_file.exists():
            result_file.unlink()

        request = {"expression": expression}
        request_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8-sig")

        elapsed = 0
        poll_interval = 1
        while not result_file.exists() and elapsed < timeout and self._proc.poll() is None:
            time.sleep(poll_interval)
            elapsed += poll_interval

        result_text = None
        if result_file.exists():
            result_text = result_file.read_text(encoding="utf-8-sig")

        if result_text is None:
            raise TimeoutError(
                f"BridgeTool не відповів за {timeout} сек (вираз: {expression[:80]}...)"
            )

        return json.loads(result_text)

    def query(self, query_text: str) -> list[dict]:
        """Виконати запит У ЦІЙ (локальній) базі і отримати рядки."""
        expr = _bsl_call("ВыполнитьЗапрос", query_text)
        result = self.call_expression(expr)
        if not result.get("ok"):
            raise RuntimeError(f"Query failed: {result.get('error')}")
        return result["value"]

    def write_items(self, kind: str, name: str, rows: list[dict], progress_log: str | None = None) -> str:
        """
        Записати рядки (у форматі, який повертає query()) у довідник/документ
        ЦІЄЇ бази. progress_log - опціональний шлях до файлу, куди BridgeTool
        писатиме прогрес ПООБ'ЄКТНО (одразу після кожного запису) - шлях
        визначає той, ХТО ВИКЛИКАЄ (кожне завдання переносу - свій лог у
        своїй папці), BridgeTool сам нічого не знає про конкретні завдання.
        """
        rows_json = json.dumps(rows, ensure_ascii=False)
        args = [_bsl_string_literal(kind), _bsl_string_literal(name), _bsl_string_literal(rows_json)]
        if progress_log:
            args.append(_bsl_string_literal(progress_log))
        expr = f"ЗаписатиЕлементи({', '.join(args)})"
        result = self.call_expression(expr, timeout=300)
        if not result.get("ok"):
            raise RuntimeError(f"Write failed: {result.get('error')}")
        return result["value"]


def query_via_com(connection_string: str, query_text: str, timeout: int = 120) -> list[dict]:
    """
    Читає дані з ІНШОЇ бази 1С через COM - виконується окремим процесом
    (32-бітний PowerShell, бо V83.COMConnector зареєстрований лише для
    32-біт), НЕ через BridgeTool. Повертає рядки у форматі, сумісному з
    Bridge1C.write_items().
    """
    out_file = COM_QUERY_SCRATCH
    if out_file.exists():
        out_file.unlink()

    args = [
        POWERSHELL_32BIT, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COM_QUERY_SCRIPT),
        "-ConnectionString", connection_string,
        "-QueryText", query_text,
        "-OutFile", str(out_file),
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"com_query.ps1 failed: {proc.stderr or proc.stdout}")
    if not out_file.exists():
        raise RuntimeError(f"com_query.ps1 didn't produce output: {proc.stdout}")

    return json.loads(out_file.read_text(encoding="utf-8"))


def _bsl_string_literal(value: str) -> str:
    """Python-рядок -> 1С рядковий літерал (подвоєння лапок)."""
    return '"' + value.replace('"', '""') + '"'


def _bsl_call(func_name: str, *string_args: str) -> str:
    """Побудувати вираз виклику функції з рядковими аргументами."""
    args = ", ".join(_bsl_string_literal(a) for a in string_args)
    return f"{func_name}({args})"


def _bsl_call_raw_last(func_name: str, string_args: list[str], raw_json_arg: str) -> str:
    """Як _bsl_call, але останній аргумент - це вже готовий JSON-текст, який
    треба передати як 1С-рядковий літерал (а не структуру!) - функція сама
    розпарсить його через ПрочитатьJSON."""
    args = ", ".join(_bsl_string_literal(a) for a in string_args)
    args += ", " + _bsl_string_literal(raw_json_arg)
    return f"{func_name}({args})"


# Готові конфігурації підключення для наших двох баз.
DEV = Bridge1C(
    platform_exe=r"D:\Programs\BAF\8.3.23.2299\bin\1cv8.exe",
    connect_args=["/F", r"D:\Bukovel\EDT_BASE\SKI"],
)

TEST_SKI_HIRE_CONNECTION_STRING = 'Srvr="REN-SER-DB1";Ref="TEST_SKI_HIRE";'
