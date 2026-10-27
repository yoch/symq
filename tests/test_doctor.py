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
    assert code == (0 if has_native() else 1)
    output = buf.getvalue()
    assert "symq doctor:" in output
    assert "Environment:" in output
    assert "Native ZDD Core (zdd-native):" in output
    assert ("AVAILABLE (loaded from" in output) == has_native()
    assert "Registered Backends" in output
    assert "External Baselines" in output


def test_doctor_cli(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    assert main(["doctor"]) == (0 if has_native() else 1)
    assert "symq doctor:" in buf.getvalue()
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
