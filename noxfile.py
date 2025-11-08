"""Automation sessions for linting, type checking, and tests."""

from __future__ import annotations

import nox

PYTHON_VERSIONS = ["3.11"]


@nox.session(python=PYTHON_VERSIONS)
def lint(session: nox.Session) -> None:
    """Run Ruff lint checks."""
    session.install("uv")
    session.run("uv", "pip", "install", ".[dev]")
    session.run("ruff", "check", "--fix", ".")


@nox.session(python=PYTHON_VERSIONS)
def typecheck(session: nox.Session) -> None:
    """Run static type checking."""
    session.install("uv")
    session.run("uv", "pip", "install", ".[dev]")
    session.run("mypy", "src", "tests")
    session.run("pyright", "src", "tests")


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run unit tests with coverage."""
    session.install("uv")
    session.run("uv", "pip", "install", ".[dev]")
    session.run(
        "pytest",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-report=xml",
    )
