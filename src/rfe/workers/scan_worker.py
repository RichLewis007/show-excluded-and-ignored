# Filename: scan_worker.py
# Author: Rich Lewis @RichLewis007
# Description: Background filesystem scanning worker. Performs filesystem traversal in a
#              separate thread, matches paths against filter rules, and emits progress updates.

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import Event
from time import monotonic

from PySide6.QtCore import QObject, Signal

from rfe.models.fs_model import NodeType, PathNode
from rfe.models.match_engine import MatchEngine, MatchResult
from rfe.models.rules_model import Rule


@dataclass(slots=True)
class ScanStats:
    # Aggregate statistics for a scan run.

    scanned: int = 0
    matched: int = 0
    matched_bytes: int = 0
    files: int = 0
    folders: int = 0
    start_time: float = field(default_factory=monotonic)
    end_time: float | None = None

    @property
    def duration(self) -> float | None:
        # Return the scan duration in seconds, if the scan has finished.
        if self.end_time is None:
            return None
        return self.end_time - self.start_time


@dataclass(slots=True)
class ScanPayload:
    # Result payload emitted on scan completion.

    nodes: list[PathNode]
    stats: ScanStats


class ScanWorker(QObject):
    # Worker object that scans a filesystem subtree for rule matches.

    progress = Signal(
        int, int, int, int, float, str
    )  # files, folders, matches, bytes, elapsed, path
    finished = Signal(object)  # ScanPayload
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        *,
        root_path: Path,
        rules: Iterable[Rule],
        case_sensitive: bool = False,
    ) -> None:
        super().__init__()
        self._root_path = root_path
        self._rules = list(rules)
        self._case_sensitive = case_sensitive
        self._cancel_requested = False
        self._pause_event = Event()
        self._pause_event.set()

    def request_cancel(self) -> None:
        # Signal the worker to stop at the next opportunity.
        self._cancel_requested = True
        self._pause_event.set()

    def request_pause(self) -> None:
        # Temporarily pause traversal until resumed.
        self._pause_event.clear()

    def request_resume(self) -> None:
        # Resume traversal after a pause.
        self._pause_event.set()

    # ------------------------------------------------------------------
    # run_scan returns None when the scan is cancelled.
    # User clicks Cancel → request_cancel() sets flag → scan loop detects it →
    # _run_scan() returns None → start() emits cancelled signal → UI handler runs.

    def start(self) -> None:
        # Entry point executed inside the worker thread.
        payload = self._run_scan()

        if payload is None:
            self.cancelled.emit()
        else:
            self.finished.emit(payload)

    # Internal helpers -------------------------------------------------

    def _run_scan(self) -> ScanPayload | None:
        # Perform the filesystem traversal, respecting cancellation signals.
        root = self._root_path
        if not root.exists():
            raise FileNotFoundError(f"Root path does not exist: {root}")

        engine = MatchEngine(self._rules, case_sensitive=self._case_sensitive)
        stats = ScanStats()

        # Mapping from relative path -> PathNode (including virtual parents).
        nodes: dict[str, PathNode] = {}
        root_key = ""
        nodes[root_key] = PathNode(
            abs_path=root,
            rel_path="",
            type="dir",
        )

        emit_interval = 200

        for dirpath, dirnames, filenames in os.walk(root):
            if self._cancel_requested:
                return None
            if not self._wait_if_paused():
                return None

            current_dir = Path(dirpath)
            entries = list(dirnames) + filenames
            for name in entries:
                if self._cancel_requested:
                    return None
                if not self._wait_if_paused():
                    return None

                abs_path = current_dir / name
                try:
                    result = engine.evaluate_path(abs_path, root)
                except (OSError, ValueError):
                    # Skip unreadable entries but continue scanning.
                    continue

                node = self._build_node(result)
                nodes[result.rel_path] = node
                if result.decision.matched:
                    stats.matched += 1
                    if node.type == "file" and node.size is not None:
                        stats.matched_bytes += node.size

                if node.type == "file":
                    stats.files += 1
                else:
                    stats.folders += 1

                stats.scanned += 1
                if stats.scanned % emit_interval == 0 or stats.scanned == 1:
                    elapsed = monotonic() - stats.start_time
                    self.progress.emit(
                        stats.files,
                        stats.folders,
                        stats.matched,
                        stats.matched_bytes,
                        elapsed,
                        str(abs_path),
                    )

        stats.end_time = monotonic()
        elapsed = stats.end_time - stats.start_time
        self.progress.emit(
            stats.files,
            stats.folders,
            stats.matched,
            stats.matched_bytes,
            elapsed,
            "done",
        )

        tree_nodes = self._build_tree(nodes, root_key)
        self._pause_event.set()
        return ScanPayload(nodes=tree_nodes, stats=stats)

    def _build_node(self, match: MatchResult) -> PathNode:
        # Create a PathNode representation for a filesystem entry.
        abs_path = match.abs_path
        try:
            stat = abs_path.stat()
            size = stat.st_size if abs_path.is_file() else None
            mtime = stat.st_mtime
        except OSError:
            size = None
            mtime = None

        node_type: NodeType = "dir" if abs_path.is_dir() else "file"
        rule_index = match.decision.rule_index
        rule_ids = list(match.all_rule_indexes)

        return PathNode(
            abs_path=abs_path,
            rel_path=match.rel_path,
            type=node_type,
            size=size,
            mtime=mtime,
            rule_index=rule_index,
            rule_ids=rule_ids,
        )

    def _build_tree(
        self,
        nodes: dict[str, PathNode],
        root_key: str,
    ) -> list[PathNode]:
        # Attach child nodes to their parents and return root-level nodes.
        ordered_keys = sorted(
            (key for key in nodes.keys() if key != root_key),
            key=lambda key: (PurePosixPath(key).parts, key),
        )

        # Prepare child lists.
        for node in nodes.values():
            node.children.clear()

        for rel_path in ordered_keys:
            node = nodes[rel_path]
            parent_rel = self._parent_key(rel_path)
            parent = nodes.get(parent_rel)
            if parent is None:
                parent = self._create_virtual_parent(parent_rel, nodes)
            parent.children.append(node)

        # Sort children alphabetically.
        self._sort_children(nodes[root_key])
        return list(nodes[root_key].children)

    def _create_virtual_parent(self, rel_path: str, nodes: dict[str, PathNode]) -> PathNode:
        # Create any missing ancestor nodes so children can attach correctly.
        current = rel_path
        # Build any missing ancestors up to the root.
        missing_paths = []
        while current not in nodes and current != "":
            missing_paths.append(current)
            current = self._parent_key(current)

        for missing in reversed(missing_paths):
            abs_path = self._root_path / missing
            node = PathNode(
                abs_path=abs_path,
                rel_path=missing,
                type="dir",
            )
            nodes[missing] = node

        return nodes.get(rel_path, nodes[""])

    @staticmethod
    def _parent_key(rel_path: str) -> str:
        # Return the parent key for a given relative path.
        path = PurePosixPath(rel_path)
        parent = path.parent
        if parent == PurePosixPath("."):
            return ""
        return parent.as_posix()

    def _sort_children(self, node: PathNode) -> None:
        # Recursively sort children so directories appear before files.
        node.children.sort(key=lambda item: (item.type != "dir", item.name.lower()))
        for child in node.children:
            self._sort_children(child)

    def _wait_if_paused(self) -> bool:
        # Block traversal while a pause has been requested.
        while not self._pause_event.wait(timeout=0.1):
            if self._cancel_requested:
                return False
        return True
