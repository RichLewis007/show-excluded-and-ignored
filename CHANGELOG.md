# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Background filesystem `ScanWorker` with progress, cancellation, and real tree population.
- Main window wiring for live scans, status-bar progress updates, and safe thread teardown.
- Tri-state “Select all” control for rule filters plus type-safe PySide6 integrations.
- Expanded pre-commit tooling (ruff, mdformat, JSON formatters) and hardened project ignore list.
- Delete workflow with confirmation dialog and asynchronous Trash worker.

## [0.1.0] - 2025-11-08

### Added

- uv-managed project scaffold with PySide6 application entry point and CLI harness.
- Core matching engine implementing rclone-style glob rules with unit tests.
- GUI skeleton: main window, rules sidebar, tree view with search modes, status bar.
- Initial developer tooling (pytest, nox, ruff, mypy) and documentation bootstrap.

[0.1.0]: https://github.com/richlewis007/show-excluded-and-ignored/releases/tag/v0.1.0
[unreleased]: https://github.com/richlewis007/show-excluded-and-ignored/compare/v0.1.0...HEAD
