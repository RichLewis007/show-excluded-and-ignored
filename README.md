# Ghost Files Finder

Desktop app for exploring files that match rclone filter rules. Built with PySide6 and managed with `uv`.

**Author:** Rich Lewis (@RichLewis007)

## Features

- Load rclone filter lists and scan a chosen root directory for matches.
- Results pane highlights matched files with rule metadata and context actions.
- Context menu lets you open matches in Finder/File Explorer or delete files safely to Trash.
- Toolbar and File menu provide quick access to select a new root, load filter files, and export results.
- Optimized performance for large datasets with thousands of files and deeply nested directories.

## Development

1. Install uv: <https://github.com/astral-sh/uv>
1. Sync dependencies (including dev extras):
   ```
   uv sync --extra dev
   ```
1. Enable git hooks:
   ```
   uv run --extra dev pre-commit install
   ```
1. Run quality checks:
   ```
   uv run --extra dev nox
   ```
1. Launch the app in dev mode:
   ```
   uv run ghost-files-finder
   ```

## Tests

Run a test to detect all types of files and folders listed in the rclone filter file:

```
uv run --extra dev pytest tests/integration/test_scanner_finds_excluded_patterns.py
```

## Status

Core scanning workflow, rule loading, and results interactions are in place.
Performance optimizations ensure smooth operation with large datasets (nodes with 500+ children).
Refer to `docs/program-specifications.md` for the roadmap and planned milestones.
Refer to `docs/debugging-performance-issues.md` for performance troubleshooting guidance.
