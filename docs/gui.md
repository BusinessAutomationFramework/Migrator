**[English](gui.md)** · [Українська](gui.uk.md)

# GUI

A local, filesystem-only web dashboard for settings and process control.
It never talks to 1C/COM/BridgeTool itself - it starts transfer runs as a
separate `python -m migrator run ...` subprocess and reads the log files
that process writes.

## Starting it

```bash
python -m migrator gui                    # http://127.0.0.1:8765
python -m migrator gui --host 0.0.0.0 --port 9000
```

Requires the `requirements.txt` dependencies installed
(`pip install -r requirements.txt`), including `python-multipart` (needed
for FastAPI's HTML form handling).

## Pages

### Dashboard (`/`)

Lists every task root from `migrator.config.yaml`, and every task found in
each (a folder containing a `schema.yaml`), with its last run's timestamp
and final log line.

### Schema editor (`/schema/<root>/<task>`)

A raw YAML textarea over the task's `schema.yaml`:

- **Save** - writes to a scratch `.yaml.tmp` file first, validates it via
  `migrator.schema.load_schema()`, and only then overwrites the real file
  (so a broken edit never clobbers a working schema).
- **Validate without saving** - the same validation, over AJAX, without
  touching the file at all.
- A small form to trigger a run immediately, optionally with `--limit N`
  for a quick smoke test.

### Live monitor (`/monitor/<root>/<task>`)

Session picker (every past run, newest first) plus the three logs a run
produces, auto-refreshed every 2 seconds while the process is still running:

- `engine.log` - the orchestration log (fetch/write/cascade steps),
  written by the Python side.
- `write_progress.log` - per-item write progress, written by BridgeTool
  itself (BSL).
- `bridge_startup.log` - BridgeTool's own startup lifecycle log, including
  the version banner it reports on open.

### Settings (`/settings`)

Views and edits `migrator.config.yaml`'s task-root registry directly - the
same file `migrator.config.resolve_task_dir()` reads.

## What it deliberately doesn't do

No authentication, no multi-user process queue, no database - this is a
local, single-operator tool. Process state (which task is "running") lives
in the GUI process's own memory; restarting the GUI loses that in-memory
status (the log files themselves are unaffected).
