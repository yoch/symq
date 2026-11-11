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
    names_only,
    reference_text,
)

ON_REFERENCE_PYTHON = sys.version_info[:2] == REFERENCE_PYTHON
HOW_TO = ("the public API differs from tests/data/api_snapshot.json; if the change is intended, "
          "run 'python tools/api_snapshot.py --write' and add a CHANGELOG line:\n")


def _compare(expected, actual):
    if not ON_REFERENCE_PYTHON:  # the text of a signature may be rendered differently
        expected, actual = names_only(expected), names_only(actual)
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
@pytest.mark.skipif(not ON_REFERENCE_PYTHON, reason="the reference is rendered with CPython 3.12")
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


def test_the_policy_page_lists_exactly_the_provisional_names():
    """``docs/stability.md`` is what users read; it must not drift from the table that is tested."""
    page = (ROOT / "docs" / "stability.md").read_text(encoding="utf-8")
    section = page.split("### Provisional names", 1)[1].split("Three finer points", 1)[0]
    listed = set(re.findall(r"`(symq[\w.]*)`", section))
    assert listed == set(PROVISIONAL)
    values = load()["values"]
    finer = page.split("Three finer points", 1)[1].split("## What a release may change", 1)[0]
    backends, _, theorems = finer.partition("**Theorems.**")
    for tier, names in values["backends"].items():
        for name in names:
            assert f"`{name}`" in backends, f"backend {name} ({tier}) is not in the policy page"
    for tier in ("stable", "provisional"):
        for name in values["theorems"][tier]:
            assert f"`{name}`" in theorems, f"theorem {name} ({tier}) is not in the policy page"


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
    assert set(load()["cli"]["json"]["check"]) == {*_CHECK_JSON_KEYS, "schema_version", "kind"}


def test_every_command_states_its_tier_in_its_help():
    from symq.__main__ import COMMAND_TIERS, _parser

    usage = _parser().format_help()
    assert {tier for tier in COMMAND_TIERS.values()} == {"stable", "experimental", "labs"}
    assert sorted(load()["cli"]["commands"]) == sorted(
        name for name, tier in COMMAND_TIERS.items() if tier == "stable")
    for name, tier in COMMAND_TIERS.items():
        line = next(line for line in usage.splitlines() if line.strip().startswith(f"{name} "))
        marker = {"stable": None, "experimental": "[experimental]",
                  "labs": "[labs, no API promise]"}[tier]
        if marker is None:
            assert "[" not in line
        else:
            assert marker in " ".join(line.split())


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
        del snapshot["cli"]["json"]["check"]["witness"]

    def retype_json_key(snapshot):
        snapshot["cli"]["json"]["anf"]["width"] = ["string"]

    def drop_argument(snapshot):
        snapshot["cli"]["commands"]["check"].pop()

    def move_backend(snapshot):
        snapshot["values"]["backends"]["stable"].remove("zdd")

    return [remove_name, add_name, change_signature, change_tier, drop_field, drop_method,
            change_base, change_exit_code, drop_json_key, retype_json_key, drop_argument,
            move_backend]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda mutate: mutate.__name__)
def test_a_change_to_the_surface_is_reported(mutate):
    recorded = load()
    changed = copy.deepcopy(recorded)
    mutate(changed)
    assert list(differences(recorded, changed)), f"{mutate.__name__} went unnoticed"
    assert not list(differences(recorded, copy.deepcopy(recorded)))


def test_the_comparison_by_name_ignores_only_the_text_of_signatures():
    recorded = load()
    changed = copy.deepcopy(recorded)
    changed["packages"]["symq"]["check_equivalence"]["signature"] += " # other rendering"
    changed["packages"]["symq"]["Budget"]["dataclass"]["fields"][0]["annotation"] = "Optional[int]"
    assert not list(differences(names_only(recorded), names_only(changed)))
    del changed["packages"]["symq"]["Circuit"]["members"]["run"]
    assert list(differences(names_only(recorded), names_only(changed)))


def test_an_environment_that_cannot_observe_a_part_needs_the_record(monkeypatch):
    """Without the capability and without a record the tool refuses instead of guessing."""
    monkeypatch.setattr(api_snapshot, "_capabilities", lambda: {"native": False, "sat": False})
    with pytest.raises(api_snapshot.Incomplete):
        api_snapshot._cli(None)
    recorded = load()
    assert api_snapshot._cli(recorded)["json"] == recorded["cli"]["json"]
    assert api_snapshot.writable() is not None


def test_writing_is_refused_outside_the_reference_environment(monkeypatch, capsys):
    monkeypatch.setattr(api_snapshot, "writable", lambda: "not here")
    before = api_snapshot.SNAPSHOT.read_bytes()
    assert api_snapshot.main(["--write"]) == 2
    assert "not here" in capsys.readouterr().err
    assert api_snapshot.SNAPSHOT.read_bytes() == before
