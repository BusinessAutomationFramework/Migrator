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

## Documentation

- [docs/architecture.md](docs/architecture.md) - why two interfaces
  (COM + BridgeTool), the exchange protocol, the engine pipeline.
- [docs/schema-format-reference.md](docs/schema-format-reference.md) -
  every `schema.yaml` field, explained.
- [docs/gui.md](docs/gui.md) - the local web dashboard.

## Status

v1.0.0 - complete: the schema-driven engine (source/destination schema,
field mappings, related-catalog cascading, pipeline hooks, tabular parts),
a local GUI (dashboard, schema editor, live monitor, settings), bilingual
docs, and reusable lessons-learned Claude Code skills. The acceptance test
(a full, unlimited "Склады" transfer cascading to 8 related catalogs) is
verified - see `CHANGELOG.md` for the detailed results.

## License

MIT - see `LICENSE`.
