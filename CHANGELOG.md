# Changelog

*(Ukrainian readers: this changelog is maintained in English only — see [README.uk.md](README.uk.md) for a Ukrainian project overview.)*
*(Українською: цей журнал змін ведеться лише англійською — див. [README.uk.md](README.uk.md) для огляду проєкту українською.)*

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
