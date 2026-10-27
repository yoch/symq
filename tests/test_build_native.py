"""Tests for the native build toolchain, compiler diagnostics, and mandatory native mode."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import symq
from symq.backends import BACKENDS, has_native, make_algebra
from tools.build_native import (
    BuildDiagnosis,
    build_extension,
    diagnose_build,
    find_python_include,
    get_compiler_candidates,
    is_native_required,
    main,
    probe_compiler,
)

ROOT = Path(__file__).resolve().parents[1]


def test_is_native_required(monkeypatch):
    monkeypatch.delenv("SYMQ_REQUIRE_NATIVE", raising=False)
    monkeypatch.delenv("SYMQ_STRICT_NATIVE", raising=False)
    monkeypatch.delenv("SYMQ_NATIVE_REQUIRED", raising=False)
    assert is_native_required() is False

    for var in ("SYMQ_REQUIRE_NATIVE", "SYMQ_STRICT_NATIVE", "SYMQ_NATIVE_REQUIRED"):
        for val in ("1", "true", "True", "YES", "on", "strict"):
            monkeypatch.setenv(var, val)
            assert is_native_required() is True
            monkeypatch.delenv(var)

    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "0")
    assert is_native_required() is False
    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "false")
    assert is_native_required() is False


def test_get_compiler_candidates_priority(monkeypatch):
    monkeypatch.delenv("CC", raising=False)
    candidates = get_compiler_candidates(explicit="my-custom-cc")
    assert candidates[0] == ("my-custom-cc", "explicit parameter / CLI argument")

    monkeypatch.setenv("CC", "clang-custom")
    candidates_with_env = get_compiler_candidates()
    assert candidates_with_env[0] == ("clang-custom", "environment variable CC")

    # Fallbacks cc, gcc, clang must be present
    fb_names = [cmd for cmd, origin in candidates_with_env if origin.startswith("system fallback")]
    assert fb_names == ["cc", "gcc", "clang"]


def test_fallback_selected_when_sysconfig_compiler_is_absent(monkeypatch):
    """When Python's sysconfig CC is missing, an available fallback must be selected."""
    monkeypatch.delenv("CC", raising=False)
    with patch("sysconfig.get_config_var", return_value="nonexistent-compiler-xyz-12345"):
        diag = diagnose_build(ROOT)
        # Should NOT fail on missing compiler if a fallback (cc, gcc, or clang) exists on the machine
        if any(c.resolved_path for c in diag.candidates_checked if c.origin.startswith("system fallback")):
            assert diag.chosen_compiler is not None
            assert diag.chosen_compiler.origin.startswith("system fallback")
            # The absent sysconfig compiler must be documented in candidates
            sysconfig_cand = next(
                c for c in diag.candidates_checked if c.origin == "Python sysconfig CC"
            )
            assert sysconfig_cand.resolved_path is None
            assert "not found in PATH" in (sysconfig_cand.error or "")


def test_diagnose_build_output_structure():
    diag = diagnose_build(ROOT)
    formatted = diag.format(detailed=True)
    assert "Native ZDD C Extension Diagnostics:" in formatted
    assert "Source:" in formatted
    assert "Target:" in formatted
    assert "Compiler detection:" in formatted
    assert "Python headers:" in formatted
    assert "Candidates considered:" in formatted


def test_find_python_include():
    chosen, checked = find_python_include()
    assert len(checked) > 0
    # In standard dev environment, Python.h is found
    if chosen is not None:
        assert (chosen / "Python.h").is_file()


def test_build_extension_strict_failure_on_missing_compiler():
    """Mandatory native mode must raise RuntimeError with diagnostics when compiler is missing."""
    with pytest.raises(RuntimeError, match="Native core build required but prerequisites missing"):
        build_extension(ROOT, require=True, compiler="definitely-nonexistent-compiler-symq-test")


def test_build_extension_optional_returns_none_on_missing_compiler():
    """Optional mode must return None without raising when compiler is missing."""
    result = build_extension(
        ROOT, quiet=True, require=False, compiler="definitely-nonexistent-compiler-symq-test"
    )
    assert result is None


def test_build_extension_compilation_failure_in_strict_mode(tmp_path):
    """A failing compiler invocation must raise RuntimeError with compiler stderr."""
    failing_script = tmp_path / "fake_cc.sh"
    failing_script.write_text("#!/bin/sh\necho 'simulated syntax error' >&2\nexit 1\n")
    failing_script.chmod(0o755)

    with pytest.raises(RuntimeError, match="Native core compilation failed"):
        build_extension(ROOT, require=True, compiler=str(failing_script))


def test_cli_diagnose_exit_codes():
    ret = main(["--root", str(ROOT), "--diagnose"])
    # If a compiler is present on this machine, diagnose exits 0
    diag = diagnose_build(ROOT)
    if diag.error_message is None:
        assert ret == 0


def test_cli_strict_failure_exit_code():
    ret = main(
        [
            "--root",
            str(ROOT),
            "--compiler",
            "definitely-nonexistent-compiler-symq-test",
            "--require",
        ]
    )
    assert ret == 1


def test_cli_optional_exit_code():
    ret = main(
        [
            "--root",
            str(ROOT),
            "--compiler",
            "definitely-nonexistent-compiler-symq-test",
            "--optional",
            "--quiet",
        ]
    )
    assert ret == 0


def test_hatch_build_hook_respects_skip(monkeypatch):
    from hatch_build import BuildHook

    hook = BuildHook(None, str(ROOT), {}, "", "", "")
    monkeypatch.setenv("SYMQ_SKIP_NATIVE", "1")
    build_data = {}
    hook.initialize("0.1.0", build_data)
    assert "artifacts" not in build_data
    assert "pure_python" not in build_data


def test_hatch_build_hook_strict_failure(monkeypatch):
    from hatch_build import BuildHook

    hook = BuildHook(None, str(ROOT), {}, "", "", "")
    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "1")
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Native core build required"):
            hook.initialize("0.1.0", {})


def test_make_algebra_unbuilt_native_backend_message():
    """Requesting zdd-native when unbuilt must give an actionable diagnostic."""
    with patch.dict(BACKENDS, {}, clear=False):
        # Temporarily remove zdd-native to simulate unbuilt native core
        if "zdd-native" in BACKENDS:
            del BACKENDS["zdd-native"]
        with pytest.raises(ValueError) as excinfo:
            make_algebra("zdd-native", 4)
        msg = str(excinfo.value)
        assert msg.startswith("unknown backend 'zdd-native'")
        assert "native C extension was not built" in msg
        assert "tools/build_native.py" in msg


def test_has_native_matches_backends():
    assert has_native() == ("zdd-native" in BACKENDS)
    assert symq.has_native() == has_native()
