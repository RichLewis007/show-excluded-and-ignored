from pathlib import Path

from rfe.models.match_engine import MatchEngine
from rfe.models.rules_model import Rule


def make_rule(action: str, pattern: str, lineno: int) -> Rule:
    return Rule(action=action, pattern=pattern, lineno=lineno, enabled=True)


def test_first_match_wins(tmp_path: Path) -> None:
    rules = [
        make_rule("-", "**/*.tmp", 1),
        make_rule("-", "**/cache/**", 2),
        make_rule("+", "**/*.md", 3),
    ]
    engine = MatchEngine(rules)

    tmp_file = tmp_path / "notes.tmp"
    tmp_file.write_text("scratch")
    result = engine.evaluate_path(tmp_file, tmp_path)

    assert result.decision.matched is True
    assert result.decision.rule_index == 0


def test_non_matching_path(tmp_path: Path) -> None:
    rules = [make_rule("-", "**/*.tmp", 1)]
    engine = MatchEngine(rules)

    md_file = tmp_path / "readme.md"
    md_file.write_text("hello")
    result = engine.evaluate_path(md_file, tmp_path)

    assert result.decision.matched is False


def test_case_insensitive_matching(tmp_path: Path) -> None:
    rules = [make_rule("-", "**/junk.txt", 1)]
    engine = MatchEngine(rules, case_sensitive=False)

    junk = tmp_path / "Foo" / "JUNK.TXT"
    junk.parent.mkdir()
    junk.write_text("junk")

    result = engine.evaluate_path(junk, tmp_path)
    assert result.decision.matched is True


def test_directory_match(tmp_path: Path) -> None:
    rules = [
        make_rule("-", "**/node_modules/**", 1),
    ]
    engine = MatchEngine(rules)

    node_dir = tmp_path / "project" / "node_modules"
    node_dir.mkdir(parents=True)
    pkg = node_dir / "left-pad"
    pkg.mkdir()

    result = engine.evaluate_path(pkg, tmp_path)
    assert result.decision.matched is True
