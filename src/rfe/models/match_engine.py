# Filename: match_engine.py
# Author: Rich Lewis @RichLewis007
# Description: Matching engine for rclone-style glob rules. Implements pattern matching
#              algorithms to match file paths against filter rules.

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .rules_model import Rule


@dataclass(slots=True)
class PreparedRule:
    # Internal representation of a rule with expanded pattern variants.

    rule: Rule
    index: int
    patterns: tuple[str, ...]
    patterns_lower: tuple[str, ...]


@dataclass(slots=True)
class MatchDecision:
    # Outcome of matching a single path.

    matched: bool
    rule_index: int | None = None
    rule: Rule | None = None


@dataclass(slots=True)
class MatchResult:
    # Full matching result for a filesystem path.

    abs_path: Path
    rel_path: str
    decision: MatchDecision
    all_rule_indexes: tuple[int, ...]


class MatchEngine:
    # Match engine implementing first-match-wins semantics.

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
        # Return the first matching rule decision for ``rel_path``.
        posix_path, lowered_path = self._prepare_candidate(rel_path)
        matches = self._matching_indexes(posix_path, lowered_path)
        if matches:
            first = matches[0]
            prepared = self._prepared[first]
            return MatchDecision(matched=True, rule_index=first, rule=prepared.rule)
        return MatchDecision(matched=False)

    def matching_rule_indexes(self, rel_path: str) -> tuple[int, ...]:
        # Return all rule indexes that match ``rel_path``.
        posix_path, lowered_path = self._prepare_candidate(rel_path)
        return self._matching_indexes(posix_path, lowered_path)

    def _pattern_matches(
        self,
        prepared: PreparedRule,
        path: PurePosixPath,
        lowered_path: PurePosixPath | None,
    ) -> bool:
        # Check whether any pattern variant matches the provided path.
        patterns = prepared.patterns if self.case_sensitive else prepared.patterns_lower
        test_path = (
            path if self.case_sensitive else lowered_path or PurePosixPath(path.as_posix().lower())
        )

        for pattern in patterns:
            if test_path.match(pattern):
                return True
        return False

    def _prepare_candidate(self, rel_path: str) -> tuple[PurePosixPath, PurePosixPath | None]:
        normalized = rel_path.strip("/")
        candidate = normalized or "."
        posix_path = PurePosixPath(candidate)
        lowered_path = PurePosixPath(candidate.lower()) if not self.case_sensitive else None
        return posix_path, lowered_path

    def _matching_indexes(
        self,
        path: PurePosixPath,
        lowered_path: PurePosixPath | None,
    ) -> tuple[int, ...]:
        matches: list[int] = []
        for prepared in self._prepared:
            if self._pattern_matches(prepared, path, lowered_path):
                matches.append(prepared.index)
        return tuple(matches)

    def _expand_patterns(self, pattern: str) -> tuple[str, ...]:
        # Generate pattern variants that treat ``**`` components as optional.
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
        # Evaluate ``abs_path`` relative to ``root`` and return the decision.
        rel = abs_path.relative_to(root).as_posix()
        posix_path, lowered_path = self._prepare_candidate(rel)
        matches = self._matching_indexes(posix_path, lowered_path)
        if matches:
            first = matches[0]
            prepared = self._prepared[first]
            decision = MatchDecision(matched=True, rule_index=first, rule=prepared.rule)
        else:
            decision = MatchDecision(matched=False)
        return MatchResult(
            abs_path=abs_path,
            rel_path=rel,
            decision=decision,
            all_rule_indexes=matches,
        )

    def scan(self, root: Path) -> Iterator[MatchResult]:
        # Yield match results for every entry beneath ``root``.
        root = root.resolve()
        for dirpath, dirnames, filenames in os.walk(root):
            current_dir = Path(dirpath)
            for name in list(dirnames) + filenames:
                abs_path = current_dir / name
                yield self.evaluate_path(abs_path, root)

    def filter_matches(self, root: Path) -> Iterator[MatchResult]:
        # Yield only those scan results whose decision matched a rule.
        for result in self.scan(root):
            if result.decision.matched:
                yield result
