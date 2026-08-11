**[English](README.md)** · [Українська](README.uk.md)

# Migrator

Schema-driven data migration engine for 1C:Enterprise / BAF infobases.

Migrator moves reference-data catalogs and documents between two 1C infobases
(e.g. a server-mode source and a file-mode destination) while preserving
internal UUIDs, using:

- **BridgeTool** (`BridgeTool/`) — a local External Data Processor that
  executes generic read/write primitives against the *destination* base only.
  It never makes outbound connections.
- **COM** — used only by the Python orchestrator, to read from the *source*
  base (via a 32-bit PowerShell helper), never by BridgeTool itself.

## Usage

    python -m migrator run <root>:<task> [--limit N]   # run a transfer task
    python -m migrator suggest <root>:<task>           # suggest related_catalogs
    python -m migrator gui                              # local web dashboard

Tasks are `schema.yaml` files under a registered task root (see
`migrator.config.example.yaml`).

## Status

v0.5.0 - the schema-driven engine (source/destination schema, field
mappings, related-catalog cascading, pipeline hooks, tabular parts) and a
local GUI (dashboard, schema editor, live monitor, settings) are working end
to end. Full documentation and the final acceptance test are in progress -
see `CHANGELOG.md`.

## License

MIT - see `LICENSE`.
