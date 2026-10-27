"""Tests for the symq doctor command and environment diagnosis."""
from __future__ import annotations

import io

from symq.doctor import doctor


def test_doctor_output():
    buf = io.StringIO()
    code = doctor(stream=buf)
    assert code == 0
    output = buf.getvalue()
    assert "symq doctor:" in output
    assert "Environment:" in output
    assert "Native ZDD Core (zdd-native):" in output
    assert "Registered Backends" in output
    assert "External Baselines" in output


def test_doctor_cli(monkeypatch):
    from symq.__main__ import main

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    code = main()
    assert code == 0
    assert "symq doctor:" in buf.getvalue()
