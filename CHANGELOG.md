# Changelog

*(Ukrainian readers: this changelog is maintained in English only — see [README.uk.md](README.uk.md) for a Ukrainian project overview.)*
*(Українською: цей журнал змін ведеться лише англійською — див. [README.uk.md](README.uk.md) для огляду проєкту українською.)*

## [1.3.0] - 2026-08-12
### Fixed
- `ЗаписатиЕлементи` (`BridgeTool/BridgeTool/Ext/ObjectModule.bsl`) no longer
  fails a whole record when a predefined item is declared in the
  destination's metadata but not yet materialized as data (destination
  catalog/chart-of-characteristic-types set to `predefinedDataUpdate:
  DontAutoUpdate` - the platform does not auto-create these, unlike mode
  "Авто"). `ПредопределенноеЗначение()` throws "Предопределенный элемент
  отсутствует в данных" in that case; the fallback now creates a fresh
  element/document and assigns `ИмяПредопределенныхДанных` before the first
  write - the standard 1C technique for binding a new object to an
  already-declared predefined slot without a Configurator/Designer pass.
  Found running the new `bukovel-legacy:services` task (Номенклатура 14/16,
  ВидыНоменклатуры 69/71 on the first attempt; 16/16 and 71/71 after the fix).
### Changed
- BridgeTool build bumped to 1.3.0 (`BridgeTool.xml`, `ВерсіяBridgeTool()`)
  via `stamp_version.py`, rebuilt with the `epf-build` skill against
  `EDT_BASE\SKI`, and validated with `epf-validate` (0 errors).

## [1.2.0] - 2026-08-11
### Added
- Optional `filter` field on `schema.yaml`: a raw 1C query-language `ГДЕ`
  condition (no leading keyword), appended verbatim by
  `TransferSchema.select_query()` for both `select_mode: all` and
  `explicit`. Lets a task read a known, named subset of a large catalog
  (e.g. a handful of predefined items already declared in the destination
  configuration) instead of a full-catalog mirror - motivated by the
  "Номенклатура" services-list task, where the destination only needed 16
  specific predefined rental-service items out of the whole nomenclature
  catalog. Deliberately unparameterized, same rationale as the existing
  `related_catalogs` simplification in `cascade.py`: the condition is
  written once, by a human, against values already fixed at schema-authoring
  time, so plain string interpolation is sufficient. Omit (default `""`) to
  keep existing tasks (e.g. `warehouse`) reading the whole object, unchanged.

## [1.1.0] - 2026-08-11
### Fixed
- `ЗаписатиЕлементи` now sets the **standard** 1C `Объект.ОбменДанными.Загрузка = Истина`
  flag before writing every object - not a bespoke bypass, but the
  platform-standard signal that "this write is a data import," which
  well-written business modules already check at the top of
  `ПередЗаписью`/`ОбработкаПроверкиЗаполнения` to skip interactive-entry-
  only validation. Found by dumping the destination's own
  `Catalogs/КассыККМ/Ext/ObjectModule.bsl` and reading its actual
  `ПередЗаписью` handler rather than guessing.
### Verified
- Full acceptance re-run: **Склады 131/131, all 8/8 cascaded catalogs
  100%** - including `Справочник.КассыККМ` (159/159, previously 0/159
  - see [0.8.0] for the original diagnosis). The "Склади" transfer is
  now complete with no known remaining gaps beyond the previously
  documented, expected serialization/group-record differences.

## [1.0.0] - 2026-08-11
### Summary
First complete release. Starting from a hand-built, one-off pilot script
that successfully moved the "Склады" catalog once, this project generalized
that experience into a reusable, schema-driven, documented tool:
- A declarative `schema.yaml` format covering source/destination shape,
  field mapping, related-catalog cascading with configurable depth/detail,
  tabular parts, pipeline hooks, and destination write-time bypass flags.
- `migrator/engine.py`, running any task against that format over a single
  shared BridgeTool session.
- A local GUI for settings and process control, needing no terminal.
- Bilingual (EN/UK) documentation and three lessons-learned Claude Code
  skills contributed back to the shared `cc-1c-skills` pack.
- An acceptance test that not only reproduced the original pilot's result
  but exceeded it: the original pilot moved one catalog; this run moves
  the same catalog **and cascades to 8 related catalogs**, with the one
  incomplete cascade traced to a genuine source data gap rather than a
  code defect - see [0.8.0] below for the full breakdown.
No BridgeTool/Python changes in this step - version bump and status/docs
update only, marking the project's stated goal (`1.0.0`) as reached.

## [0.8.0] - 2026-08-11
### Acceptance test (the project's core deliverable)
`python -m migrator run bukovel-legacy:warehouse` - full, unlimited run:
- **Справочник.Склады: 131/131** written, UUIDs preserved, verified by a
  full field-by-field source/destination comparison plus a tabular-part
  row-count spot check (42/45 sampled matched exactly; the 3 that didn't
  are explained below).
