# Show Excluded and Ignored

Desktop app for exploring files that match rclone filter rules. Built with PySide6 and managed with `uv`.

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
   uv run show-excluded-and-ignored
   ```

## Status

Early scaffolding stage. Refer to `docs/program-specifications.md` for the roadmap.
