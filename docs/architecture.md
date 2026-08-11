**[English](architecture.md)** · [Українська](architecture.uk.md)

# Architecture

## Why two interfaces

Migrator moves catalogs/documents between two 1C:Enterprise infobases: a
**source** (in the pilot deployment, a server-mode base reachable only over
the network) and a **destination** (a local file-mode base). Two different
interfaces are used deliberately:

- **COM** (`BridgeTool/com_query.ps1`) reads from the source. It runs as a
  separate 32-bit PowerShell process (`V83.COMConnector` is only registered
  32-bit) and never writes anything - read-only, by construction.
- **BridgeTool** (`BridgeTool/BridgeTool.epf`) writes to the destination. It
  is a classic External Data Processor that opens the destination base as a
  normal 1C client and stays running, polling a small exchange folder for
  requests. **BridgeTool never makes an outbound connection anywhere** - it
  only ever talks to its own (destination) base.

This split exists because a single External Data Processor cannot safely be
handed a live connection string to an arbitrary remote base (safe-mode
restrictions, credential exposure, and no clean way to guarantee it never
touches anything else). Keeping BridgeTool destination-only, and doing all
source reads from a completely separate process, makes the "what can this
component reach" question trivial to answer.

```
   TEST base (server)                      DEV base (file-mode)
        |                                         |
        |  COM (read-only)                         |  BridgeTool.epf (read/write)
        v                                         v
  com_query.ps1  <---- orchestrated by ---->  bridge_client.Bridge1C
        (32-bit PowerShell)                    (persistent 1cv8.exe session)
                          \                    /
                           \                  /
                          migrator.engine.TransferEngine
                                    ^
                                    |
                          migrator.schema.TransferSchema
                              (schema.yaml per task)
```

## The exchange protocol (Python ↔ BridgeTool)

`ЗапускПараметр()` is unavailable to External Data Processors under 1C's
safe execution mode, so command-line arguments cannot reach BridgeTool at
startup. Instead:

1. `Bridge1C.start()` (`BridgeTool/bridge_client.py`) writes a small
   bootstrap text file (`BridgeTool/_launch_config.txt`, one fixed path) with
   two lines: the exchange folder, and (optionally) the folder BridgeTool
   should log its own startup lifecycle to.
2. It then launches `1cv8.exe ENTERPRISE ... /Execute"BridgeTool.epf"` as one
   single command-line string (not an argv list - `list2cmdline` and
   PowerShell's own tokenizer both mangle embedded quotes like `/F"path"`
   otherwise).
3. BridgeTool's form (`Forms/Форма/Ext/Form/Module.bsl`) reads that bootstrap
   file in `ПриОткрытии`, writes `ready.txt` into the exchange folder the
   moment it's genuinely ready to accept requests, and starts a 1-second
   polling loop (`ПодключитьОбработчикОжидания`).
4. Each request is a `request.json` file (`{"expression": "..."}` - any BSL
   expression, evaluated via `Вычислить()`); BridgeTool deletes it, evaluates
   it through `ОбробитиТекстКоманди` in `Ext/ObjectModule.bsl`, and writes
   `request.json.result.json`.
5. `stop.txt` signals a graceful shutdown (`ЗавершитьРаботуСистемы`) instead
   of killing the process, so the file-mode base releases its locks cleanly.

One BridgeTool session serves many requests - it is *not* restarted per
call (a cold start is ~20s). `TransferEngine` keeps one session open across
an entire cascade tree (a main catalog plus everything it cascades into).

## Universal primitives, not business logic

`ObjectModule.bsl` deliberately exposes only two generic operations, both
usable against **any** catalog or document by name:

- `ВыполнитьЗапрос(ТекстЗапроса)` - run an arbitrary 1C query in the local
  (destination) base, return rows as JSON.
- `ЗаписатиЕлементи(ВидОбъекта, ИмяОбъекта, JSONРядки, ...)` - upsert rows
  (by UUID) into a catalog/document. Handles group-vs-item creation order,
  predefined-item lookup, per-field type coercion, tabular parts, and an
  `additional_properties` bypass bag - see
  [schema-format-reference.md](schema-format-reference.md) for how a task
  schema drives each of these.

*Which* catalogs to move, in what order, with what field mapping - none of
that lives in BSL. It's schema-declared in Python (`migrator/schema.py`,
`migrator/engine.py`) so the two universal primitives never need to change
when a new transfer task is added.

## The engine pipeline

`migrator.engine.TransferEngine.run()`, given a `TransferSchema`:

1. Builds a `SELECT` (`TransferSchema.select_query()` - either `SELECT *` or
   an explicit column list built from `field_mappings`).
2. Runs `before_read` hooks, reads via COM (optionally fetching declared
   `tabular_parts` as extra queries, merged into each row).
3. Runs `before_write` hooks, writes via BridgeTool (`ЗаписатиЕлементи`,
   passing through `destination_write_options.additional_properties`).
4. Runs `after_write` hooks.
5. Looks at which `related_catalogs` rules actually matched a `__ref_type__`
   present in the fetched rows (`migrator.cascade.plan_cascade`), and
   recursively transfers each one over the *same* BridgeTool session -
   `reference_only` transfers the whole related catalog once (these tend to
   be small lookup tables); `full` recurses the engine one level deeper,
   itself subject to `related_catalogs`/depth again.

See [schema-format-reference.md](schema-format-reference.md) for the full
`schema.yaml` field reference, and [gui.md](gui.md) for the web dashboard
that drives all of this without a terminal.
