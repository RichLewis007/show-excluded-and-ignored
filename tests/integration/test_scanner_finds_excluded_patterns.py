"""Integration tests ensuring the bundled filter file matches expected paths."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from rfe.models.match_engine import MatchEngine
from rfe.models.rules_model import parse_filter_file


@pytest.fixture(name="patterns_dir")
def fixture_patterns_dir(tmp_path: Path) -> Path:
    """Build a representative directory tree covering the sample filter file."""
    root = tmp_path / "samples"
    root.mkdir()

    # macOS system files
    (root / ".DS_Store").touch()
    (root / ".AppleDouble").mkdir()
    (root / ".localized").touch()
    (root / ".LSOverride").touch()
    (root / ".TemporaryItems" / "temp.txt").parent.mkdir(parents=True, exist_ok=True)
    (root / ".TemporaryItems" / "temp.txt").touch()
    (root / ".fseventsd").mkdir()
    (root / ".Spotlight-V100").mkdir()
    (root / ".Trashes").mkdir()
    (root / "Backups.backupdb").mkdir()
    (root / ".DocumentRevisions-V100").mkdir()
    (root / ".VolumeIcon.icns").touch()
    (root / ".com.apple.timemachine.donotpresent").touch()
    (root / "Icon1").touch()
    (root / "._Icon1").touch()

    # Windows system files
    (root / "Desktop.ini").touch()
    (root / "lowercase" / "desktop.ini").parent.mkdir(parents=True, exist_ok=True)
    (root / "lowercase" / "desktop.ini").touch()
    (root / "ehthumbs.db").touch()
    (root / "thumbs_upper" / "Thumbs.db").parent.mkdir(parents=True, exist_ok=True)
    (root / "thumbs_upper" / "Thumbs.db").touch()
    (root / "thumbs_lower" / "thumbs.db").parent.mkdir(parents=True, exist_ok=True)
    (root / "thumbs_lower" / "thumbs.db").touch()
    (root / ".picasa.ini").touch()

    # Temporary files
    (root / "temp.tmp").touch()
    (root / "backup.bak").touch()
    (root / "document.~lock.test#").touch()
    (root / "~$doc.docx").touch()
    (root / "download.part").touch()
    (root / "chrome.crdownload").touch()
    (root / "generic.download").touch()
    (root / "vim.swp").touch()
    (root / "vim.swo").touch()

    # Developer cache/build folders
    (root / "__pycache__").mkdir()
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / ".cache").mkdir()
    (root / "dist").mkdir()
    (root / "build").mkdir()
    (root / "coverage").mkdir()
    (root / "project.egg-info").mkdir()
    (root / ".cocoapods").mkdir()
    (root / "compiled.pyo").touch()

    return root


def test_match_engine_flags_patterns(patterns_dir: Path) -> None:
    """Ensure every expected pattern is matched by the filter file."""
    repo_root = Path(__file__).resolve().parents[2]
    filter_file = repo_root / "tests" / "data" / "rclone-filter-list.txt"
    rules = parse_filter_file(filter_file)
    engine = MatchEngine(rules)

    matches = [engine.evaluate_path(path, patterns_dir) for path in iterate_paths(patterns_dir)]

    matched_paths = {result.rel_path for result in matches if result.decision.matched}
    assert matched_paths, "Expected at least one matched path"

    expected_patterns = [
        ".DS_Store",
        ".AppleDouble",
        ".VolumeIcon.icns",
        ".localized",
        ".LSOverride",
        ".TemporaryItems/temp.txt",
        ".fseventsd",
        ".Spotlight-V100",
        ".Trashes",
        "Backups.backupdb",
        ".DocumentRevisions-V100",
        "Icon1",
        "._Icon1",
        "Desktop.ini",
        "lowercase/desktop.ini",
        "ehthumbs.db",
        "thumbs_upper/Thumbs.db",
        "thumbs_lower/thumbs.db",
        ".picasa.ini",
        "temp.tmp",
        "backup.bak",
        "document.~lock.test#",
        "~$doc.docx",
        "download.part",
        "chrome.crdownload",
        "generic.download",
        "vim.swp",
        "vim.swo",
        "__pycache__",
        "node_modules",
        ".cache",
        ".cocoapods",
        "dist",
        "build",
        "coverage",
        "project.egg-info",
        "compiled.pyo",
    ]

    for path in expected_patterns:
        # For directories, ensure any child path matches; for files exact name.
        if path.endswith("."):
            continue
        assert any(
            rel_path == path or rel_path.startswith(path + "/") for rel_path in matched_paths
        ), f"Expected match for pattern: {path}"


def iterate_paths(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        for dirname in dirnames:
            yield current / dirname
        for filename in filenames:
            yield current / filename
