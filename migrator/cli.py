"""
Командний рядок Migrator.

    python -m migrator run <root>:<task> [--limit N] [--log-dir DIR]
    python -m migrator suggest <root>:<task> [--sample N]

"run" - виконати завдання переносу за його schema.yaml.
"suggest" - зробити невелику пробну вибірку з джерела (--sample записів,
за замовчуванням 20) і вивести YAML-заготовку related_catalogs для ВСІХ
__ref_type__, що реально трапились - початкова точка для "auto-suggest
пов'язаних довідників", яку користувач потім звіряє/редагує вручну.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from migrator.cascade import find_related_ref_types
from migrator.config import resolve_schema_path
from migrator.engine import TransferEngine, bridge_client
from migrator.schema import load_schema


def cmd_run(args: argparse.Namespace) -> None:
    schema_path = resolve_schema_path(args.task)
    if not schema_path.exists():
        print(f"Схему не знайдено: {schema_path}", file=sys.stderr)
        sys.exit(1)
    schema = load_schema(schema_path)

    session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = Path(args.log_dir) if args.log_dir else schema_path.parent / "logs" / "engine" / session_stamp

    engine = TransferEngine(schema, session_dir=session_dir)
    result = engine.run(limit=args.limit)

    print(f"\nЗавершено {result.kind}.{result.name}: отримано {result.fetched}, {result.write_summary}")
    if result.cascaded:
        print(f"Каскадовано: {', '.join(result.cascaded)}")


def cmd_suggest(args: argparse.Namespace) -> None:
    schema_path = resolve_schema_path(args.task)
    if not schema_path.exists():
        print(f"Схему не знайдено: {schema_path}", file=sys.stderr)
        sys.exit(1)
    schema = load_schema(schema_path)

    query = schema.select_query(limit=args.sample)
    print(f"Пробна вибірка: {query}")
    rows = bridge_client.query_via_com(schema.source.connection_string, query)
    ref_types = sorted(find_related_ref_types(rows))

    if not ref_types:
        print("Пов'язаних посилань не знайдено у пробній вибірці.")
        return

    print("\n# Заготовка related_catalogs - перевірте detail/depth і додайте у schema.yaml:")
    print("related_catalogs:")
    for ref_type in ref_types:
        print(f"  - ref_type: {ref_type}")
        print("    detail: reference_only")
        print("    depth: 1")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="migrator", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Виконати завдання переносу")
    run_parser.add_argument("task", help="<корінь>:<завдання>, напр. bukovel-legacy:warehouse")
    run_parser.add_argument("--limit", type=int, default=None, help="Обмежити кількість записів (для тесту)")
    run_parser.add_argument("--log-dir", default=None, help="Куди писати engine.log/write_progress.log")
    run_parser.set_defaults(func=cmd_run)

    suggest_parser = sub.add_parser("suggest", help="Запропонувати related_catalogs за пробною вибіркою")
    suggest_parser.add_argument("task", help="<корінь>:<завдання>")
    suggest_parser.add_argument("--sample", type=int, default=20, help="Розмір пробної вибірки (за замовч. 20)")
    suggest_parser.set_defaults(func=cmd_suggest)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
