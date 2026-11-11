"""Shared test configuration: repository paths and optional-capability markers.

Optional capabilities are declared with markers instead of ad-hoc ``skipif`` guards:

* ``native``   -- needs the compiled C core (``symq.backends.zdd_native``);
* ``sat``      -- needs an interruptible SAT solver (``python-sat``);
* ``checkout`` -- needs a git checkout whose ``src/symq`` is the imported package (provenance
  tools read ``git rev-parse HEAD`` and hash the in-tree sources). Running the suite from an
  extracted sdist against the installed package skips these;
* ``fault_injection`` -- needs the instrumented build of the C core, whose allocations can be
  made to fail (``python tools/sanitize_native.py``); the package build never has these hooks.

A test carrying an unavailable capability is skipped with the precise reason. A skip is not a
validation, so a CI job can turn skips into failures with
``SYMQ_TEST_REQUIRE=native,sat,checkout``.

Every test also receives exactly one **tier** marker, derived from what its module imports:

* ``labs``         -- reaches ``symq.labs`` (research, no API promise);
* ``experimental`` -- reaches ``symq.experimental`` but not ``symq.labs``;
* ``core``         -- everything else: the maintained package and the repository-level guards.

The tier is read from the import statements of the test module and, transitively, of the
repository modules it imports (``tests.testkit``, ``benchmarks``, ``tools``). It cannot see a
module named only in a string (``importlib.import_module``, a ``python -m symq ...`` subprocess),
so it classifies tests for selection and coverage (``-m core``); it is not an isolation proof.
"""
from __future__ import annotations

import ast
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


@cache
def fault_injection_unavailable_reason() -> str | None:
    reason = native_unavailable_reason()
    if reason is not None:
        return reason
    from symq.backends import _zdd

    if not hasattr(_zdd, "_fault_inject"):
        return ("the C core was built without allocation-failure hooks; "
                "run python tools/sanitize_native.py")
    return None


_CAPABILITIES = {
    "native": native_unavailable_reason,
    "sat": sat_unavailable_reason,
    "checkout": checkout_unavailable_reason,
    "fault_injection": fault_injection_unavailable_reason,
}


def _required() -> set[str]:
    value = os.environ.get("SYMQ_TEST_REQUIRE", "")
    required = {part.strip() for part in value.split(",") if part.strip()}
    unknown = required - set(_CAPABILITIES)
    if unknown:
        raise pytest.UsageError(f"SYMQ_TEST_REQUIRE names unknown capabilities: {sorted(unknown)}")
    return required


TIERS = ("core", "experimental", "labs")
"""Tier markers, from the maintained core to research code; a test carries exactly one."""

_LOCAL_PACKAGES = ("tests", "benchmarks", "tools")


@cache
def _imported_modules(path: Path) -> frozenset[str]:
    """Absolute names of every module ``path`` imports, at any nesting depth."""
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    if package[:1] == ("src",):
        package = package[1:]  # ``src/symq/experimental/x.py`` is the module symq.experimental.x
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package[:len(package) - node.level + 1]) if node.level else []
            if node.module:
                base += node.module.split(".")
            module = ".".join(base)
            names.add(module)
            # ``from tests.testkit import liveness`` names a module, not an attribute.
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return frozenset(names)


def _local_source(module: str) -> Path | None:
    parts = module.split(".")
    if parts[:2] == ["symq", "experimental"]:
        # Some ``symq.experimental`` modules only re-export ``symq.labs``: a test that imports
        # one of them reaches labs, so the opt-in layer is followed too. The rest of ``symq`` is
        # not: the core never imports labs at module level.
        base = ROOT.joinpath("src", *parts)
    elif parts[0] in _LOCAL_PACKAGES:
        base = ROOT.joinpath(*parts)
    else:
        return None
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


@cache
def module_tier(path: Path) -> str:
    """Highest layer reached by ``path`` through its imports and its repository-local imports.

    ``path`` is a resolved path. Anything that is not Python source of this repository (another
    file type, or a test collected from outside ``ROOT`` in the same session) is ``core``.
    """
    if path.suffix != ".py" or ROOT not in path.parents:
        return TIERS[0]
    seen, pending, rank = {path}, [path], 0
    while pending:
        for module in _imported_modules(pending.pop()):
            if module == "symq.labs" or module.startswith("symq.labs."):
                return "labs"
            if module == "symq.experimental" or module.startswith("symq.experimental."):
                rank = 1
            source = _local_source(module)
            if source is not None and source not in seen:
                seen.add(source)
                pending.append(source)
    return TIERS[rank]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(getattr(pytest.mark, module_tier(Path(str(item.path)).resolve())))
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
