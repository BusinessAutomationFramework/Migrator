# Changelog

*(Ukrainian readers: this changelog is maintained in English only — see [README.uk.md](README.uk.md) for a Ukrainian project overview.)*
*(Українською: цей журнал змін ведеться лише англійською — див. [README.uk.md](README.uk.md) для огляду проєкту українською.)*

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
