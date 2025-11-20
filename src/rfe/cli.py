# Filename: cli.py
# Author: Rich Lewis @RichLewis007
# Description: Command-line interface utilities for Ghost Files Finder. Provides CLI tools for
#              inspecting rclone-style filter matches from the command line.

from __future__ import annotations

import argparse
from pathlib import Path

from .models.match_engine import MatchEngine
from .models.rules_model import parse_filter_file


def build_parser() -> argparse.ArgumentParser:
    # Create and configure the command-line argument parser.
    parser = argparse.ArgumentParser(
        prog="sei-cli",
        description="Inspect rclone-style filter matches from the command line.",
    )
    parser.add_argument("root", type=Path, help="Root directory to scan.")
    parser.add_argument(
        "--filter-file",
        type=Path,
        required=True,
        help="Filter file containing glob rules.",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Treat pattern matching as case-sensitive.",
    )
    parser.add_argument(
        "--show-non-matching",
        action="store_true",
        help="Display files that do not match any rule.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Entry point for the CLI utility.
    parser = build_parser()
    args = parser.parse_args(argv)

    rules = parse_filter_file(args.filter_file)
    engine = MatchEngine(rules, case_sensitive=args.case_sensitive)
    root = args.root.expanduser().resolve()

    if not root.exists():
        parser.error(f"Root path does not exist: {root}")

    count = 0
    for result in engine.scan(root):
        if not result.decision.matched and not args.show_non_matching:
            continue
        status = (
            f"{result.decision.rule.action} ({result.decision.rule_index})"
            if result.decision.matched and result.decision.rule
            else "none"
        )
        print(f"{status}\t{result.rel_path}")
        count += 1

    print(f"Scanned {count} items under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
