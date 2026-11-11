"""Record the public API of the SymQ core and compare it with the committed record.

    python tools/api_snapshot.py            # compare; print the differences, exit 1 if any
    python tools/api_snapshot.py --write    # rewrite the snapshot and the generated reference

The record is ``tests/data/api_snapshot.json``. It holds what ``docs/stability.md`` promises:

* the names exported by ``symq``, ``symq.sat``, ``symq.backends`` and ``symq.generators``
  (their ``__all__``), each with its tier, its signature, its dataclass fields and its public
  members;
* the registered backend names, the ordering policies and the theorem names, by tier;
* the arguments of the stable commands (``check``, ``anf``, ``doctor``), the exit code of a
  fixed list of scenarios, and the keys and JSON types of each ``--json`` output.

Nothing of ``symq.experimental`` or ``symq.labs`` is recorded: they carry no promise.

A change to the record is a change to the public API. It is made on purpose, with ``--write``,
and comes with a ``CHANGELOG.md`` line; ``tests/test_api_snapshot.py`` fails otherwise.

What an environment cannot observe (the native classes without the C core, the SAT scenarios
without ``python-sat``) is taken from the committed record, so the comparison still runs there.
The comparison is exact on every supported Python version. ``--write`` refuses an incomplete
environment, a ``symq`` imported from elsewhere than this checkout, and any Python other than the
reference version, so that the committed file always comes from one known configuration.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import importlib
import inspect
import io
import json
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "data" / "api_snapshot.json"
REFERENCE = ROOT / "docs" / "reference" / "api-core.md"
PACKAGES = ("symq", "symq.sat", "symq.backends", "symq.generators")
REFERENCE_PYTHON = (3, 12)
"""The CPython version the record is written with. Every supported version must reproduce it."""

_PHASE = "sign-phase programs with measure-and-reset are outside the classical core"
_STRATEGY = "heuristic selector: its rules are meant to be overturned by new measurements"
_ENCODING = "building blocks of the SAT encoding, which changes with the encoding"
_VARIANT = "comparison variant of a stable backend, kept for measurements"

PROVISIONAL: dict[str, str] = {
    "symq.PhaseProgram": _PHASE,
    "symq.check_phase_equivalence": _PHASE,
    "symq.phase_semantics": _PHASE,
    "symq.Choice": _STRATEGY,
    "symq.choose": _STRATEGY,
    "symq.features": _STRATEGY,
    "symq.sat.Encoder": _ENCODING,
    "symq.sat.Miter": _ENCODING,
    "symq.sat.build_miter": _ENCODING,
    "symq.backends.SparseCopyAlgebra": _VARIANT,
    "symq.backends.PackedFallbackAlgebra": _VARIANT,
    "symq.backends.WireAdaptiveAlgebra": _VARIANT,
    "symq.backends.AutoZDDAlgebra": _VARIANT,
    "symq.backends.MixedSparseZDD": "value type of the two adaptive variants",
}
"""Exported names that are *not* frozen, each with the reason. Every other exported name is
stable. The table is mirrored in ``docs/stability.md`` (a test compares the two)."""

PROVISIONAL_MEMBERS: dict[str, tuple[str, ...]] = {
    "symq.sat.Contract": ("assumption",),
}
"""Members of a stable class that are not frozen. ``Contract.assumption`` takes expressions of
``symq.sat.assumptions``, a module that is not exported."""

STABLE_BACKENDS = ("linear", "packed", "reference", "sparse", "truthtable", "zdd")
NATIVE_BACKENDS = ("zdd-native", "zdd-native-wide")
"""Stable too, but registered only when the optional C core is built."""
STABLE_THEOREMS = ("classical_contract", "classical_full")
PROVISIONAL_THEOREMS = ("sign_phase_exact", "sign_phase_up_to_global")

_BACKEND_IDENTITY = ("name", "max_width")
"""Class attributes of a concrete backend that are stable besides the ``Algebra`` interface."""

_OPERATORS = (
    "__add__", "__and__", "__bool__", "__call__", "__contains__", "__getitem__", "__invert__",
    "__iter__", "__len__", "__mul__", "__or__", "__str__", "__xor__",
)


class Incomplete(RuntimeError):
    """This environment cannot observe a part of the API and no committed record supplies it."""


def tier(qualified: str) -> str:
    return "provisional" if qualified in PROVISIONAL else "stable"


def _own_classes(cls: type) -> list[type]:
    """The classes of ``cls``'s MRO that SymQ defines, most derived first."""
    return [base for base in cls.__mro__ if base.__module__.split(".")[0] == "symq"]


