# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-01-XX

### Added

- File and folder size tracking for matched items during scanning
- Size of matches display in scanning dialog and app footer with proper formatting (\<1 MB, KB, MB, TB, etc.)
- Column sorting by clicking column headers with custom sorting for Size (numeric) and Modified (chronological) columns
- Case-insensitive sorting for Name and Full Path columns
- About dialog showing on app launch with version, copyright, and license information
- macOS system menu "About Ghost Files Finder" and "Quit Ghost Files Finder" items that appear in the macOS menu bar following macOS standards
- MIT License file added to project root
- Time elapsed display in scanning dialog with minutes/seconds format when exceeding 59 seconds
- UI Sounds checkbox in results pane footer to mute/unmute all application sounds
- Pause/Resume functionality for scans that preserves scan progress
- Version information (1.0.0) and copyright (2025 Rich Lewis) in About dialog

### Changed

- Updated application version from 0.1.0 to 1.0.0
- Improved About dialog positioning to appear on the same screen as main window
- Enhanced macOS process name setting for better dock/task switcher integration

### Fixed

- Fixed index validation errors in proxy model sorting to prevent Qt warnings
- Fixed multi-monitor positioning for About dialog and main window to launch on the last-used monitor
- Fixed case-insensitive sorting implementation for Name and Full Path columns using Qt's built-in `setSortCaseSensitivity`
- Improved About dialog timing to show after main window is fully visible
- **Performance**: Fixed application freezing when processing large datasets with many nested directories
  - Implemented incremental node processing with frequent UI updates during tree model population
  - Optimized recursive child processing with chunked processing (25-50 items) and event loop updates
  - Improved column resizing to avoid expensive `resizeColumnToContents()` operations for large datasets
  - Added detailed debug logging for performance bottleneck identification
  - Application now handles nodes with 500+ children without UI freezing

## [Unreleased]

### Added

- Background filesystem `ScanWorker` with progress, cancellation, and real tree population.
- Main window wiring for live scans, status-bar progress updates, and safe thread teardown.
- Tri-state “Select all” control for rule filters plus type-safe PySide6 integrations.
- Expanded pre-commit tooling (ruff, mdformat, JSON formatters) and hardened project ignore list.
- Delete workflow with confirmation dialog and asynchronous Trash worker.
- Export dialog supporting lines, CSV, JSON, and JSONL formats for visible or full results.
- Persistent settings for last-used root/filter paths and default export format.
- Results pane promoted to a dedicated “Results” panel that fills the window beneath the search bar.
- File context menu now offers “Open in Finder/File Explorer” with OS-specific handling.
- “Open…” action validates and loads rclone filter files, replacing rules and triggering a rescan.
- “Select Root…” action lets users change the scan directory from the toolbar or File menu.
- Selecting rules in the sidebar now immediately filters results, with multi-select supported.
- Folder rows render in bold, their full paths include a trailing slash, and the context menu explains that folders cannot be deleted.
- When no rule checkboxes are active the full source tree is shown; unchecking “Select all” clears the result list.
- Added File ▸ Quit command (also on the toolbar) with confirmation dialog before closing the app.
- Clicking a rule highlights its row and colors matching results in the tree with the rule’s tint.
- Double-click rename updates files on disk while keeping highlights and summary counts in sync.
- Results footer now shows live file/folder totals plus highlighted counts, and the tree exposes “Expand all” / “Collapse all” controls.
- Clearing the search field immediately re-runs the filter so visible results reset without extra clicks.
- Modal scanning dialog mirrors footer progress (long-path friendly), now owns the Scan / Pause / Cancel controls, and stays larger to accommodate long paths.
- macOS builds now show “Ghost Files Finder” as the app name and use a bundled window icon.
- Toolbar now presents icon buttons with text labels for scan, source root, rules file, delete, export, and quit actions using bundled Feather SVGs.
- Added helper script `scripts/copy_feather_icons.sh` to sync Feather SVG assets into the project resources.
- Added PyInstaller configuration (`ghost_files_finder.spec`) and helper script to produce distributable builds.
- Selecting a source folder or rules file no longer triggers an automatic scan; the Scan button activates once both selections are made.
- Scan progress dialog now mirrors the main badge image, switches to a “scan complete” badge when finished, uses Feather play/pause/close icons, formats large numbers with thousand separators, and stays open until closed by the user.
- Introduced a QtMultimedia-backed sound manager with bundled tones to provide pleasant audio feedback for toolbar and scan dialog buttons.

### Changed

- Removed the `**/Icon?` filter rule and its Icon sample data from fixtures and tests.
- `create-samples.py` now relies solely on the shared fixture helper; manual extras were removed to avoid divergence.
- Replaced module/class/function docstrings with block comments to standardise documentation style project-wide.
- Removed Pause and Cancel toolbar actions in favour of dialog-hosted controls for scanning.
- Startup no longer triggers an immediate scan; the user initiates scanning explicitly.
- Updated app metadata and configuration directories to use the “Ghost Files Finder” identity and credit Rich Lewis as the author.

## [0.1.0] - 2025-11-08

### Added

- uv-managed project scaffold with PySide6 application entry point and CLI harness.
- Core matching engine implementing rclone-style glob rules with unit tests.
- GUI skeleton: main window, rules sidebar, tree view with search modes, status bar.
- Initial developer tooling (pytest, nox, ruff, mypy) and documentation bootstrap.

[0.1.0]: https://github.com/richlewis007/show-excluded-and-ignored/releases/tag/v0.1.0
[unreleased]: https://github.com/richlewis007/show-excluded-and-ignored/compare/v0.1.0...HEAD
