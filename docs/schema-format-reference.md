**[English](schema-format-reference.md)** · [Українська](schema-format-reference.uk.md)

# `schema.yaml` reference

One YAML file per transfer task, loaded by `migrator.schema.load_schema()`.
A task is addressed as `<root>:<task>` (see `migrator.config.yaml`) and its
schema resolves to `<root path>/<task>/schema.yaml`.

Every real, working example referenced below is
`D:\Bukovel\Transfer\warehouse\schema.yaml` (the `bukovel-legacy:warehouse`
task) - it is not tracked in this repo (that task root is intentionally
external), but the same fields apply to any task registered under
`TransferDATA/` inside this repo.

## Top-level fields

```yaml
schema_version: 1
task: warehouse
kind: Справочник        # "Справочник" | "Документ"
name: Склады
description: "Free text - what this task moves and why."
```

## `source` - where rows are read from

```yaml
source:
  connection: com        # only "com" is currently supported
  connection_string: 'Srvr="REN-SER-DB1";Ref="TEST_SKI_HIRE";'
```

Reads always go through `com_query.ps1` (a separate 32-bit PowerShell
process) - see [architecture.md](architecture.md).

## `destination` - where rows are written to

```yaml
destination:
  connection: bridge     # only "bridge" is currently supported
  platform_exe: 'D:\Programs\BAF\8.3.23.2299\bin\1cv8.exe'
  connect_args: ["/F", 'D:\Bukovel\EDT_BASE\SKI']   # or ["/S", "server\\base"]
```

`platform_exe`/`connect_args` are optional - if omitted, the engine falls
back to `bridge_client.DEV` (the default destination configured for the
pilot deployment).

## `select_mode` - which fields are read

- `all` (default, recommended) - `SELECT * FROM <Kind>.<Name>`. Safe: every
  field the source has is read, nothing is silently dropped by an
  incomplete `field_mappings` list.
- `explicit` - builds an explicit column list from `field_mappings` (plus
  the always-required system fields: `Ссылка`, and for catalogs
  `ЭтоГруппа`/`Родитель`/`Предопределенный`/`ИмяПредопределенныхДанных`).
  Use this only when you deliberately want to restrict what's read.

## `field_mappings` - the "Schema 1 ↔ Schema 2" transport mapping

This is the field-level mapping the user asked for explicitly: a stable
internal `id`, the field's name on the source side, its name on the
destination side (usually identical - both sides are typically the same
underlying BAF configuration, just different environments), and a
human-readable description.

```yaml
field_mappings:
  - id: warehouse_type
    source_field: ТипСклада
    destination_field: ТипСклада
    description: "Warehouse kind - a ТипыСкладов enum value."
  - id: price_kind_retail
    source_field: РозничныйВидЦены
    destination_field: РозничныйВидЦены
    description: "Retail price kind - a reference to Справочник.ВидыЦен."
```

You do **not** need to list every field here - only ones worth documenting,
renaming, or that a future per-field extension might hook into. Everything
else transfers 1:1 as long as `select_mode: all` (the default).

## `related_catalogs` - cascading to dependency catalogs

Each rule fires only if its `ref_type` actually appears (as a `__ref_type__`
wrapper) somewhere in the fetched rows - unused rules are simply skipped,
cheaply.

```yaml
related_catalogs:
  - ref_type: Справочник.ВидыЦен
    detail: reference_only   # "reference_only" | "full"
    depth: 1
    description: "Price kinds referenced by warehouses."
```

- `reference_only` - transfers the **entire** related catalog once (no
  further cascading of *its* related catalogs). Deliberately simple: these
  tend to be small lookup tables, and filtering to only the referenced UUIDs
  would need parameterized COM queries for no real benefit at this scale.
- `full` - recursively runs the whole engine one level deeper for that
  catalog (itself subject to `related_catalogs`/depth again).
- `depth` bounds how many `full` levels are allowed before a rule is
  skipped (logged, not an error).
- A rule that points back at the task's own catalog (self-reference) is
  automatically a no-op - the current catalog is marked visited before
  cascade rules are evaluated.

Use `python -m migrator suggest <root>:<task> [--sample N]` to get a
starting list of every `__ref_type__` actually observed in a sample -
review and copy the ones you want into `related_catalogs`.

## `tabular_parts` - табличные части

```yaml
tabular_parts:
  - name: ДоступныеУслуги
    description: "Services (Номенклатура) available at this warehouse."
```

Each declared name is fetched as its own query
(`SELECT * FROM <Kind>.<Name>.<TabularPartName>`) and merged into the owning
row before it's written. On write, `ЗаписатиЕлементи` detects the key is a
tabular part (via object metadata, not by name convention) and fully
replaces its rows (clear + re-add) - the source is the single source of
truth for a tabular part's contents.

## `destination_write_options` - write-time bypass flags

```yaml
destination_write_options:
  additional_properties:
    ПропуститьОбновлениеФлагаКонтроляОперативныхОстатков: true
```

Becomes `Объект.ДополнительныеСвойства` entries set right before
`Записать()` on the destination side - the generic mechanism for "skip this
expensive/business-specific recompute during import" flags a target base's
own code might support. Which flags exist and what they do is destination
business logic, not something Migrator hardcodes.

## `hooks` - pipeline extension points

```yaml
hooks:
  - stage: before_read     # before_read | before_write | after_each_item | after_write
    name: log_query
  - stage: before_write
    name: require_fields
    args:
      fields: [Наименование]
  - stage: after_write
    name: print_summary
```

`name` must be registered in `migrator/hooks.py` (`@hooks.register("...")`).
Built-ins: `log_query` (before_read), `require_fields` (before_write - warns,
does not block, on empty required fields), `log_progress` (after_each_item),
`print_summary` (after_write). Declaring any `after_each_item` hook switches
the engine from one batch write to one write-per-row (needed for genuine
per-item granularity - slower, since each row is its own round trip to
BridgeTool).
