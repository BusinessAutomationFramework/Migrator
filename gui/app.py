"""
Локальний GUI Migrator (FastAPI) - панель для налаштувань і контролю за
процесом переносу. Говорить ЛИШЕ з файловою системою: читає/пише
schema.yaml та migrator.config.yaml, запускає перенос як ОКРЕМИЙ процес
(`python -m migrator run ...`) і читає його логи - сам НІКОЛИ не
звертається до 1С/COM/BridgeTool напряму (це відповідальність migrator.engine).

Запуск: python -m migrator gui [--host 0.0.0.0] [--port 8765]
"""

from __future__ import annotations

import re
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from migrator.config import CONFIG_FILE, EXAMPLE_CONFIG_FILE, REPO_ROOT, load_config
from migrator.schema import load_schema

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Migrator")

# {"root:task": subprocess.Popen} - лише для статусу "виконується/завершено"
# на сторінці монітора. Локальний однокористувацький інструмент - process
# state в пам'яті процесу GUI цілком достатньо, без окремої БД/черги.
RUNNING: dict[str, subprocess.Popen] = {}

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _safe(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Неприпустима назва: {name!r}")
    return name


def _task_dir(root: str, task: str, config: dict) -> Path:
    _safe(root)
    _safe(task)
    roots = config.get("task_roots", {})
    if root not in roots:
        raise KeyError(f"Корінь '{root}' не зареєстровано")
    root_path = Path(roots[root]["path"])
    if not root_path.is_absolute():
        root_path = (REPO_ROOT / root_path).resolve()
    return root_path / task


def _list_tasks(root: str, root_path: Path) -> list[dict]:
    tasks = []
    if not root_path.exists():
        return tasks
    for entry in sorted(root_path.iterdir()):
        schema_path = entry / "schema.yaml"
        if entry.is_dir() and schema_path.exists():
            tasks.append({
                "root": root,
                "task": entry.name,
                "last_run": _latest_run_summary(entry),
            })
    return tasks


def _run_sessions(task_dir: Path) -> list[str]:
    engine_logs = task_dir / "logs" / "engine"
    if not engine_logs.exists():
        return []
    return sorted((p.name for p in engine_logs.iterdir() if p.is_dir()), reverse=True)


def _latest_run_summary(task_dir: Path) -> dict | None:
    sessions = _run_sessions(task_dir)
    if not sessions:
        return None
    session = sessions[0]
    log_file = task_dir / "logs" / "engine" / session / "engine.log"
    last_line = ""
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        last_line = lines[-1] if lines else ""
    return {"session": session, "last_line": last_line}


def _bridge_version(task_dir: Path, session: str) -> str | None:
    log_file = task_dir / "logs" / "engine" / session / "bridge_startup.log"
    if not log_file.exists():
        return None
    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if "Версія BridgeTool:" in line:
            return line.split("Версія BridgeTool:", 1)[1].strip()
    return None


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    config = load_config()
    roots = config.get("task_roots", {})
    root_sections = []
    for root_name in roots:
        root_path = Path(roots[root_name]["path"])
        if not root_path.is_absolute():
            root_path = (REPO_ROOT / root_path).resolve()
        root_sections.append({
            "name": root_name,
            "path": str(root_path),
            "tasks": _list_tasks(root_name, root_path),
        })
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context={"root_sections": root_sections}
    )


@app.get("/schema/{root}/{task}", response_class=HTMLResponse)
def schema_editor(request: Request, root: str, task: str):
    config = load_config()
    task_dir = _task_dir(root, task, config)
    schema_path = task_dir / "schema.yaml"
    content = schema_path.read_text(encoding="utf-8") if schema_path.exists() else ""
    error = None
    if content:
        try:
            load_schema(schema_path)
        except Exception as exc:
            error = str(exc)
    return templates.TemplateResponse(
        request=request, name="schema_editor.html",
        context={"root": root, "task": task, "content": content, "error": error, "saved": False},
    )


