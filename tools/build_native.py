"""Compile ``src/symq/backends/_zdd.c`` in place with the platform C compiler.

Used by the hatch build hook and as a standalone CLI tool.
Supports mandatory native mode (SYMQ_REQUIRE_NATIVE=1 or --require) and provides
detailed diagnostics of compiler detection, Python headers, and compilation results.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

NAME = "symq.backends._zdd"


def is_native_required() -> bool:
    """Return True if native extension compilation is explicitly marked mandatory."""
    for var in ("SYMQ_REQUIRE_NATIVE", "SYMQ_STRICT_NATIVE", "SYMQ_NATIVE_REQUIRED"):
        val = os.environ.get(var, "").strip().lower()
        if val in ("1", "true", "yes", "on", "strict"):
            return True
    return False


def source(root: Path | str) -> Path:
    return Path(root) / "src" / "symq" / "backends" / "_zdd.c"


def target(root: Path | str) -> Path:
    suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
    return Path(root) / "src" / "symq" / "backends" / f"_zdd{suffix}"


@dataclass
class CompilerCandidate:
    raw_command: str
    origin: str
    binary: str
    extra_flags: list[str]
    resolved_path: Path | None = None
    version: str | None = None
    error: str | None = None


@dataclass
class BuildDiagnosis:
    source_path: Path
    target_path: Path
    candidates_checked: list[CompilerCandidate] = field(default_factory=list)
    chosen_compiler: CompilerCandidate | None = None
    include_paths_checked: list[tuple[Path, bool]] = field(default_factory=list)
    chosen_include: Path | None = None
    command_executed: list[str] | None = None
    returncode: int | None = None
    build_stdout: str = ""
    build_stderr: str = ""
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.target_path.exists() and self.returncode == 0

    def format(self, detailed: bool = True) -> str:
        lines: list[str] = []
        lines.append("Native ZDD C Extension Diagnostics:")
        lines.append(f"  Source: {self.source_path}")
        lines.append(f"  Target: {self.target_path}")

        lines.append("  Compiler detection:")
        if self.chosen_compiler:
            lines.append(
                f"    [OK] Selected: {self.chosen_compiler.resolved_path} "
                f"({self.chosen_compiler.origin})"
            )
            if self.chosen_compiler.version:
                lines.append(f"         Version:  {self.chosen_compiler.version}")
        else:
            lines.append("    [FAILED] No usable C compiler found in PATH.")

        if detailed and self.candidates_checked:
            lines.append("    Candidates considered:")
            for c in self.candidates_checked:
                status = (
                    f"found at {c.resolved_path}"
                    if c.resolved_path
                    else (c.error or "not found in PATH")
                )
                lines.append(f"      - '{c.raw_command}' ({c.origin}) -> {status}")

        lines.append("  Python headers:")
        if self.chosen_include:
            lines.append(f"    [OK] Python.h found in: {self.chosen_include}")
        else:
            lines.append("    [FAILED] Python.h not found.")
            if detailed and self.include_paths_checked:
                lines.append("    Include directories checked:")
                for inc_path, exists in self.include_paths_checked:
                    lines.append(f"      - {inc_path} -> {'found' if exists else 'missing'}")

        if self.command_executed:
            lines.append(
                f"  Compile command: {' '.join(shlex.quote(arg) for arg in self.command_executed)}"
            )
            lines.append(f"  Exit code: {self.returncode}")

        if self.build_stderr:
            lines.append("  Compiler stderr:")
            for err_line in self.build_stderr.strip().splitlines()[-20:]:
                lines.append(f"    {err_line}")

        if self.error_message:
            lines.append(f"  Status: ERROR: {self.error_message}")
        elif self.success:
            lines.append("  Status: SUCCESS")
        else:
            lines.append("  Status: NOT BUILT")

        return "\n".join(lines)


def get_compiler_candidates(explicit: str | None = None) -> list[tuple[str, str]]:
    """Return list of (command_string, origin_description) to probe in priority order.

    If an explicit compiler is requested, only that candidate is probed.
    Otherwise, probes $CC, sysconfig CC, and standard fallbacks (cc, gcc, clang).
    """
    if explicit and explicit.strip():
        return [(explicit.strip(), "explicit parameter / CLI argument")]

    candidates: list[tuple[str, str]] = []
    env_cc = os.environ.get("CC")
    if env_cc and env_cc.strip():
        candidates.append((env_cc.strip(), "environment variable CC"))
    sys_cc = sysconfig.get_config_var("CC")
    if sys_cc and sys_cc.strip():
        candidates.append((sys_cc.strip(), "Python sysconfig CC"))
    for fallback in ("cc", "gcc", "clang"):
        candidates.append((fallback, f"system fallback '{fallback}'"))
    return candidates


def probe_compiler(command_str: str, origin: str) -> CompilerCandidate:
    parts = shlex.split(command_str)
    if not parts:
        return CompilerCandidate(command_str, origin, "", [], error="empty command string")
    binary = parts[0]
    extra_flags = parts[1:]
    resolved = shutil.which(binary)
    if not resolved:
        return CompilerCandidate(command_str, origin, binary, extra_flags, error="not found in PATH")
    resolved_path = Path(resolved)
    version: str | None = None
    try:
        res = subprocess.run(
            [str(resolved_path), "--version"], capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            version = res.stdout.strip().splitlines()[0]
    except Exception as exc:
        return CompilerCandidate(
            command_str, origin, binary, extra_flags, resolved_path, error=str(exc)
        )

    if version is None:
        try:
            res = subprocess.run(
                [str(resolved_path), "-v"], capture_output=True, text=True, timeout=5
            )
            output = (res.stderr or res.stdout).strip()
            if output:
                version = output.splitlines()[-1]
        except Exception:
            version = "version unknown"

    return CompilerCandidate(
        raw_command=command_str,
        origin=origin,
        binary=binary,
        extra_flags=extra_flags,
        resolved_path=resolved_path,
        version=version,
    )


def find_python_include() -> tuple[Path | None, list[tuple[Path, bool]]]:
    include_paths: list[Path] = []
    inc = sysconfig.get_paths().get("include")
    if inc:
        include_paths.append(Path(inc))
    inc_py = sysconfig.get_config_var("INCLUDEPY")
    if inc_py and Path(inc_py) not in include_paths:
        include_paths.append(Path(inc_py))
    plat = sysconfig.get_paths().get("platinclude")
    if plat and Path(plat) not in include_paths:
        include_paths.append(Path(plat))

    checked: list[tuple[Path, bool]] = []
    chosen: Path | None = None
    for p in include_paths:
        has_h = (p / "Python.h").is_file()
        checked.append((p, has_h))
        if has_h and chosen is None:
            chosen = p
    return chosen, checked


def diagnose_build(root: Path | str, compiler: str | None = None) -> BuildDiagnosis:
    root = Path(root)
    src = source(root)
    out = target(root)
    diagnosis = BuildDiagnosis(source_path=src, target_path=out)

    candidates = get_compiler_candidates(compiler)
    for cmd_str, origin in candidates:
        candidate = probe_compiler(cmd_str, origin)
        diagnosis.candidates_checked.append(candidate)
        if candidate.resolved_path and candidate.error is None and diagnosis.chosen_compiler is None:
            diagnosis.chosen_compiler = candidate

    chosen_inc, checked_inc = find_python_include()
    diagnosis.chosen_include = chosen_inc
    diagnosis.include_paths_checked = checked_inc

    if not src.is_file():
        diagnosis.error_message = f"C source file missing at {src}"
    elif diagnosis.chosen_compiler is None:
        diagnosis.error_message = (
            "No usable C compiler found in PATH. Candidates probed: "
            + ", ".join(f"'{c.raw_command}' ({c.origin})" for c in diagnosis.candidates_checked)
        )
    elif diagnosis.chosen_include is None:
        diagnosis.error_message = (
            "Python.h header not found. Please install Python development packages "
            "(e.g. 'python3-dev' or 'python3-devel')."
        )
    return diagnosis


def build_extension(
    root: Path | str,
    quiet: bool = False,
    require: bool | None = None,
    compiler: str | None = None,
) -> Path | None:
    """Compile and link in place; ``None`` when impossible (no compiler or no headers).

    When ``require=True`` (or environment variable ``SYMQ_REQUIRE_NATIVE=1`` is active),
    missing prerequisites or compiler errors raise ``RuntimeError`` instead of returning None.
    """
    if require is None:
        require = is_native_required()

    root = Path(root)
    diag = diagnose_build(root, compiler=compiler)
    if diag.error_message:
        if require:
            raise RuntimeError(
                f"Native core build required but prerequisites missing:\n{diag.format()}"
            )
        if not quiet:
            print(diag.format(detailed=False), file=sys.stderr)
        return None

    assert diag.chosen_compiler is not None and diag.chosen_compiler.resolved_path is not None
    assert diag.chosen_include is not None

    output = diag.target_path
    output.parent.mkdir(parents=True, exist_ok=True)

    extra_cflags = shlex.split(os.environ.get("CFLAGS", ""))
    extra_ldflags = shlex.split(os.environ.get("LDFLAGS", ""))

    command = [
        str(diag.chosen_compiler.resolved_path),
        *diag.chosen_compiler.extra_flags,
        "-O3",
        "-std=c11",
        "-fPIC",
        "-shared",
        "-fno-strict-aliasing",
        f"-I{diag.chosen_include}",
        *extra_cflags,
        str(diag.source_path),
        *extra_ldflags,
        "-o",
        str(output),
    ]

    diag.command_executed = command
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    diag.returncode = done.returncode
    diag.build_stdout = done.stdout
    diag.build_stderr = done.stderr

    if done.returncode != 0:
        diag.error_message = f"Compiler exited with return code {done.returncode}"
        if require:
            raise RuntimeError(f"Native core compilation failed:\n{diag.format()}")
        if not quiet:
            print(diag.format(detailed=False), file=sys.stderr)
        return None

    if not quiet:
        print(
            f"[symq] Built native core: {output}\n"
            f"       Compiler: {diag.chosen_compiler.resolved_path} ({diag.chosen_compiler.origin})\n"
            f"       Version:  {diag.chosen_compiler.version}",
            file=sys.stderr,
        )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile the symq native ZDD core in place (_zdd C extension)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root directory (default: symq repository root)",
    )
    parser.add_argument(
        "--require",
        "--strict",
        action="store_true",
        default=None,
        dest="require",
        help="Enforce mandatory native compilation: exit with code 1 on failure.",
    )
    parser.add_argument(
        "--optional",
        "--allow-skip",
        action="store_false",
        dest="require",
        help="Allow compilation to be skipped without error (exit code 0).",
    )
    parser.add_argument(
        "--compiler",
        "-c",
        type=str,
        default=None,
        help="Explicit C compiler command or executable path.",
    )
    parser.add_argument(
        "--diagnose",
        "--check",
        action="store_true",
        help="Inspect toolchain, compiler candidates, and Python headers without compiling.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational output.",
    )

    args = parser.parse_args(argv)

    if args.diagnose:
        diag = diagnose_build(args.root, compiler=args.compiler)
        print(diag.format(detailed=True))
        if diag.error_message:
            return 1 if (args.require is True or (args.require is None and is_native_required())) else 0
        return 0

    strict = True if args.require is None else args.require
    if is_native_required():
        strict = True

    try:
        built = build_extension(
            root=args.root,
            quiet=args.quiet,
            require=strict,
            compiler=args.compiler,
        )
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if built is None:
        if strict:
            return 1
        print("native core not built (skipped)", file=sys.stderr)
        return 0

    print(str(built))
    return 0


if __name__ == "__main__":
    sys.exit(main())