def _plain(value: Any) -> bool:
    if isinstance(value, tuple):
        return all(_plain(item) for item in value)
    return value is None or isinstance(value, (bool, int, float, str))


class _Text(str):
    """An annotation written as text, shown without the quotes ``repr`` would add."""

    __slots__ = ()

    def __repr__(self) -> str:
        return str(self)


def signature(function: Any) -> str:
    """``inspect.signature`` as text; annotations kept as strings lose their quotes."""
    found = inspect.signature(function)

    def plain(annotation: Any) -> Any:
        return _Text(annotation) if isinstance(annotation, str) else annotation

    return str(found.replace(
        parameters=[parameter.replace(annotation=plain(parameter.annotation))
                    for parameter in found.parameters.values()],
        return_annotation=plain(found.return_annotation)))


def _member(member: Any) -> dict[str, Any]:
    abstract = {"abstract": True} if getattr(member, "__isabstractmethod__", False) else {}
    if isinstance(member, property):
        return {"kind": "property", **abstract}
    for wrapper, kind in ((staticmethod, "staticmethod"), (classmethod, "classmethod")):
        if isinstance(member, wrapper):
            return {"kind": kind, "signature": signature(member.__func__), **abstract}
    if inspect.isfunction(member):
        return {"kind": "method", "signature": signature(member), **abstract}
    if _plain(member):
        return {"kind": "attribute", "value": list(member) if isinstance(member, tuple) else member}
    return {"kind": "attribute"}


def _annotation(annotation: Any) -> str:
    return annotation if isinstance(annotation, str) else repr(annotation)


def _members(cls: type) -> dict[str, dict[str, Any]]:
    """Public members of ``cls`` that SymQ defines, each from the most derived definition."""
    fields = ({field.name for field in dataclasses.fields(cls)}
              if dataclasses.is_dataclass(cls) else set())
    found: dict[str, dict[str, Any]] = {}
    for base in _own_classes(cls):
        for name, member in vars(base).items():
            public = not name.startswith("_") or name in _OPERATORS
            if public and name not in fields and name not in found:
                found[name] = _member(member)
        # Instance attributes cannot be seen on a class; the ones a class declares can.
        for name, annotation in vars(base).get("__annotations__", {}).items():
            if not name.startswith("_") and name not in fields and name not in found:
                found[name] = {"kind": "attribute", "annotation": _annotation(annotation)}
    return dict(sorted(found.items()))


def _fields(cls: type) -> list[dict[str, Any]]:
    """The public fields, in order. Underscore fields are private state, not interface."""
    missing = dataclasses.MISSING
    found = []
    for field in dataclasses.fields(cls):
        if field.name.startswith("_"):
            continue
        entry: dict[str, Any] = {
            "name": field.name, "annotation": _annotation(field.type),
            "required": field.default is missing and field.default_factory is missing,
            "in_constructor": field.init, "keyword_only": field.kw_only}
        if field.default is not missing and _plain(field.default):
            default = field.default
            entry["default"] = list(default) if isinstance(default, tuple) else default
        found.append(entry)
    return found


