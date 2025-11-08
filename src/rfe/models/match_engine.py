"""Matching engine for rclone-style glob rules."""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .rules_model import Rule


@dataclass(slots=True)
class PreparedRule:
    rule: Rule
    index: int
    patterns: tuple[str, ...]
    patterns_lower: tuple[str, ...]


@dataclass(slots=True)
class MatchDecision:
    matched: bool
    rule_index: int | None = None
    rule: Rule | None = None


@dataclass(slots=True)
class MatchResult:
    abs_path: Path
    rel_path: str
    decision: MatchDecision


class MatchEngine:
    """Match engine implementing first-match-wins semantics."""

    def __init__(self, rules: Sequence[Rule], *, case_sensitive: bool = False) -> None:
        self.rules = rules
        self.case_sensitive = case_sensitive
        self._prepared: list[PreparedRule] = [
            PreparedRule(
                rule=rule,
                index=idx,
                patterns=self._expand_patterns(rule.pattern),
                patterns_lower=self._expand_patterns(rule.pattern.lower()),
            )
            for idx, rule in enumerate(rules)
            if rule.pattern
        ]

    def match_path(self, rel_path: str) -> MatchDecision:
        normalized = rel_path.strip("/")
        candidate = normalized or "."
        posix_path = PurePosixPath(candidate)
        lowered_path = PurePosixPath(candidate.lower()) if not self.case_sensitive else None

        for prepared in self._prepared:
            if self._pattern_matches(prepared, posix_path, lowered_path):
                return MatchDecision(
                    matched=True,
                    rule_index=prepared.index,
                    rule=prepared.rule,
                )
        return MatchDecision(matched=False)

    def _pattern_matches(
        self,
        prepared: PreparedRule,
        path: PurePosixPath,
        lowered_path: PurePosixPath | None,
    ) -> bool:
        patterns = prepared.patterns if self.case_sensitive else prepared.patterns_lower
        test_path = (
            path if self.case_sensitive else lowered_path or PurePosixPath(path.as_posix().lower())
        )

        for pattern in patterns:
            if test_path.match(pattern):
                return True
        return False

    def _expand_patterns(self, pattern: str) -> tuple[str, ...]:
        """Generate pattern variants that treat ``**`` components as optional."""
        variants: set[str] = {pattern}
        queue: list[str] = [pattern]

        while queue:
            current = queue.pop()
            for token in ("**/", "/**", "**"):
                start = current.find(token)
                while start != -1:
                    reduced = current[:start] + current[start + len(token) :]
                    if reduced and reduced not in variants:
                        variants.add(reduced)
                        queue.append(reduced)
                    start = current.find(token, start + 1)

        # Ensure patterns retain original ordering preference: longer first.
        return tuple(sorted(variants, key=lambda item: (-len(item), item)))

    def evaluate_path(self, abs_path: Path, root: Path) -> MatchResult:
        rel = abs_path.relative_to(root).as_posix()
        decision = self.match_path(rel)
        return MatchResult(abs_path=abs_path, rel_path=rel, decision=decision)

    def scan(self, root: Path) -> Iterator[MatchResult]:
        root = root.resolve()
        for dirpath, dirnames, filenames in os.walk(root):
            current_dir = Path(dirpath)
            for name in list(dirnames) + filenames:
                abs_path = current_dir / name
                yield self.evaluate_path(abs_path, root)

    def filter_matches(self, root: Path) -> Iterator[MatchResult]:
        for result in self.scan(root):
            if result.decision.matched:
                yield result
