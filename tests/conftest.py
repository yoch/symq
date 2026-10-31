"""Shared test configuration: repository paths and optional-capability markers.

Optional capabilities are declared with markers instead of ad-hoc ``skipif`` guards:

* ``native``   -- needs the compiled C core (``symq.backends.zdd_native``);
* ``sat``      -- needs an interruptible SAT solver (``python-sat``);
* ``checkout`` -- needs a git checkout whose ``src/symq`` is the imported package (provenance
  tools read ``git rev-parse HEAD`` and hash the in-tree sources). Running the suite from an
  extracted sdist against the installed package skips these.

A test carrying an unavailable capability is skipped with the precise reason. A skip is not a
validation, so a CI job can turn skips into failures with
``SYMQ_TEST_REQUIRE=native,sat,checkout``.
"""
from __future__ import annotations

import os
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
"""Repository root (the directory holding ``pyproject.toml``)."""


@cache
def native_unavailable_reason() -> str | None:
    try:
        import symq.backends.zdd_native  # noqa: F401
    except ImportError as error:
        return f"native C core unavailable: {error}"
    return None


@cache
def sat_unavailable_reason() -> str | None:
    try:
        from symq.sat import available
    except ImportError as error:  # pragma: no cover - symq.sat itself is pure Python
        return f"symq.sat unavailable: {error}"
    return None if available() else "python-sat is not installed"


@cache
def checkout_unavailable_reason() -> str | None:
    import symq

    if not (ROOT / ".git").exists():
        return "not a git checkout (for example an extracted sdist)"
    if Path(symq.__file__).resolve() != ROOT / "src" / "symq" / "__init__.py":
        return f"symq is imported from {Path(symq.__file__).parent}, not from this checkout"
    return None


_CAPABILITIES = {
    "native": native_unavailable_reason,
    "sat": sat_unavailable_reason,
    "checkout": checkout_unavailable_reason,
}


def _required() -> set[str]:
    value = os.environ.get("SYMQ_TEST_REQUIRE", "")
    required = {part.strip() for part in value.split(",") if part.strip()}
    unknown = required - set(_CAPABILITIES)
    if unknown:
        raise pytest.UsageError(f"SYMQ_TEST_REQUIRE names unknown capabilities: {sorted(unknown)}")
    return required


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    required = _required()
    for item in items:
        for name, probe in _CAPABILITIES.items():
            if item.get_closest_marker(name) is None:
                continue
            reason = probe()
            if reason is None:
                continue
            if name in required:
                raise pytest.UsageError(
                    f"SYMQ_TEST_REQUIRE demands {name!r} but {reason} (needed by {item.nodeid})"
                )
            item.add_marker(pytest.mark.skip(reason=reason))
