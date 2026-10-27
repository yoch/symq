"""System diagnostic and environment reporting for symq."""
from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import TextIO

import symq
from symq.backends import BACKENDS, has_native
from tools.build_native import diagnose_build, target


def doctor(stream: TextIO | None = None) -> int:
    """Print an environment diagnosis and toolchain status. Returns 0 if healthy."""
    out = stream if stream is not None else sys.stdout

    lines: list[str] = [
        "symq doctor:",
        "  Environment:",
        f"    - symq version:      {getattr(symq, '__version__', '0.1.0')}",
        f"    - Python version:    {platform.python_version()} ({platform.python_implementation()})",
        f"    - Platform:          {platform.platform()}",
        f"    - Executable:        {sys.executable}",
    ]

    root = Path(__file__).resolve().parents[2]
    build_diag = diagnose_build(root)
    built_target = target(root)
    is_native = has_native()

    lines.append("  Native ZDD Core (zdd-native):")
    if is_native and built_target.exists():
        lines.append(f"    [OK] Status: AVAILABLE (loaded from {built_target})")
        if build_diag.chosen_compiler and build_diag.chosen_compiler.resolved_path:
            lines.append(
                f"    [OK] Compiler toolchain: {build_diag.chosen_compiler.resolved_path} "
                f"({build_diag.chosen_compiler.origin})"
            )
            if build_diag.chosen_compiler.version:
                lines.append(f"         Compiler version:   {build_diag.chosen_compiler.version}")
        lines.append("    [OK] Max native width:   64 wires (uint64_t monomial masks)")
    else:
        lines.append("    [WARN] Status: NOT AVAILABLE (pure-Python mode)")
        lines.append("           Hint: Run 'python tools/build_native.py' to compile the C core.")
        if build_diag.chosen_compiler and build_diag.chosen_compiler.resolved_path:
            lines.append(
                f"           Available compiler: {build_diag.chosen_compiler.resolved_path} "
                f"({build_diag.chosen_compiler.origin})"
            )
        else:
            lines.append("           No C compiler found in PATH.")
        if build_diag.chosen_include:
            lines.append(f"           Python headers:     {build_diag.chosen_include}")
        else:
            lines.append("           Python headers:     Python.h missing (install python3-dev)")

    lines.append(f"  Registered Backends ({len(BACKENDS)}):")
    for name in sorted(BACKENDS):
        tag = "native C core" if name == "zdd-native" else "pure-python"
        lines.append(f"    - {name:<17} [{tag}]")

    lines.append("  External Baselines (symq.external):")
    try:
        from symq import external

        if not external.UNAVAILABLE:
            versions = external.versions()
            lines.append(
                f"    [OK] Status: AVAILABLE ({', '.join(f'{k}: {v}' for k, v in versions.items())})"
            )
        else:
            missing = ", ".join(sorted(external.UNAVAILABLE))
            lines.append(f"    [INFO] Status: OPTIONAL (missing: {missing})")
            lines.append("           Install external baselines with: pip install 'symq[external]'")
    except ImportError:
        lines.append("    [INFO] Status: not installed (install with pip install 'symq[external]')")

    output_str = "\n".join(lines)
    print(output_str, file=out)
    return 0
