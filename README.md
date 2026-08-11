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

## Status

v0.1.0 - early scaffold. The schema-driven engine, GUI, and documentation are
under active development. See `CHANGELOG.md` for progress.

## License

MIT - see `LICENSE`.