@app.post("/schema/{root}/{task}", response_class=HTMLResponse)
def schema_save(request: Request, root: str, task: str, content: str = Form(...)):
    config = load_config()
    task_dir = _task_dir(root, task, config)
    schema_path = task_dir / "schema.yaml"

    error = None
    try:
        # Валідація ПЕРЕД записом на диск - тимчасовий файл, щоб не
        # затерти робочу схему явно некоректним YAML/структурою.
        scratch = schema_path.with_suffix(".yaml.tmp")
        scratch.write_text(content, encoding="utf-8")
        load_schema(scratch)
        scratch.unlink()
    except Exception as exc:
        error = str(exc)

    saved = False
    if error is None:
        task_dir.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(content, encoding="utf-8")
        saved = True

    return templates.TemplateResponse(
        request=request, name="schema_editor.html",
        context={"root": root, "task": task, "content": content, "error": error, "saved": saved},
    )


@app.post("/schema/{root}/{task}/validate")
def schema_validate(root: str, task: str, content: str = Form(...)):
    config = load_config()
    task_dir = _task_dir(root, task, config)
    scratch = task_dir / "schema.yaml.tmp"
    try:
        task_dir.mkdir(parents=True, exist_ok=True)
        scratch.write_text(content, encoding="utf-8")
        load_schema(scratch)
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)})
    finally:
        if scratch.exists():
            scratch.unlink()


@app.post("/run/{root}/{task}")
def trigger_run(root: str, task: str, limit: str = Form("")):
    config = load_config()
    task_dir = _task_dir(root, task, config)
    session = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = task_dir / "logs" / "engine" / session

    cmd = [sys.executable, "-m", "migrator", "run", f"{root}:{task}", "--log-dir", str(log_dir)]
    if limit.strip():
        cmd += ["--limit", limit.strip()]

    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_file = open(log_dir / "gui_stdout.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd, cwd=str(REPO_ROOT), stdout=stdout_file, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    RUNNING[f"{root}:{task}"] = proc

    return RedirectResponse(url=f"/monitor/{root}/{task}?session={session}", status_code=303)


@app.get("/monitor/{root}/{task}", response_class=HTMLResponse)
def monitor(request: Request, root: str, task: str, session: str | None = None):
    config = load_config()
    task_dir = _task_dir(root, task, config)
    sessions = _run_sessions(task_dir)
    active_session = session or (sessions[0] if sessions else None)

    proc = RUNNING.get(f"{root}:{task}")
    running = proc is not None and proc.poll() is None

    return templates.TemplateResponse(
        request=request, name="monitor.html",
        context={
            "root": root, "task": task,
            "sessions": sessions, "active_session": active_session, "running": running,
        },
    )


@app.get("/monitor/{root}/{task}/tail")
def monitor_tail(root: str, task: str, session: str):
    config = load_config()
    task_dir = _task_dir(root, task, config)
    session_dir = task_dir / "logs" / "engine" / _safe(session)

    def _read(name: str) -> str:
        f = session_dir / name
        return f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""

    proc = RUNNING.get(f"{root}:{task}")
    running = proc is not None and proc.poll() is None

    return JSONResponse({
        "running": running,
        "engine_log": _read("engine.log"),
        "write_progress_log": _read("write_progress.log"),
        "bridge_startup_log": _read("bridge_startup.log"),
        "bridge_version": _bridge_version(task_dir, session),
    })


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    config = load_config()
    cfg_path = CONFIG_FILE if CONFIG_FILE.exists() else EXAMPLE_CONFIG_FILE
    content = cfg_path.read_text(encoding="utf-8")
    return templates.TemplateResponse(
        request=request, name="settings.html",
        context={"content": content, "roots": config.get("task_roots", {}), "saved": False, "error": None},
    )


@app.post("/settings", response_class=HTMLResponse)
def settings_save(request: Request, content: str = Form(...)):
    error = None
    try:
        parsed = yaml.safe_load(content) or {}
        if "task_roots" not in parsed:
            raise ValueError("Конфіг має містити ключ 'task_roots'")
    except Exception as exc:
        error = str(exc)

    saved = False
    if error is None:
        CONFIG_FILE.write_text(content, encoding="utf-8")
        saved = True

    config = load_config()
    return templates.TemplateResponse(
        request=request, name="settings.html",
        context={"content": content, "roots": config.get("task_roots", {}), "saved": saved, "error": error},
    )
