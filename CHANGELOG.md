# Changelog

*(Ukrainian readers: this changelog is maintained in English only — see [README.uk.md](README.uk.md) for a Ukrainian project overview.)*
*(Українською: цей журнал змін ведеться лише англійською — див. [README.uk.md](README.uk.md) для огляду проєкту українською.)*

## [0.4.0] - 2026-08-11
### Added
- Tabular parts (табличные части) are now transferred end-to-end:
  - `com_query.ps1 -TabularParts <names> -ObjectRef <Kind.Name>` runs one
    extra query per declared tabular part (`SELECT * FROM <ObjectRef>.<TS>`)
    and embeds each part's rows into the owning row, keyed by the part's
    own name.
  - `ObjectModule.bsl`: extracted the shared `ПрисвоитиПоле(...)` helper
    (deserialize + Date() conversion + type-driven null coercion + write,
    one field at a time) and reused it for both regular attributes and
    tabular part columns; `ЗаписатиЕлементи` now detects tabular-part keys
    via object metadata and fully replaces them (clear + re-add).
  - `TransferSchema.tabular_parts` / `tabular_part_names`; `engine.py`
    passes them through to `query_via_com`.
- `ЗаписатиЕлементи` gained an optional `ДополнительныеСвойстваJSON` param -
  a generic `{"Ключ": значення}` bag applied to `Объект.ДополнительныеСвойства`
  before `Записать()`. Replaces the previously hardcoded
  `ПропуститьОбновлениеФлагаКонтроляОперативныхОстатков` literal; this flag
  is now declared per-task via `schema.yaml`'s `destination_write_options`.
- `Bridge1C.write_items(..., additional_properties=...)` and
  `query_via_com(..., tabular_parts=..., object_ref=...)` passthroughs.
### Fixed
- **Enum value bug** (present on both sides, same root cause: an enum
  *value*'s `.Метаданные()` returns its *type*'s metadata, not a
  per-value one, so `.Имя` always returned the type name):
  - `com_query.ps1` (external COM, source-side reads): the global
    `Перечисления` manager marshals to a plain, unindexable array over
    `V83.COMConnector` (confirmed empirically, also true for
    `Справочники`) - worked around by resolving each candidate value's
    canonical form via a query-language lookup (`ЗНАЧЕНИЕ(Перечисление.
    Тип.Имя)` + `ЗначениеВСтрокуВнутр()`), cached per enum type. Also
    handles the "field never explicitly set" case, which stores a
    distinct all-zero internal id that resolves to the type's first
    metadata-defined value.
  - `ObjectModule.bsl`'s `ЗначениеДляJSON` (local session, destination-side
    reads via `ВыполнитьЗапрос`): fixed by linear-scanning
    `Перечисления[Тип].Получить(i)` against metadata-declared value names
    (`ИндексЗначения` turned out not to exist on the enum manager).
### Verified
- `python -m migrator run bukovel-legacy:warehouse --limit 5`: enum fields
  (`ТипСклада`, plus 8 others) now resolve to real value names on both the
  source-read and destination-read paths; a tabular part
  (`ДоступныеУслуги`) with 13 rows transferred and confirmed present on
  the DEV side; cascades to `ВидыЦен`/`СтруктураПредприятия` still work.

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