def _describe_class(cls: type) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": "class",
        "bases": [base.__name__ for base in cls.__mro__[1:]
                  if base.__module__.split(".")[0] in ("symq", "builtins") and base is not object],
    }
    if dataclasses.is_dataclass(cls):
        parameters = cls.__dataclass_params__
        entry["dataclass"] = {
            "frozen": parameters.frozen, "eq": parameters.eq, "order": parameters.order,
            "hashable": cls.__hash__ is not None, "slots": "__slots__" in vars(cls),
            "fields": _fields(cls)}
    elif getattr(cls, "_is_protocol", False):
        entry["protocol"] = {"runtime_checkable": bool(getattr(cls, "_is_runtime_protocol", False))}
    else:
        for base in _own_classes(cls):
            if "__init__" in vars(base):
                entry["constructor"] = signature(vars(base)["__init__"])
                break
    entry["members"] = _members(cls)
    return entry


def describe(qualified: str, value: Any) -> dict[str, Any]:
    """The record of one exported name."""
    if inspect.isclass(value):
        entry = _describe_class(value)
    elif inspect.isfunction(value):
        entry = {"kind": "function", "signature": signature(value)}
    else:
        entry = {"kind": "constant", "type": type(value).__name__}
        if _plain(value) and not qualified.endswith(".__version__"):
            entry["value"] = list(value) if isinstance(value, tuple) else value
    if qualified in PROVISIONAL_MEMBERS:
        entry["provisional_members"] = sorted(PROVISIONAL_MEMBERS[qualified])
    return {"tier": tier(qualified), **entry}


def _provisional_members(entries: dict[str, dict[str, Any]]) -> None:
    """A concrete backend promises the ``Algebra`` interface and its identity, nothing more."""
    interface = set(entries["Algebra"]["members"]) | set(_BACKEND_IDENTITY)
    for entry in entries.values():
        if entry.get("kind") == "class" and "Algebra" in entry["bases"]:
            entry["provisional_members"] = sorted(set(entry["members"]) - interface)


def _packages(reference: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for package in PACKAGES:
        module = importlib.import_module(package)
        entries: dict[str, dict[str, Any]] = {}
        for name in sorted(module.__all__):
            qualified = f"{package}.{name}"
            value = getattr(module, name)
            if qualified == "symq.backends.NATIVE_IMPORT_ERROR":
                # ``None`` when the C core loads, the reason as text when it does not.
                entries[name] = {"tier": tier(qualified), "kind": "constant", "type": "str | None"}
            elif value is None:  # a native class, and the C core is not built here
                entries[name] = _recorded(reference, f"the native class {qualified}",
                                          "packages", package, name)
            else:
                entries[name] = describe(qualified, value)
        if package == "symq.backends":
            _provisional_members(entries)
        packages[package] = entries
    return packages


def _recorded(reference: dict[str, Any] | None, what: str, *path: str) -> Any:
    """The committed record at ``path``, for what this environment cannot observe."""
    node: Any = reference
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise Incomplete(f"{what} cannot be observed in this environment")
        node = node[key]
    return node


def _values() -> dict[str, Any]:
    from symq import POLICIES
    from symq.backends import BACKENDS
    from symq.facade import THEOREMS

    stable = (*STABLE_BACKENDS, *NATIVE_BACKENDS)
    theorems = (*STABLE_THEOREMS, *PROVISIONAL_THEOREMS)
    return {
        "backends": {"stable": sorted(STABLE_BACKENDS),
                     "stable_with_native_core": sorted(NATIVE_BACKENDS),
                     "provisional": sorted(set(BACKENDS) - set(stable))},
        "policies": list(POLICIES),
        "theorems": {"stable": sorted(STABLE_THEOREMS), "provisional": sorted(PROVISIONAL_THEOREMS),
                     "no_promise": sorted(set(THEOREMS) - set(theorems))},
    }


def _argument(action: argparse.Action) -> dict[str, Any]:
    if action.option_strings:
        flag = isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction))
        entry: dict[str, Any] = {"name": " ".join(action.option_strings),
                                 "required": action.required}
        entry["value"] = "flag" if flag else getattr(action.type, "__name__", "str").lstrip("_")
        if isinstance(action, argparse._AppendAction):
            entry["repeatable"] = True
    else:
        entry = {"name": action.dest, "required": action.nargs not in ("?", "*"),
                 "value": getattr(action.type, "__name__", "str").lstrip("_")}
    if action.nargs is not None and not (action.option_strings and action.nargs == 0):
        entry["nargs"] = action.nargs
    if action.choices is not None:
        entry["choices"] = list(action.choices)
    if action.default is not None and _plain(action.default) and action.default is not False:
        default = action.default
        entry["default"] = list(default) if isinstance(default, tuple) else default
    return entry


