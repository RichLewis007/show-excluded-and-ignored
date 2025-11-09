"""Create a sample tree covering every rule in the bundled filter file.

This utility mirrors the integration-test fixture and is helpful for manual QA
or demonstrations. Usage examples:

    uv run --extra dev python create-samples.py
    uv run --extra dev python create-samples.py --output ./temp/samples --force

The ``--extra dev`` flag ensures optional development dependencies are available.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Protocol, cast

from tests.integration.test_scanner_finds_excluded_patterns import fixture_patterns_dir


def create_samples(destination: Path, *, force: bool) -> Path:
    """Create the sample tree at ``destination``.

    Args:
        destination: Directory where the structure should be created.
        force: If True, overwrite the destination when it already exists.

    Returns:
        The destination path.
    """
    if destination.exists():
        if not force:
            raise FileExistsError(
                f"Destination {destination} already exists. Use --force to overwrite."
            )
        shutil.rmtree(destination)

    destination.mkdir(parents=True, exist_ok=True)

    class _PatternsDirFactory(Protocol):
        def __call__(self, *, tmp_path: Path) -> Path: ...

    factory = cast(_PatternsDirFactory, getattr(fixture_patterns_dir, "__wrapped__", None))
    if factory is None:
        raise RuntimeError("fixtures_patterns_dir.__wrapped__ is unavailable.")
    factory(tmp_path=destination)

    # The integration fixture builds its structure at ``tmp_path / "samples"``.
    # When users pass an explicit destination (e.g., ./temp/samples) we only
    # want that single directory, so flatten any nested ``samples`` folder.
    nested = destination / "samples"
    if nested.exists() and nested.is_dir():
        for child in list(nested.iterdir()):
            target = destination / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            child.rename(target)
        shutil.rmtree(nested)

    _ensure_additional_examples(destination)

    return destination


def _ensure_additional_examples(destination: Path) -> None:
    """Create sample entries not covered by the fixture helper."""
    extras = {
        ".VolumeIcon.icns": "file",
        ".com.apple.timemachine.donotpresent": "file",
        "document.~lock.test#": "file",
        "._Icon1": "file",
    }
    extra_dirs = [".cocoapods"]

    obsolete = destination / "~lock.test#"
    if obsolete.exists():
        obsolete.unlink()

    for rel, kind in extras.items():
        path = destination / rel
        if path.exists():
            continue
        if kind == "file":
            path.touch()

    for rel in extra_dirs:
        path = destination / rel
        path.mkdir(exist_ok=True)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Create a sample directory tree containing every pattern from a given rclone filter list file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./temp"),
        help="Destination directory for generated samples (default: %(default)s).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination directory if it already exists.",
    )

    args = parser.parse_args()
    target = create_samples(args.output, force=args.force)
    print(f"Created sample tree at {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
