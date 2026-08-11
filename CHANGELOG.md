# Changelog

*(Ukrainian readers: this changelog is maintained in English only — see [README.uk.md](README.uk.md) for a Ukrainian project overview.)*
*(Українською: цей журнал змін ведеться лише англійською — див. [README.uk.md](README.uk.md) для огляду проєкту українською.)*

## [0.3.0] - 2026-08-11
### Added
- `migrator/` Python package: the schema-driven transfer engine.
  - `schema.py` - `TransferSchema` YAML format: `source`/`destination`
    connection info, `select_mode` (`all` vs `explicit`), `field_mappings`
    (stable id + source/destination field name + human description - the
    "Schema 1 <-> Schema 2" transport mapping), `related_catalogs` (cascade
    rules: `ref_type`/`detail`/`depth`), `hooks`.
  - `hooks.py` - pipeline extension registry (`before_read`, `before_write`,
    `after_each_item`, `after_write`); built-ins `log_query`,
    `require_fields`, `log_progress`, `print_summary`.
  - `cascade.py` - `plan_cascade()`: detects which configured
    `related_catalogs` rules actually match `__ref_type__` values present
    in a fetched batch.
  - `engine.py` - `TransferEngine`: reads via COM, writes via BridgeTool,
    runs hooks at each stage, recursively cascades related catalogs
    (`reference_only` transfers the whole related catalog once;
    `full` recurses the engine one level deeper), single shared
    BridgeTool session across an entire cascade tree.
  - `config.py` - resolves `<root>:<task>` against `migrator.config.yaml`.
  - `cli.py` / `__main__.py` - `python -m migrator run <root>:<task>
    [--limit N]` and `python -m migrator suggest <root>:<task>` (samples
    the source and prints a `related_catalogs` starting point from the
    `__ref_type__`s actually observed - the "auto-suggest related catalogs"
    starting point, refined manually from there).
- `D:\Bukovel\Transfer\warehouse\schema.yaml` - the "Склады" task's first
  schema-driven definition (lives outside this repo per the task-root
  design; not tracked here).
### Changed
- `BridgeTool/migrator.py` renamed to `BridgeTool/bridge_client.py` - it
  collided by name with the new top-level `migrator` package.
### Verified
- `python -m migrator run bukovel-legacy:warehouse --limit 5`: real COM
  read (5 rows) + BridgeTool write, plus both configured `related_catalogs`
  cascaded automatically (`Справочник.ВидыЦен` 25/25,
  `Справочник.СтруктураПредприятия` 126/126) over a single shared
  BridgeTool session - no restart between the main write and the cascades.

## [0.2.0] - 2026-08-11
### Added
- Version stamping: `BridgeTool/scripts/stamp_version.py` writes the repo's
  `VERSION` into `BridgeTool.xml`'s `<Comment>` and a new BSL
  `ВерсіяBridgeTool()` function in `ObjectModule.bsl`.
- `Module.bsl` logs the BridgeTool version as the first `bridge_startup.log`
  line and appends `version=X` to `ready.txt`'s content.
- `migrator.py` reads `VERSION` at import time, logs it at session start, and
  warns (does not fail) if the running `BridgeTool.epf`'s reported version
  doesn't match.
- `migrator/_version.py`: single source of truth for the Python side's
  version string.
### Fixed
- `migrator.py`: reconfigured stdout/stderr to UTF-8 (`errors="replace"`) -
  Cyrillic status prints were crashing with `UnicodeEncodeError` on a
  default-codepage Windows console.
- Verified: live COM-read (TEST_SKI_HIRE) + BridgeTool-write (DEV) round
  trip against the rebuilt `BridgeTool.epf` (v0.2.0).

## [0.1.0] - 2026-08-11
### Added
- Initial repo scaffold: `VERSION`, `.gitignore`/`.gitattributes`, `pyproject.toml`,
  `requirements.txt`, `migrator.config.example.yaml` / `migrator.config.yaml`
  (task-root registry), `LICENSE`, `TransferDATA/`.
- `BridgeTool/` folded in from the standalone pilot (`D:\Bukovel\BAF_TOOLS\BridgeTool\`):
  `.epf`, BSL source tree, `com_query.ps1`, `migrator.py`. Hardcoded bootstrap
  path and `TOOL_DIR` updated for the new location; `migrator.py`'s `TOOL_DIR`
  now self-locates via `Path(__file__).resolve().parent` instead of a literal
  path, to prevent a repeat of the stale-path-after-move bug found during the
  pilot session.
- Verified: live "1+1" round trip against `BridgeTool.epf` from the new
  `Migrator/BridgeTool/` location.
