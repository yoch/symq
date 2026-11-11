"""The advice printed for a missing native core fits the installation that prints it.

``python tools/build_native.py`` exists in a source checkout only. A user who installed a wheel
has no such file, and on Windows the core cannot be built at all.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

import symq._native_hint as hint_module
from symq._native_hint import REBUILD_FROM_SDIST, in_source_checkout, native_core_hint
from tests.conftest import ROOT


def test_a_source_checkout_is_told_to_use_the_build_tool(monkeypatch):
    monkeypatch.setattr(hint_module, "in_source_checkout", lambda: True)
    monkeypatch.setattr(hint_module.sys, "platform", "linux")
    assert "python tools/build_native.py" in native_core_hint()
    assert "pip install" not in native_core_hint()


def test_an_installed_package_is_never_sent_to_a_file_it_does_not_have(monkeypatch):
    monkeypatch.setattr(hint_module, "in_source_checkout", lambda: False)
    monkeypatch.setattr(hint_module.sys, "platform", "linux")
    hint = native_core_hint()
    assert "tools/build_native.py" not in hint
    assert REBUILD_FROM_SDIST in hint
    # The rebuild must fail loudly rather than fall back to pure Python again.
    assert "SYMQ_REQUIRE_NATIVE=1" in REBUILD_FROM_SDIST and "--no-binary symq" in REBUILD_FROM_SDIST


@pytest.mark.parametrize("checkout", [True, False])
def test_windows_is_told_the_core_does_not_exist_there(monkeypatch, checkout):
    monkeypatch.setattr(hint_module, "in_source_checkout", lambda: checkout)
    monkeypatch.setattr(hint_module.sys, "platform", "win32")
    hint = native_core_hint()
    assert "not available on Windows" in hint
    assert "build_native" not in hint and "pip install" not in hint


def test_the_checkout_probe_sees_this_installation_as_it_is():
    """True from the repository, false for an installed wheel (which ships neither file)."""
    package = Path(hint_module.__file__).resolve().parent
    expected = package == ROOT / "src" / "symq"
    assert in_source_checkout() == expected
    if not expected:
        assert not (package / "backends" / "_zdd.c").exists()


def test_doctor_gives_the_advice_once(monkeypatch):
    import symq.doctor as module

    monkeypatch.setattr(module, "has_native", lambda: False)
    hint = native_core_hint()
    monkeypatch.setattr(module, "NATIVE_IMPORT_ERROR", f"extension not installed; or: {hint}")
    buf = io.StringIO()
    module.doctor(stream=buf)
    assert buf.getvalue().count(hint) == 1  # in the reason; no second "Hint:" line
    monkeypatch.setattr(module, "NATIVE_IMPORT_ERROR", "undefined symbol: PyFoo")
    buf = io.StringIO()
    module.doctor(stream=buf)
    assert f"Hint: {hint}." in buf.getvalue()


def test_doctor_reports_the_sat_engine(monkeypatch):
    import symq.doctor as module
    import symq.sat

    buf = io.StringIO()
    module.doctor(stream=buf)
    text = buf.getvalue()
    assert "SAT engine (symq.sat):" in text
    if symq.sat.available():
        assert "[OK] Status: AVAILABLE (python-sat " in text
    monkeypatch.setattr(symq.sat, "available", lambda: False)
    buf = io.StringIO()
    assert module.doctor(stream=buf) == 0  # optional, like the native core
    assert "NOT INSTALLED" in buf.getvalue() and "pip install 'symq[sat]'" in buf.getvalue()