def _commands() -> dict[str, Any]:
    from symq.__main__ import _ENGINES, COMMAND_TIERS, _parser

    parser = _parser()
    subparsers = next(action for action in parser._actions
                      if isinstance(action, argparse._SubParsersAction))
    undeclared = sorted(set(subparsers.choices) ^ set(COMMAND_TIERS))
    if undeclared:
        raise RuntimeError(f"commands without a tier, or tiers without a command: {undeclared}")
    skipped = (argparse._HelpAction, argparse._SubParsersAction)
    return {
        "options": sorted(" ".join(action.option_strings) for action in parser._actions
                          if not isinstance(action, skipped)),
        "engine_aliases": dict(sorted(_ENGINES.items())),
        "commands": {name: [_argument(action) for action in sub._actions
                            if not isinstance(action, argparse._HelpAction)]
                     for name, sub in subparsers.choices.items()
                     if COMMAND_TIERS[name] == "stable"},
    }


_TOFFOLI = {"width": 3, "gates": [["ccx", [0, 1, 2]]]}
_EMPTY = {"width": 3, "gates": []}
_WIDE = {"width": 70, "gates": [["cx", [0, 69]]]}
_INPUTS = {"toffoli.json": _TOFFOLI, "empty.json": _EMPTY, "wide.json": _WIDE}
_HADAMARD = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[1];\nh q[0];\n'


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One command line, run in a directory that holds four small inputs."""

    label: str
    arguments: tuple[str, ...]
    needs: tuple[str, ...] = ()
    """The optional capabilities without which the scenario cannot be observed here."""
    without_native: bool = False
    """Run as if the C core could not be loaded (``symq doctor`` only)."""


SCENARIOS = (
    Scenario("check: equivalent", ("check", "toffoli.json", "toffoli.json", "--json")),
    Scenario("check: equivalent, text output", ("check", "toffoli.json", "toffoli.json")),
    Scenario("check: different", ("check", "toffoli.json", "empty.json", "--json")),
    Scenario("check: different, text output", ("check", "toffoli.json", "empty.json")),
    Scenario("check: budget exhausted", ("check", "toffoli.json", "empty.json", "--engine", "zdd",
                                         "--max-nodes", "1", "--json")),
    Scenario("check: budget exhausted, text output",
             ("check", "toffoli.json", "empty.json", "--engine", "zdd", "--max-nodes", "1")),
    Scenario("check: width beyond the engine",
             ("check", "wide.json", "wide.json", "--engine", "truthtable", "--json")),
    Scenario("check: engine alias 'python'",
             ("check", "toffoli.json", "empty.json", "--engine", "python", "--json")),
    Scenario("check: SAT contract, equivalent on the observed wire",
             ("check", "toffoli.json", "empty.json", "--engine", "sat", "--observe", "0",
              "--json"), needs=("sat",)),
    Scenario("check: unsupported gate in the input", ("check", "h.qasm", "h.qasm")),
    Scenario("check: circuits of different widths", ("check", "toffoli.json", "wide.json")),
    Scenario("check: missing file", ("check", "toffoli.json", "missing.json")),
    Scenario("check: unknown engine",
             ("check", "toffoli.json", "toffoli.json", "--engine", "nope")),
    Scenario("check: missing argument", ("check", "toffoli.json")),
    Scenario("anf: success", ("anf", "toffoli.json", "--json")),
    Scenario("anf: budget exhausted", ("anf", "toffoli.json", "--max-nodes", "1", "--json")),
    Scenario("anf: budget exhausted, text output", ("anf", "toffoli.json", "--max-nodes", "1")),
    Scenario("anf: wire outside the circuit", ("anf", "toffoli.json", "--wire", "7")),
    # What ``doctor --json`` contains depends on what is installed, so each report names the
    # installation it describes; the report without the C core is simulated where it is present.
    Scenario("doctor: report with the native core", ("doctor", "--json"), needs=("native", "sat")),
    Scenario("doctor: report without the native core", ("doctor", "--json"), needs=("sat",),
             without_native=True),
    Scenario("doctor: text report", ("doctor",)),
    Scenario("doctor: native core required and present",
             ("doctor", "--require-native", "--json"), needs=("native", "sat")),
    Scenario("doctor: native core required and absent",
             ("doctor", "--require-native", "--json"), needs=("sat",), without_native=True),
    Scenario("doctor: native core required and absent, text output",
             ("doctor", "--require-native"), without_native=True),
    Scenario("version", ("--version",)),
    Scenario("unknown command", ("frobnicate",)),
)
"""The exit code of each is recorded, and for the JSON kinds of the stable commands the outcome,
the identity (``kind``, ``schema_version``) and the shape of the output of that very scenario:
the keys present when a command succeeds and when it stops without a result are not the same."""

_JSON_KINDS = {"symq_classical_check": "check", "symq_anf": "anf", "symq_doctor": "doctor"}
_OPEN = {"anf.outputs", "doctor.native.max_variables"}
"""Objects keyed by data (a wire index, a backend name): the shape of their values is recorded
once, under ``*``."""
_OPAQUE = {"doctor.sources", "doctor.external"}
"""Objects whose content is explicitly outside the promise (``docs/stability.md``)."""
_EITHER = {"doctor.native.import_error": {"null", "string"}}
"""Values whose type depends on the installation, so that no single environment sees both:
``null`` when the C core loads, the reason as text when it does not."""


def _json_type(value: Any) -> str:
    for kind, name in ((bool, "boolean"), (int, "integer"), (float, "number"), (str, "string"),
                       (list, "array"), (dict, "object")):
        if isinstance(value, kind):
            return name
    return "null"


def _shape(value: Any, command: str, path: str, found: dict[str, set[str]]) -> None:
    """Record the JSON type at ``path`` and, recursively, of what ``value`` contains."""
    qualified = f"{command}.{path}"
    kind = _json_type(value)
    if qualified in _EITHER:
        if kind not in _EITHER[qualified]:
            raise RuntimeError(f"{qualified} is {kind}, expected one of {sorted(_EITHER[qualified])}")
        found.setdefault(path, set()).update(_EITHER[qualified])
    else:
        found.setdefault(path, set()).add(kind)
    if qualified in _OPAQUE:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _shape(item, command, f"{path}.*" if qualified in _OPEN else f"{path}.{key}", found)
    elif isinstance(value, list):
        for item in value:
            _shape(item, command, f"{path}[]", found)


def _run(scenario: Scenario, directory: Path) -> tuple[int, Any]:
    import symq.doctor
    from symq.__main__ import main

    out = io.StringIO()
    argv = [str(directory / word) if word.endswith((".json", ".qasm")) else word
            for word in scenario.arguments]
    present = symq.doctor.has_native
    if scenario.without_native:
        symq.doctor.has_native = lambda: False
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(argv)
            except SystemExit as exit_:
                code = 0 if exit_.code is None else exit_.code
    finally:
        symq.doctor.has_native = present
    if not isinstance(code, int):
        raise TypeError(f"{scenario.label}: exit status {code!r} is not an integer")
    try:
        return code, json.loads(out.getvalue())
    except ValueError:
        return code, None


def _capabilities() -> dict[str, bool]:
    from symq import has_native
    from symq.sat import available

    return {"native": has_native(), "sat": available()}


def _cli(reference: dict[str, Any] | None) -> dict[str, Any]:
    capabilities = _capabilities()
    codes: dict[str, int] = {}
    outcomes: dict[str, str] = {}
    identity: dict[str, dict[str, Any]] = {}
    shapes: dict[str, dict[str, list[str]]] = {}
    with tempfile.TemporaryDirectory() as name:
        directory = Path(name)
        for file, content in _INPUTS.items():
            (directory / file).write_text(json.dumps(content), encoding="utf-8")
        (directory / "h.qasm").write_text(_HADAMARD, encoding="utf-8")
        for scenario in SCENARIOS:
            label = scenario.label
            if not all(capabilities[name] for name in scenario.needs):
                # Not observable here: this scenario is taken from the record as a whole. Every
                # scenario that does run is compared exactly, so nothing else is trusted.
                recorded = _recorded(reference, f"the scenario {label!r}", "cli")
                codes[label] = _recorded(recorded, f"the scenario {label!r}", "exit_codes", label)
                for section, target in (("outcomes", outcomes), ("json", shapes),
                                        ("json_identity", identity)):
                    if label in recorded.get(section, {}):
                        target[label] = recorded[section][label]
                continue
            code, output = _run(scenario, directory)
            codes[label] = code
            command = _JSON_KINDS.get(output.get("kind")) if isinstance(output, dict) else None
            if command is None:
                continue
            identity[label] = {"kind": output["kind"], "schema_version": output["schema_version"]}
            if "outcome" in output:
                outcomes[label] = output["outcome"]
            found: dict[str, set[str]] = {}
            for key, value in output.items():
                _shape(value, command, key, found)
            shapes[label] = {key: sorted(kinds) for key, kinds in sorted(found.items())}
    return {**_commands(), "exit_codes": codes, "outcomes": outcomes, "json_identity": identity,
            "json": shapes}


def build(reference: dict[str, Any] | None = None) -> dict[str, Any]:
    """The API record of the running interpreter.

    ``reference`` (the committed record) supplies what cannot be observed here; without it an
    unobservable part raises :class:`Incomplete`.
    """
    return {"snapshot_version": 1, "packages": _packages(reference), "values": _values(),
            "cli": _cli(reference)}


def differences(expected: Any, actual: Any, path: str = "") -> Iterator[str]:
    """One line per place where ``actual`` departs from ``expected``."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            where = f"{path}.{key}" if path else key
            if key not in actual:
                yield f"removed: {where}"
            elif key not in expected:
                yield f"added: {where}"
            else:
                yield from differences(expected[key], actual[key], where)
    elif expected != actual:
        yield f"changed: {path}: {json.dumps(expected)} -> {json.dumps(actual)}"


