"""
Рушій, що виконує TransferSchema: читає джерело (COM), пише приймач
(BridgeTool), запускає хуки у визначених точках пайплайна, і каскадно
переносить пов'язані довідники за related_catalogs. Замінює
fetch_catalog.py + write_catalog.py (Phase 7 - вони видаляються).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from pathlib import Path

from migrator import hooks
from migrator.cascade import plan_cascade
from migrator.config import REPO_ROOT
from migrator.schema import TransferSchema

# BridgeTool/bridge_client.py - НЕ пакет migrator, а окремий скрипт-клієнт
# (Bridge1C, query_via_com) у сусідній папці; підключаємо через sys.path,
# а не копіюємо код, щоб лишався ОДИН джерело істини для протоколу обміну.
BRIDGETOOL_DIR = REPO_ROOT / "BridgeTool"
if str(BRIDGETOOL_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGETOOL_DIR))

import bridge_client  # noqa: E402


@dataclass
class TransferResult:
    kind: str
    name: str
    fetched: int = 0
    write_summary: str = ""
    cascaded: list[str] = dc_field(default_factory=list)


class TransferContext:
    """Передається у кожен хук. rows/query/item/index/total/result -
    рантайм-стан поточного кроку пайплайна, який engine.py виставляє
    безпосередньо перед відповідним run(stage, ...)."""

    def __init__(self, schema: TransferSchema, engine: "TransferEngine"):
        self.schema = schema
        self._engine = engine
        self.query: str = ""
        self.rows: list[dict] = []
        self.item: dict | None = None
        self.index: int = 0
        self.total: int = 0
        self.result: str = ""

    def log(self, message: str) -> None:
        self._engine.log(message)


class TransferEngine:
    def __init__(self, schema: TransferSchema, bridge: "bridge_client.Bridge1C | None" = None,
                 session_dir: Path | None = None):
        self.schema = schema
        self.session_dir = session_dir
        self.bridge = bridge or self._build_bridge(schema)
        if session_dir and self.bridge.session_log is None:
            # Лог життєвого циклу запуску (Python-сторона) і лог, куди САМ
            # BridgeTool (BSL) пише bridge_startup.log - обидва в ту саму
            # сесійну папку, поруч з engine.log/write_progress.log.
            self.bridge.session_log = session_dir / "session.log"
            self.bridge.bridge_log_dir = session_dir

    @staticmethod
    def _build_bridge(schema: TransferSchema) -> "bridge_client.Bridge1C":
        dest = schema.destination
        platform_exe = dest.platform_exe or bridge_client.DEV.platform_exe
        connect_args = dest.connect_args or bridge_client.DEV.connect_args
        return bridge_client.Bridge1C(platform_exe=platform_exe, connect_args=connect_args)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} {message}"
        print(line)
        if self.session_dir:
            try:
                self.session_dir.mkdir(parents=True, exist_ok=True)
                with open(self.session_dir / "engine.log", "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

    def run(self, limit: int | None = None, depth: int = 0, visited: set[str] | None = None) -> TransferResult:
        # Лише НАЙЗОВНІШНІЙ виклик (depth=0) керує життєвим циклом
        # BridgeTool - каскадні під-рушії (Phase: _cascade) переДають ТОЙ
        # САМИЙ вже запущений bridge і не повинні зупиняти його передчасно.
        if depth == 0:
            with self.bridge:
                return self._run(limit=limit, depth=depth, visited=visited)
        return self._run(limit=limit, depth=depth, visited=visited)

    def _run(self, limit: int | None, depth: int, visited: set[str] | None) -> TransferResult:
        visited = visited if visited is not None else set()
        schema = self.schema
        ctx = TransferContext(schema, self)

        ctx.query = schema.select_query(limit=limit)
        hooks.run("before_read", ctx, schema.hooks)

        self.log(f"Читання {schema.kind}.{schema.name} (джерело: {schema.source.connection})")
        if schema.source.connection != "com":
            raise ValueError(f"Непідтримуване джерело: {schema.source.connection!r}")
        rows = bridge_client.query_via_com(schema.source.connection_string, ctx.query)
        self.log(f"Отримано {len(rows)} записів.")
        ctx.rows = rows

        hooks.run("before_write", ctx, schema.hooks)

        progress_log = str(self.session_dir / "write_progress.log") if self.session_dir else None
        result_summary = self._write(schema, rows, ctx, progress_log)

        ctx.result = result_summary
        hooks.run("after_write", ctx, schema.hooks)

        result = TransferResult(kind=schema.kind, name=schema.name, fetched=len(rows), write_summary=result_summary)

        visited.add(f"{schema.kind}.{schema.name}")
        for rule in plan_cascade(rows, schema.related_catalogs):
            if rule.ref_type in visited:
                continue
            if depth >= rule.depth:
                self.log(f"Каскад {rule.ref_type} пропущено - глибина {depth} досягла ліміту {rule.depth}")
                continue
            self._cascade(rule, depth, visited)
            result.cascaded.append(rule.ref_type)

        return result

    def _write(self, schema: TransferSchema, rows: list[dict], ctx: TransferContext, progress_log: str | None) -> str:
        per_item_hooks = schema.hooks_for("after_each_item")
        if not per_item_hooks:
            return self.bridge.write_items(schema.kind, schema.name, rows, progress_log=progress_log)

        # after_each_item вимагає СПРАВЖНЬОЇ пооб'єктної гранулярності -
        # пишемо по одному рядку за раз (BridgeTool вже запущений, тож
        # overhead - лише файловий обмін, не перезапуск 1cv8.exe).
        summaries = []
        total = len(rows)
        for index, row in enumerate(rows, start=1):
            summaries.append(self.bridge.write_items(schema.kind, schema.name, [row], progress_log=progress_log))
            ctx.item, ctx.index, ctx.total = row, index, total
            hooks.run("after_each_item", ctx, per_item_hooks)
        total_count = sum(int(s.split("Итого: ")[1].split(",")[0]) for s in summaries if "Итого: " in s)
        success_count = sum(int(s.split("Успешно: ")[1].split("\n")[0]) for s in summaries if "Успешно: " in s)
        return f"Итого: {total_count}, Успешно: {success_count}"

    def _cascade(self, rule, depth: int, visited: set[str]) -> None:
        ref_kind, ref_name = rule.ref_type.split(".", 1)
        self.log(f"Каскад: {rule.ref_type} (detail={rule.detail}, depth={depth + 1}/{rule.depth})")

        if rule.detail == "reference_only":
            query = f"ВЫБРАТЬ * ИЗ {rule.ref_type}"
            rows = bridge_client.query_via_com(self.schema.source.connection_string, query)
            self.log(f"Каскад {rule.ref_type}: отримано {len(rows)} записів.")
            summary = self.bridge.write_items(ref_kind, ref_name, rows)
            self.log(f"Каскад {rule.ref_type}: {summary.splitlines()[0] if summary else summary}")
            visited.add(rule.ref_type)
            return

        # detail == "full": рекурсивно проганяємо ПОВНИЙ рушій для цього
        # довідника - без власного schema.yaml це означає SELECT * і без
        # ЙОГО ВЛАСНИХ related_catalogs (генеричний passthrough).
        sub_schema = TransferSchema(
            task=f"{self.schema.task}::{ref_name}",
            kind=ref_kind,
            name=ref_name,
            source=self.schema.source,
            destination=self.schema.destination,
        )
        TransferEngine(sub_schema, bridge=self.bridge, session_dir=self.session_dir).run(depth=depth + 1, visited=visited)
