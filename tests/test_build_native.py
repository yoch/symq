"""Tests for the native build toolchain, compiler diagnostics, and mandatory native mode."""
from __future__ import annotations

import sysconfig
from pathlib import Path
from unittest.mock import patch

import pytest

import symq
from symq.backends import BACKENDS, has_native, make_algebra
from tools.build_native import (
    build_extension,
    diagnose_build,
    find_python_include,
    get_compiler_candidates,
    is_native_required,
    main,
    native_mode,
)

ROOT = Path(__file__).resolve().parents[1]


def test_is_native_required(monkeypatch):
    monkeypatch.delenv("SYMQ_REQUIRE_NATIVE", raising=False)
    assert is_native_required() is False

    for val in ("1", "true", "True", "YES", "on"):
        monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", val)
        assert is_native_required() is True

    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "0")
    assert is_native_required() is False
    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "false")
    assert is_native_required() is False


def test_native_mode(monkeypatch):
    monkeypatch.delenv("SYMQ_REQUIRE_NATIVE", raising=False)
    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
    assert native_mode() == "optional"
    monkeypatch.setenv("SYMQ_SKIP_NATIVE", "0")
    assert native_mode() == "optional"
    monkeypatch.setenv("SYMQ_SKIP_NATIVE", "1")
    assert native_mode() == "skip"
    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "1")
    with pytest.raises(ValueError, match="mutually exclusive"):
        native_mode()
    monkeypatch.delenv("SYMQ_SKIP_NATIVE")
    assert native_mode() == "require"


def test_unusable_cc_falls_back_with_warning_and_fails_when_required(monkeypatch):
    monkeypatch.setenv("CC", "/nonexistent/symq-test-cc")
    diag = diagnose_build(ROOT)
    assert any("$CC" in warning for warning in diag.warnings)
    if diag.chosen_compiler is not None:
        assert diag.chosen_compiler.origin != "environment variable CC"
    with pytest.raises(RuntimeError, match="CC"):
        build_extension(ROOT, quiet=True, require=True)


def test_malformed_compiler_and_flags_do_not_crash(monkeypatch):
    assert build_extension(ROOT, quiet=True, require=False, compiler="'unclosed") is None
    monkeypatch.setenv("CFLAGS", "'unclosed")
    assert build_extension(ROOT, quiet=True, require=False) is None
    with pytest.raises(RuntimeError, match="CFLAGS"):
        build_extension(ROOT, quiet=True, require=True)


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


def _pretend_free_threaded(monkeypatch):
    real = sysconfig.get_config_var
    monkeypatch.setattr(sysconfig, "get_config_var",
                        lambda name: 1 if name == "Py_GIL_DISABLED" else real(name))


def test_a_free_threaded_interpreter_gets_no_native_core(monkeypatch, capsys):
    """Optional mode: no compilation, a clear reason, and the pure-Python install goes on."""
    from tools import build_native

    assert build_native.free_threaded() is bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
    _pretend_free_threaded(monkeypatch)
    assert build_native.free_threaded() is True
    diag = diagnose_build(ROOT)
    assert diag.error_message == build_native.FREE_THREADED_MESSAGE
    with patch("tools.build_native.subprocess.run") as run:
        assert build_extension(ROOT, quiet=False, require=False) is None
    assert not any("-shared" in str(call) for call in run.call_args_list)  # never compiled
    assert "free-threaded" in capsys.readouterr().err


def test_a_free_threaded_interpreter_fails_a_required_native_build(monkeypatch):
    _pretend_free_threaded(monkeypatch)
    with pytest.raises(RuntimeError, match="free-threaded"):
        build_extension(ROOT, quiet=True, require=True)


def test_the_c_source_refuses_a_free_threaded_build_by_itself():
    """A build path that bypasses the script must not produce the module either."""
    source = (ROOT / "src" / "symq" / "backends" / "_zdd.c").read_text(encoding="utf-8")
    guard = source.index("#ifdef Py_GIL_DISABLED")
    assert source.index("#include <Python.h>") < guard < source.index("typedef struct")
    assert source[guard:].startswith("#ifdef Py_GIL_DISABLED\n#error ")


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
    diag = diagnose_build(ROOT)
    assert ret == (0 if diag.error_message is None else 1)
    missing = ["--root", str(ROOT), "--compiler", "definitely-nonexistent-compiler-symq-test"]
    assert main([*missing, "--diagnose"]) == 1
    assert main([*missing, "--diagnose", "--optional"]) == 0


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


