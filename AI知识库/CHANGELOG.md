# Changelog

## [2.2.0] - 2026-06-01

### Added
- `--help` usage display when run without arguments
- Type annotations for all 24 functions
- 7 end-to-end tests with real NVIDIA API calls
- `.env` file for API key isolation
- README.md and CHANGELOG.md

### Changed
- API key moved from config.json to environment variable
- 100 template documents removed (152 → 52 real documents)

### Fixed
- config.json no longer contains plaintext API key

## [2.1.0] - 2026-06-01

### Added
- 27 unit tests covering all 9 commands
- .gitignore for .env and __pycache__

## [2.0.0] - 2026-06-01

### Added
- Rebuilt kb-manager.py from scratch (398 lines)
- 9 CLI commands: init, list, analyze-text, unified-search, batch-import, sync-memory-to-kb, sync-kb-to-memory, rebuild-index, backup
- NVIDIA API integration for AI deep analysis
- Content deduplication via SHA-256 hash
- Dual-track sync (Memory ↔ KB)
- Windows encoding compatibility (UTF-8, GBK fallback)
- File collision avoidance via `unique_path()` — same-slug imports get -N suffix instead of overwrite