def load() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def dump(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def _summary(value: Any) -> str:
    text = inspect.getdoc(value) or ""
    return " ".join(text.split("\n\n")[0].split())


def _field_text(field: dict[str, Any]) -> str:
    text = f"{field['name']}: {field['annotation']}"
    if "default" in field:
        text += f" = {field['default']!r}"
    elif not field["required"]:
        text += " = ..."
    return f"`{text}`"


def _reference_lines(snapshot: dict[str, Any], lookup: Callable[[str, str], Any]) -> Iterator[str]:
    yield "# Core API reference"
    yield ""
    yield ("<!-- Generated by `python tools/api_snapshot.py --write` from the live package and "
           "`tests/data/api_snapshot.json`. Do not edit by hand. -->")
    yield ""
    yield ("Every name exported by the core packages, with its tier "
           "([stability policy](../stability.md)), its signature or constructor, its fields and "
           "members, and the first paragraph of its documentation. `symq.experimental` and `symq.labs` carry no promise and are not "
           "listed.")
    for package in PACKAGES:  # the order of the stability policy, not the order of the file
        entries = snapshot["packages"][package]
        yield ""
        yield f"## `{package}`"
        for name, entry in sorted(entries.items()):
            value = lookup(package, name)
            yield ""
            signature = entry.get("signature", "")
            yield f"### `{name}{signature}`"
            yield ""
            yield f"*{entry['kind']}, {entry['tier']}*"
            summary = _summary(value) if entry["kind"] != "constant" else ""
            if summary:
                yield ""
                yield summary
            if entry["kind"] != "class":
                if "value" in entry:
                    yield ""
                    yield f"Value: `{json.dumps(entry['value'])}`."
                continue
            if entry["bases"]:
                yield ""
                yield "Bases: " + ", ".join(f"`{base}`" for base in entry["bases"]) + "."
            if "constructor" in entry:
                yield ""
                yield f"Constructor: `{entry['constructor']}`."
            fields = entry.get("dataclass", {}).get("fields", [])
            if fields:
                yield ""
                yield "Fields: " + ", ".join(_field_text(field) for field in fields) + "."
            provisional = set(entry.get("provisional_members", ()))
            rows = [(member, record) for member, record in sorted(entry["members"].items())
                    if member not in provisional]
            if rows:
                yield ""
                yield "| Member | Kind | Signature, type or value |"
                yield "| --- | --- | --- |"
                for member, record in rows:
                    text = record.get("signature", "") or record.get("annotation", "")
                    if "value" in record:
                        text = json.dumps(record["value"])
                    cell = f"`{text}`".replace("|", "\\|") if text else ""
                    yield f"| `{member}` | {record['kind']} | {cell} |"
            if provisional:
                yield ""
                yield ("Provisional members (beyond the `Algebra` interface): "
                       + ", ".join(f"`{member}`" for member in sorted(provisional)) + ".")
    yield ""


def reference_text(snapshot: dict[str, Any]) -> str:
    """The generated ``docs/reference/api-core.md`` for ``snapshot`` and the live docstrings."""
    def lookup(package: str, name: str) -> Any:
        return getattr(importlib.import_module(package), name)

    return "\n".join(_reference_lines(snapshot, lookup))


def writable() -> str | None:
    """Why this environment may not write the record, or ``None`` when it may."""
    import symq

    if sys.version_info[:2] != REFERENCE_PYTHON:
        return "the record is written with Python {}.{}".format(*REFERENCE_PYTHON)
    imported = Path(symq.__file__).resolve().parent
    if imported != ROOT / "src" / "symq":
        return (f"the record must describe this checkout, but symq is imported from {imported}; "
                "run with PYTHONPATH=src or an editable install of this checkout")
    missing = [name for name, present in _capabilities().items() if not present]
    if missing:
        return f"the record needs every optional capability; missing: {', '.join(missing)}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="rewrite the snapshot and the generated reference")
    arguments = parser.parse_args(argv)
    if arguments.write:
        reason = writable()
        if reason is not None:
            print(f"api_snapshot: {reason}", file=sys.stderr)
            return 2
        snapshot = build()
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(dump(snapshot), encoding="utf-8")
        REFERENCE.write_text(reference_text(snapshot), encoding="utf-8")
        print(f"wrote {SNAPSHOT.relative_to(ROOT)} and {REFERENCE.relative_to(ROOT)}")
        return 0
    expected = load()
    found = list(differences(expected, build(expected)))
    for line in found:
        print(line)
    if found:
        print(f"{len(found)} difference(s) from {SNAPSHOT.relative_to(ROOT)}; if intended, run "
              "'python tools/api_snapshot.py --write' and add a CHANGELOG line", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