def test_cli_optional_exit_code(monkeypatch):
    # A caller's mandatory-native policy must not leak into the optional-mode
    # unit test. The CLI intentionally gives SYMQ_REQUIRE_NATIVE precedence.
    monkeypatch.delenv("SYMQ_REQUIRE_NATIVE", raising=False)
    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
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


def test_cli_mandatory_env_overrides_optional_flag(monkeypatch):
    # Document the existing CLI precedence rather than weakening the native
    # requirement in production merely to make a test pass.
    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "1")
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
    assert ret == 1


def _build_hook():
    pytest.importorskip("hatchling")
    hatch_build = pytest.importorskip("hatch_build")
    return hatch_build.BuildHook(str(ROOT), {}, None, None, str(ROOT), "wheel")


def test_hatch_build_hook_respects_skip(monkeypatch):
    hook = _build_hook()
    monkeypatch.delenv("SYMQ_REQUIRE_NATIVE", raising=False)
    monkeypatch.setenv("SYMQ_SKIP_NATIVE", "1")
    build_data = {}
    hook.initialize("0.1.0", build_data)
    assert "artifacts" not in build_data
    assert "pure_python" not in build_data


def test_hatch_build_hook_strict_failure(monkeypatch):
    hook = _build_hook()
    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
    monkeypatch.setenv("SYMQ_REQUIRE_NATIVE", "1")
    with patch("shutil.which", return_value=None), pytest.raises(
        RuntimeError, match="Native core build required"
    ):
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
        assert "native C extension is not installed" in msg
        from symq._native_hint import native_core_hint

        assert native_core_hint() in msg  # advice for this installation, not a fixed path


def test_has_native_matches_backends():
    assert has_native() == ("zdd-native" in BACKENDS)
    assert symq.has_native() == has_native()


# ---- macOS target architecture (ARCHFLAGS) ----

def test_archflags_are_read_on_macos_only(monkeypatch):
    import tools.build_native as module

    monkeypatch.setenv("ARCHFLAGS", "-arch x86_64")
    monkeypatch.setattr(module.sys, "platform", "darwin")
    assert module.architecture_flags() == ["-arch", "x86_64"]
    monkeypatch.setattr(module.sys, "platform", "linux")
    assert module.architecture_flags() == []
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.delenv("ARCHFLAGS")
    assert module.architecture_flags() == []


def _compile_command(monkeypatch, tmp_path, platform):
    """The compiler command ``build_extension`` would run on ``platform``, without running it."""
    import subprocess

    import tools.build_native as module

    real = subprocess.run
    captured = []

    def run(command, *args, **kwargs):
        if "-shared" in command:
            captured.append(list(command))
            return subprocess.CompletedProcess(command, 0, "", "")
        return real(command, *args, **kwargs)

    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
    monkeypatch.setattr(module.sys, "platform", platform)
    monkeypatch.setattr(module.subprocess, "run", run)
    root = tmp_path / "root"
    (root / "src" / "symq" / "backends").mkdir(parents=True)
    (root / "src" / "symq" / "backends" / "_zdd.c").write_text("/* not compiled */\n")
    assert module.build_extension(root, quiet=True, require=True) is not None
    assert len(captured) == 1
    return captured[0]


def test_the_macos_build_targets_the_requested_architecture(monkeypatch, tmp_path):
    """A wheel builder asks for an architecture with ARCHFLAGS; ignoring it would build for the
    host and label the wheel for the target: it installs, then fails to import."""
    monkeypatch.setenv("ARCHFLAGS", "-arch x86_64")
    command = _compile_command(monkeypatch, tmp_path, "darwin")
    assert command[command.index("-arch") + 1] == "x86_64"
    assert command.index("-arch") < command.index("-o")
    assert "dynamic_lookup" in command


def test_archflags_do_not_reach_the_compiler_elsewhere(monkeypatch, tmp_path):
    monkeypatch.setenv("ARCHFLAGS", "-arch x86_64")
    assert "-arch" not in _compile_command(monkeypatch, tmp_path, "linux")


def test_unparsable_archflags_fail_a_required_build(monkeypatch, tmp_path):
    import tools.build_native as module

    monkeypatch.delenv("SYMQ_SKIP_NATIVE", raising=False)
    monkeypatch.setenv("ARCHFLAGS", "-arch 'x86_64")
    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(RuntimeError, match="ARCHFLAGS"):
        module.build_extension(ROOT, quiet=True, require=True)
