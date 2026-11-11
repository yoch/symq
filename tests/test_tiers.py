"""Every test carries exactly one tier marker, derived from the imports of its module."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import ROOT, TIERS, module_tier

TESTS = ROOT / "tests"


def test_this_test_is_in_the_core_tier(request):
    tiers = [name for name in TIERS if request.node.get_closest_marker(name)]
    assert tiers == ["core"]


@pytest.mark.parametrize("name, tier", [
    ("test_circuit.py", "core"),                     # imports symq only
    ("test_ci_workflow.py", "core"),                 # imports no symq module at all
    ("test_experimental_api.py", "experimental"),    # symq.experimental, no labs
    ("test_contextual_substitution.py", "labs"),     # a direct symq.labs import
])
def test_known_modules_are_classified(name, tier):
    assert module_tier(TESTS / name) == tier


def test_the_tier_follows_repository_local_imports(tmp_path, monkeypatch):
    """A test that reaches labs only through a helper of this repository is a labs test."""
    from tests import conftest

    package = tmp_path / "tests"
    package.mkdir()
    (package / "helper.py").write_text("def f():\n    from symq.labs import rewrite\n")
    (package / "relative.py").write_text("from . import helper\n")
    (package / "absolute.py").write_text("import tests.helper\n")
    (package / "plain.py").write_text("import symq\nfrom symq.sat import Contract\n")
    (package / "opt_in.py").write_text("from symq import experimental\n")
    monkeypatch.setattr(conftest, "ROOT", tmp_path)
    module_tier.cache_clear()
    conftest._imported_modules.cache_clear()
    try:
        assert module_tier(package / "relative.py") == "labs"
        assert module_tier(package / "absolute.py") == "labs"
        assert module_tier(package / "plain.py") == "core"
        assert module_tier(package / "opt_in.py") == "experimental"
        assert module_tier(tmp_path / "notes.md") == "core"  # not Python source
    finally:
        module_tier.cache_clear()
        conftest._imported_modules.cache_clear()


def test_the_three_tiers_are_all_populated():
    """A tier that selected no test at all would make ``-m <tier>`` silently run nothing."""
    tiers = {path.name: module_tier(path) for path in sorted(Path(TESTS).glob("test_*.py"))}
    assert set(tiers.values()) == set(TIERS)


def test_a_test_outside_the_repository_does_not_break_collection(tmp_path):
    """``pytest tests/x.py /elsewhere/test_y.py`` collects both; the hook sees every item."""
    outside = tmp_path / "test_elsewhere.py"
    outside.write_text("from symq.labs import rewrite\n")
    assert module_tier(outside) == "core"
