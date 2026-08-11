"""
Реєстр коренів завдань (task roots) - migrator.config.yaml. Кожне завдання
переносу адресується як "<root_name>:<task_id>" і резолвиться у
"<task_roots.<root_name>.path>/<task_id>/schema.yaml". Дозволяє завданню
жити ЗА МЕЖАМИ цього репозиторію (наприклад, у приватному git) без
переміщення файлів - лише реєстрація шляху тут.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / "migrator.config.yaml"
EXAMPLE_CONFIG_FILE = REPO_ROOT / "migrator.config.example.yaml"


def load_config(path: str | Path | None = None) -> dict:
    if path is not None:
        cfg_path = Path(path)
    elif CONFIG_FILE.exists():
        cfg_path = CONFIG_FILE
    else:
        cfg_path = EXAMPLE_CONFIG_FILE
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def resolve_task_dir(task_ref: str, config: dict | None = None) -> Path:
    """
    "bukovel-legacy:warehouse" -> Path("D:/Bukovel/Transfer/warehouse")
    "warehouse" (без коду кореня) -> корінь default_task_root.
    """
    config = config if config is not None else load_config()
    if ":" in task_ref:
        root_name, task_id = task_ref.split(":", 1)
    else:
        root_name, task_id = config.get("default_task_root", "default"), task_ref

    roots = config.get("task_roots", {})
    if root_name not in roots:
        raise KeyError(
            f"Корінь завдань '{root_name}' не зареєстровано у {CONFIG_FILE.name} "
            f"(доступні: {', '.join(roots) or '(жодного)'})"
        )
    root_path = Path(roots[root_name]["path"])
    if not root_path.is_absolute():
        root_path = (REPO_ROOT / root_path).resolve()
    return root_path / task_id


def resolve_schema_path(task_ref: str, config: dict | None = None) -> Path:
    return resolve_task_dir(task_ref, config) / "schema.yaml"
