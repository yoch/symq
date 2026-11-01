"""Tests for the symq doctor command and environment diagnosis."""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from symq.__main__ import main
from symq.backends import has_native
from symq.doctor import doctor

SRC = Path(__file__).resolve().parents[1] / "src"


def test_doctor_output():
    buf = io.StringIO()
    code = doctor(stream=buf)
    assert code == 0, "a missing optional native core is not an error"
    output = buf.getvalue()
    assert "symq doctor:" in output
    assert "Environment:" in output
    assert "Native ZDD Core (zdd-native, zdd-native-wide):" in output
    assert ("AVAILABLE (loaded from" in output) == has_native()
    assert "Registered Backends" in output
    assert "External Baselines" in output


def test_doctor_cli(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    assert main(["doctor"]) == 0
    assert "symq doctor:" in buf.getvalue()
    assert main(["doctor", "--require-native"]) == (0 if has_native() else 1)
    with pytest.raises(SystemExit):
        main(["--frobnicate"])


def test_package_imports_outside_the_source_tree(tmp_path):
    """The wheel ships only ``src/symq``: importing symq must not need ``tools/``."""
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    done = subprocess.run(
        [sys.executable, "-c", "import symq, symq.doctor; print(symq.__file__)"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stderr


def test_require_native_reports_why_the_core_is_missing(monkeypatch):
    import symq.doctor as module

    monkeypatch.setattr(module, "has_native", lambda: False)
    monkeypatch.setattr(module, "NATIVE_IMPORT_ERROR", "stale native core (ABI 4, expected 5)")
    buf = io.StringIO()
    assert module.doctor(stream=buf, require_native=True) == 1
    assert "[ERROR] Status: NOT AVAILABLE" in buf.getvalue()
    assert "Reason: stale native core (ABI 4, expected 5)" in buf.getvalue()
    buf = io.StringIO()
    assert module.doctor(stream=buf) == 0
    assert "[INFO] Status: NOT AVAILABLE" in buf.getvalue()


def test_wide_native_backend_is_labelled_native():
    buf = io.StringIO()
    doctor(stream=buf)
    if has_native():
        assert "zdd-native-wide   [native C core]" in buf.getvalue()


def test_doctor_json_identifies_the_build(capsys):
    import json

    assert main(["doctor", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["kind"] == "symq_doctor" and data["schema_version"] == 1
    assert len(data["source_sha256"]) == 64 and "__init__.py" in data["sources"]
    # The C source ships in the sdist and a checkout, not in the wheel.
    import symq

    if (Path(symq.__file__).parent / "backends" / "_zdd.c").exists():
        assert "backends/_zdd.c" in data["sources"]
    assert data["native"]["available"] == has_native()
    if has_native():
        assert data["native"]["abi"] == 6 and len(data["native"]["sha256"]) == 64
    assert "linear" in data["backends"]