- Cascaded to 8 related catalogs (`suggest`'s full list minus the
  self-reference): **7/8 100%** (ВидыЦен 25/25, СтруктураПредприятия
  126/126, БизнесРегионы 0/0, Календари 1/1, КлассификаторКОАТУУ 0/0,
  СпособыОбеспеченияПотребностей 0/0, ФизическиеЛица 361/361).
  Справочник.КассыККМ (159 rows) is a **known, documented, non-code
  limitation**: every source row has an empty composite-type "Владелец"
  field, and the destination's own business logic requires a
  non-blank derived "Организация" on write - a source data-completeness
  gap, not a transfer defect (see `schema.yaml`'s `related_catalogs` entry).
- Remaining field-level differences are the same categories the original
  hand-built pilot already found and accepted: group-record field resets,
  and `Формат()`'s "empty date" (0001-01-01) rendering as `""` in BSL
  vs. a literal digit string from COM/.NET `.ToString()` - both sides
  store the identical date value, confirmed by direct testing.
- `fetch_catalog.py`/`write_catalog.py` retired - moved to
  `_retired/` (not deleted; that task root isn't version-controlled) with
  a note pointing at the new engine.
### Fixed (found only under a full, unlimited, multi-catalog run)
- `com_query.ps1`: a query returning **exactly one row** silently
  corrupted on output - `$rows | ConvertTo-Json` (piping a 1-element
  `ArrayList`) unwraps to a bare JSON object instead of a 1-element array,
  a well-known PowerShell gotcha. The destination then iterated the row's
  *fields* as if they were rows, producing `Invalid parameter value` on
  `УникальныйИдентификатор("")`. Fixed with `ConvertTo-Json -InputObject`
  (bypasses pipeline enumeration) instead of piping.
- `com_query.ps1`: a query result with **exactly one column** marshals
  its `Колонки` property as a scalar (the column object itself), not a
  collection - `.Количество()` on it threw `Unknown name`. Fixed with a
  try/catch fallback that treats the scalar as the single column.
- `com_query.ps1`: **composite-type columns** (e.g. `Владелец`, the owner
  of a subordinate catalog, valid as several different reference types)
  throw `Member not found` via `GetProperty` COM binding - fixed with a
  try/catch fallback to `InvokeMethod`, which retrieves the same value
  correctly.
- `migrator/engine.py`: cascaded catalog writes never passed a
  `progress_log`, so `ЗаписатиЕлементи` silently wrote no per-item log at
  all for cascades - the КассыККМ failures above were invisible until this
  was fixed (each cascade now gets its own `cascade_<name>.log`).

## [0.7.0] - 2026-08-11
### Added
- Three reusable Claude Code skills, distilled from this project's hardest
  debugging sessions, added to the shared `cc-1c-skills` pack (a separate,
  third-party-owned repo at `D:\Bukovel\Skills\cc-1c-skills\` - **not**
  committed/pushed there by this step; that repo's git history is not ours
  to touch without separate confirmation):
  - `classic-xml-bsl-gotchas` - module-level `Перем` needing a compilation
    directive, `ЗапускПараметр()` unavailable in safe mode, hand-edited
    `Form.xml` `<ChildItems>` silently dropped, `-listFile` required for
    partial `/DumpConfigToFiles`, and the enum-value `.Метаданные()` bug
    (both the local-BSL and the external-COM manifestations, and their
    respective fixes) found in Phase 3.
  - `1c-thick-client-hang-diagnosis` - an escalation checklist for
    "1cv8.exe started but isn't responding" (stale compiled artifact →
    is the process even up → session/lock conflicts → ready-signal timing
    → tech-log as a last resort).
  - `1cv8-cmdline-quoting` - before/after Python `subprocess`/PowerShell
    snippets for `1cv8.exe`'s `/Flag"value"` argument style, and the
    failure signature when `list2cmdline`/PowerShell's tokenizer mangles it.
### Note
- No BridgeTool/COM changes this step - skills are documentation, not
  code, so no E2E transfer test applies here.

## [0.6.0] - 2026-08-11
### Added
- Bilingual documentation under `docs/` (EN primary + UK translation, same
  top-of-file language-switcher link pattern as the READMEs):
  - `architecture.md`/`.uk.md` - why two interfaces (COM for source reads,
    BridgeTool for destination writes), the bootstrap-file exchange
    protocol, the two universal BSL primitives, and the engine pipeline.
  - `schema-format-reference.md`/`.uk.md` - every `schema.yaml` field
    (`source`, `destination`, `select_mode`, `field_mappings`,
    `related_catalogs`, `tabular_parts`, `destination_write_options`,
    `hooks`), with the real `bukovel-legacy:warehouse` task as reference.
  - `gui.md`/`.uk.md` - the local web dashboard's pages and what it
    deliberately doesn't do (no auth, no multi-user queue).
- README.md/README.uk.md now link to the new docs and list the CLI's three
  subcommands (`run`/`suggest`/`gui`).
### Note
- No BridgeTool/COM changes this step - docs only, so no E2E transfer test
  applies here (see CHANGELOG for the last verified run in [0.5.0]).

## [0.5.0] - 2026-08-11
### Added
- `gui/` - a local FastAPI web app (`python -m migrator gui [--host] [--port]`),
  filesystem-only (starts transfer runs as a separate `python -m migrator run`
  subprocess; never touches 1C/COM/BridgeTool directly itself):
  - **Dashboard** (`/`) - task roots from `migrator.config.yaml`, tasks found
    in each (folders with a `schema.yaml`), and each task's last run status.
  - **Schema editor** (`/schema/<root>/<task>`) - raw YAML textarea, save
    (validated against a scratch copy before overwriting), and an
    AJAX "validate without saving" button; a form to trigger a run
    (optionally `--limit`) directly from the page.
  - **Live monitor** (`/monitor/<root>/<task>`) - session picker, live
    running/idle badge, and the three logs a run produces
    (`engine.log`, `write_progress.log`, `bridge_startup.log` +
    parsed BridgeTool version), polled every 2s while running.
  - **Settings** (`/settings`) - view/edit `migrator.config.yaml`'s
    task-root registry directly.
- `requirements.txt`: `python-multipart` (required by FastAPI for HTML
  form parsing).
### Verified
- Full round trip through the GUI itself: dashboard → schema editor
  (validate) → triggered a real 3-row transfer + 2 cascades via the
  "Run now" form → monitor page auto-updated from "running" to "idle"
  with all three logs populated and the correct BridgeTool version shown.

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
