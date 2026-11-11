"""The public API of the core is the committed record; drifting from it is a deliberate act.

``tests/data/api_snapshot.json`` is what ``docs/stability.md`` promises. These tests rebuild the
record from the running package and fail on any difference. To change the public surface on
purpose, run ``python tools/api_snapshot.py --write`` and add a ``CHANGELOG.md`` line.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib
import re
import sys

import pytest

from tests.conftest import ROOT
from tools import api_snapshot
from tools.api_snapshot import (
    PACKAGES,
    PROVISIONAL,
    REFERENCE,
    REFERENCE_PYTHON,
    build,
    differences,
    load,
    reference_text,
)

ON_REFERENCE_PYTHON = sys.version_info[:2] == REFERENCE_PYTHON
HOW_TO = ("the public API differs from tests/data/api_snapshot.json; if the change is intended, "
          "run 'python tools/api_snapshot.py --write' and add a CHANGELOG line:\n")


def _compare(expected, actual):
    """Exact on every supported Python: a version that renders a signature differently must be
    looked at, not waved through."""
    return list(differences(expected, actual))


def test_the_public_api_matches_the_record():
    recorded = load()
    found = _compare(recorded, build(recorded))
    assert not found, HOW_TO + "\n".join(found)


@pytest.mark.native
@pytest.mark.sat
def test_a_complete_environment_observes_every_part_itself():
    """With the C core and SAT present nothing is taken from the record, so nothing is trusted."""
    found = _compare(load(), build())
    assert not found, HOW_TO + "\n".join(found)


@pytest.mark.native
@pytest.mark.sat
@pytest.mark.skipif(not ON_REFERENCE_PYTHON, reason="the generated page is checked with the Python version that writes it")
def test_the_generated_reference_is_current():
    assert REFERENCE.read_text(encoding="utf-8") == reference_text(load()), (
        "docs/reference/api-core.md is stale: run 'python tools/api_snapshot.py --write'")


def test_the_record_covers_exactly_the_exported_names():
    recorded = load()["packages"]
    assert set(recorded) == set(PACKAGES)
    for package in PACKAGES:
        assert sorted(recorded[package]) == sorted(importlib.import_module(package).__all__)


def test_every_provisional_name_is_exported_and_recorded_as_such():
    recorded = load()["packages"]
    for qualified in PROVISIONAL:
        package, _, name = qualified.rpartition(".")
        assert recorded[package][name]["tier"] == "provisional"
    tiers = {entry["tier"] for entries in recorded.values() for entry in entries.values()}
    assert tiers == {"stable", "provisional"}


def _policy() -> str:
    return (ROOT / "docs" / "stability.md").read_text(encoding="utf-8")


def _names(cell: str) -> set[str]:
    return set(re.findall(r"`([^`]+)`", cell))


def test_the_policy_page_lists_exactly_the_provisional_names():
    """``docs/stability.md`` is what users read; it must not drift from the table that is tested."""
    section = _policy().split("### Provisional names", 1)[1].split("### Names inside", 1)[0]
    assert set(re.findall(r"`(symq[\w.]*)`", section)) == set(PROVISIONAL)


def test_the_policy_page_gives_each_backend_and_theorem_its_recorded_tier():
    values = load()["values"]
    rows = {line.split("|")[1].strip(): [cell for cell in line.split("|")[2:6]]
            for line in _policy().splitlines() if line.startswith(("| Backend names", "| Theorem"))}
    backends = rows["Backend names (keys of `BACKENDS`)"]
    assert [_names(cell) for cell in backends] == [
        set(values["backends"]["stable"]), set(values["backends"]["stable_with_native_core"]),
        set(values["backends"]["provisional"]), set()]
    theorems = rows["Theorem names of `verify` and `verify_explicit`"]
    assert [_names(cell) for cell in theorems] == [
        set(values["theorems"]["stable"]), set(), set(values["theorems"]["provisional"]),
        set(values["theorems"]["no_promise"])]


def test_the_policy_page_documents_every_exit_code_the_commands_produce():
    table = _policy().split("| Exit code | Meaning |", 1)[1].split("\n\n", 1)[0]
    documented = {int(line.split("|")[1]) for line in table.splitlines()[2:]}
    observed = set(load()["cli"]["exit_codes"].values())
    from symq.__main__ import EXIT_INTERNAL, EXIT_USAGE

    assert observed | {EXIT_INTERNAL} == documented == {0, 1, 2, EXIT_USAGE, EXIT_INTERNAL}
    assert "exit codes: 0 equivalent/success, 1 different, 2 inconclusive or unsupported, " \
        "3 usage or input error, 4 internal error" in " ".join(_parser_help().split())


def test_the_policy_page_names_the_supported_python_versions():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    versions = sorted(re.findall(r'"Programming Language :: Python :: (3\.\d+)"', project),
                      key=lambda text: int(text.split(".")[1]))
    assert f"CPython {versions[0]} to {versions[-1]}" in _policy()


def _parser_help() -> str:
    from symq.__main__ import _parser

    return _parser().format_help()


def test_backend_and_theorem_tiers_cover_the_live_registries():
    from symq.backends import BACKENDS, has_native
    from symq.facade import THEOREMS

    values = load()["values"]
    backends = values["backends"]
    native = set(backends["stable_with_native_core"])
    assert {*backends["stable"], *backends["provisional"]} == set(BACKENDS) - native
    if has_native():
        assert native <= set(BACKENDS)
    assert {name for names in values["theorems"].values() for name in names} == set(THEOREMS)


def test_a_concrete_backend_promises_the_algebra_interface_only():
    recorded = load()["packages"]["symq.backends"]
    interface = set(recorded["Algebra"]["members"])
    assert recorded["Algebra"].get("provisional_members") is None
    for name in ("ZDDAlgebra", "NativeZDDAlgebra", "PackedAlgebra"):
        entry = recorded[name]
        assert set(entry["members"]) - set(entry["provisional_members"]) <= interface | {
            "name", "max_width"}
    assert "node_count" in recorded["ZDDAlgebra"]["provisional_members"]


def test_check_json_keys_are_named_and_exist_on_the_record():
    """The keys are an explicit list: a new record field must not leak into the CLI by accident,
    and a renamed field must fail here rather than at run time."""
    from symq import VerificationRecord
    from symq.__main__ import _CHECK_JSON_KEYS

    fields = {field.name for field in dataclasses.fields(VerificationRecord)}
    assert set(_CHECK_JSON_KEYS) <= fields
    shapes = load()["cli"]["json"]
    assert len([label for label in shapes if label.startswith("check:")]) >= 5
    for label, keys in shapes.items():
        if label.startswith("check:"):
            assert set(keys) == {*_CHECK_JSON_KEYS, "schema_version", "kind"}, label


def test_every_command_states_its_tier_in_its_help():
    """Read from the parser, not from formatted text: argparse may colour or wrap its help."""
    import argparse

    from symq.__main__ import COMMAND_TIERS, _parser

    subparsers = next(action for action in _parser()._actions
                      if isinstance(action, argparse._SubParsersAction))
    helps = {action.dest: action.help for action in subparsers._choices_actions}
    assert set(helps) == set(COMMAND_TIERS)
    assert set(COMMAND_TIERS.values()) == {"stable", "experimental", "labs"}
    assert sorted(load()["cli"]["commands"]) == sorted(
        name for name, tier in COMMAND_TIERS.items() if tier == "stable")
    prefix = {"stable": "", "experimental": "[experimental] ", "labs": "[labs, no API promise] "}
    for name, tier in COMMAND_TIERS.items():
        assert helps[name].startswith(prefix[tier]), name
        if tier == "stable":
            assert not helps[name].startswith("["), name


# ---- the comparison itself must see what it claims to see ----

def _mutations():
    def remove_name(snapshot):
        del snapshot["packages"]["symq"]["check_equivalence"]

    def add_name(snapshot):
        snapshot["packages"]["symq"]["brand_new"] = {"tier": "stable", "kind": "function",
                                                     "signature": "()"}

    def change_signature(snapshot):
        snapshot["packages"]["symq"]["check_equivalence"]["signature"] += " # changed"

    def change_tier(snapshot):
        snapshot["packages"]["symq"]["choose"]["tier"] = "stable"

    def drop_field(snapshot):
        snapshot["packages"]["symq"]["Budget"]["dataclass"]["fields"].pop()

    def drop_method(snapshot):
        del snapshot["packages"]["symq"]["Circuit"]["members"]["run"]

    def change_base(snapshot):
        snapshot["packages"]["symq"]["QasmSyntaxError"]["bases"].remove("ValueError")

    def change_exit_code(snapshot):
        snapshot["cli"]["exit_codes"]["check: different"] = 2

    def drop_json_key(snapshot):
        del snapshot["cli"]["json"]["check: different"]["witness"]

    def retype_json_key(snapshot):
        snapshot["cli"]["json"]["anf: success"]["width"] = ["string"]

    def bump_schema_version(snapshot):
        snapshot["cli"]["json_identity"]["check: equivalent"]["schema_version"] = 2

    def rename_outcome(snapshot):
        snapshot["cli"]["outcomes"]["check: budget exhausted"] = "undecided"

    def drop_argument(snapshot):
        snapshot["cli"]["commands"]["check"].pop()

    def move_backend(snapshot):
        snapshot["values"]["backends"]["stable"].remove("zdd")

    return [remove_name, add_name, change_signature, change_tier, drop_field, drop_method,
            change_base, change_exit_code, drop_json_key, retype_json_key, bump_schema_version,
            rename_outcome, drop_argument, move_backend]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda mutate: mutate.__name__)
def test_a_change_to_the_surface_is_reported(mutate):
    recorded = load()
    changed = copy.deepcopy(recorded)
    mutate(changed)
    assert list(differences(recorded, changed)), f"{mutate.__name__} went unnoticed"
    assert not list(differences(recorded, copy.deepcopy(recorded)))


# ---- and the record must be built from the live package, not from itself ----

def _live_mutations():
    """Each changes the running package the way a careless commit would."""
    import symq
    import symq.__main__ as cli
    import symq.generators
    from symq import Budget, Circuit
    from symq.backends import Algebra

    def function_default(patch):
        def check_equivalence(left, right, *, backend="zdd", budget=None, backend_options=None,
                              order=None):
            raise NotImplementedError
        patch.setattr(symq, "check_equivalence", check_equivalence)

    def method_removed(patch):
        patch.delattr(Circuit, "inverse")

    def operator_removed(patch):
        patch.delattr(symq.ANF, "__mul__")

    def property_became_method(patch):
        patch.setattr(symq.ANF, "degree", lambda self: 0)

    def abstract_method_made_concrete(patch):
        patch.setattr(Algebra.variable, "__isabstractmethod__", False)

    def protocol_no_longer_runtime_checkable(patch):
        patch.setattr(symq.Verdict, "_is_runtime_protocol", False)

    def declared_attribute_removed(patch):
        annotations = dict(symq.ResourceLimitExceeded.__annotations__)
        del annotations["observed"]
        patch.setattr(symq.ResourceLimitExceeded, "__annotations__", annotations)

    def dataclass_default_changed(patch):
        field = Budget.__dataclass_fields__["max_seconds"]
        patch.setattr(field, "default", 30.0)

    def dataclass_no_longer_hashable(patch):
        patch.setattr(symq.Gate, "__hash__", None)

    def constant_value_changed(patch):
        patch.setattr(symq.generators, "MUTATIONS", symq.generators.MUTATIONS[:-1])

    def policy_removed(patch):
        patch.setattr(symq, "POLICIES", symq.POLICIES[:-1])

    def engine_alias_removed(patch):
        patch.delitem(cli._ENGINES, "python")

    def json_key_dropped(patch):
        patch.setattr(cli, "_CHECK_JSON_KEYS", cli._CHECK_JSON_KEYS[:-1])

    def text_mode_exit_code_differs(patch):
        real = cli._check

        def check(args):
            code = real(args)
            return code if args.json else 0
        patch.setattr(cli, "_check", check)

    def doctor_failure_code_changed(patch):
        import symq.doctor as doctor_module

        real = doctor_module.doctor
        patch.setattr(doctor_module, "doctor", lambda **kwargs: 4 if real(**kwargs) else 0)

    def version_option_removed(patch):
        real = cli._parser

        def parser():
            built = real()
            built._actions[:] = [action for action in built._actions
                                 if "--version" not in action.option_strings]
            return built
        patch.setattr(cli, "_parser", parser)

    def anf_term_type_changed(patch):
        real = cli._print_json

        def print_json(value):
            if value.get("kind") == "symq_anf" and "outputs" in value:
                value = {**value, "outputs": {wire: [str(term) for term in terms]
                                              for wire, terms in value["outputs"].items()}}
            real(value)
        patch.setattr(cli, "_print_json", print_json)

    return [function_default, method_removed, operator_removed, property_became_method,
            abstract_method_made_concrete, protocol_no_longer_runtime_checkable,
            declared_attribute_removed, dataclass_default_changed, dataclass_no_longer_hashable,
            constant_value_changed, policy_removed, engine_alias_removed, json_key_dropped,
            text_mode_exit_code_differs, doctor_failure_code_changed, version_option_removed,
            anf_term_type_changed]


@pytest.mark.parametrize("mutate", _live_mutations(), ids=lambda mutate: mutate.__name__)
def test_a_change_to_the_live_package_is_seen(mutate, monkeypatch):
    """The power check that matters: change the package, rebuild the record, expect a difference.

    The mutations of the stored JSON above only show that the comparison compares.
    """
    recorded = load()
    assert not _compare(recorded, build(recorded))
    mutate(monkeypatch)
    assert _compare(recorded, build(recorded)), f"{mutate.__name__} went unnoticed"


def test_an_environment_that_cannot_observe_a_part_needs_the_record(monkeypatch):
    """Without the capability and without a record the tool refuses instead of guessing."""
    monkeypatch.setattr(api_snapshot, "_capabilities", lambda: {"native": False, "sat": False})
    with pytest.raises(api_snapshot.Incomplete):
        api_snapshot._cli(None)
    recorded = load()
    assert api_snapshot._cli(recorded) == recorded["cli"]
    assert api_snapshot.writable() is not None


def test_an_incomplete_environment_trusts_the_record_for_skipped_scenarios_only(monkeypatch):
    """Whatever does run there is compared exactly: a renamed or dropped key is still seen."""
    import symq.__main__ as cli

    monkeypatch.setattr(api_snapshot, "_capabilities", lambda: {"native": False, "sat": False})
    real = cli._print_json

    def print_json(value):
        if value.get("kind") == "symq_anf" and "width" in value:
            value = {key if key != "width" else "breadth": item for key, item in value.items()}
        real(value)

    monkeypatch.setattr(cli, "_print_json", print_json)
    recorded = load()
    found = list(differences(recorded["cli"]["json"], api_snapshot._cli(recorded)["json"]))
    assert found == ["added: anf: success.breadth", "removed: anf: success.width"]


def test_writing_is_refused_outside_the_reference_environment(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(api_snapshot, "SNAPSHOT", tmp_path / "snapshot.json")
    monkeypatch.setattr(api_snapshot, "REFERENCE", tmp_path / "reference.md")
    monkeypatch.setattr(api_snapshot, "writable", lambda: "not here")
    assert api_snapshot.main(["--write"]) == 2
    assert "not here" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_the_record_must_describe_this_checkout(monkeypatch):
    """An editable install of another checkout would otherwise be recorded as this one."""
    import symq

    if sys.version_info[:2] != REFERENCE_PYTHON:
        pytest.skip("the version check comes first on other interpreters")
    monkeypatch.setattr(api_snapshot, "_capabilities", lambda: {"native": True, "sat": True})
    monkeypatch.setattr(symq, "__file__", "/somewhere/else/symq/__init__.py")
    assert "imported from" in api_snapshot.writable()
