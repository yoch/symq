"""Compile ``src/symq/backends/_zdd.c`` in place with the platform C compiler.

Used by the build hook, by ``python tools/build_native.py`` and by the test suite, which skips
the native tests when no compiler is available. Returns the built path, or ``None``.
"""
from __future__ import annotations

import shutil
import subprocess
import sysconfig
from pathlib import Path

NAME = "symq.backends._zdd"


def source(root: Path | str) -> Path:
    return Path(root) / "src" / "symq" / "backends" / "_zdd.c"


def target(root: Path | str) -> Path:
    suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
    return Path(root) / "src" / "symq" / "backends" / f"_zdd{suffix}"


def build_extension(root: Path | str, quiet: bool = False) -> Path | None:
    """Compile and link in place; ``None`` when impossible (no compiler or no headers)."""
    root = Path(root)
    include = sysconfig.get_paths()["include"]
    compiler = sysconfig.get_config_var("CC") or "cc"
    cc = shutil.which(compiler.split()[0])
    if cc is None or not (Path(include) / "Python.h").exists():
        return None
    output = target(root)
    command = [
        cc,
        "-O3",
        "-std=c11",
        "-fPIC",
        "-shared",
        "-fno-strict-aliasing",
        f"-I{include}",
        str(source(root)),
        "-o",
        str(output),
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        if not quiet:
            print(done.stderr[-4000:], file=__import__("sys").stderr)
        return None
    return output


if __name__ == "__main__":
    built = build_extension(Path(__file__).resolve().parents[1])
    print(built if built is not None else "native core not built")
