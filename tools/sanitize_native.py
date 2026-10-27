"""Run the native-core tests against an AddressSanitizer + UndefinedBehaviorSanitizer build.

The sanitized extension is compiled into a temporary copy of ``src/``, so the in-place release
build is never replaced. CPython itself is not instrumented: ``libasan`` is preloaded and leak
detection is disabled (the interpreter's own allocations would be reported). Timings from
this build must never be mixed with release timings.

Usage: python tools/sanitize_native.py [pytest arguments]   (default: the native tests)
Requires gcc or clang with ASan/UBSan runtimes; exits 2 when they are missing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ["-O1", "-g", "-fno-omit-frame-pointer", "-fsanitize=address,undefined",
         "-fno-sanitize-recover=undefined", "-std=c11", "-fPIC", "-shared",
         "-fno-strict-aliasing"]
# ``float-cast-overflow`` is included: resource counts travel as integers, and this check is
# what catches a rounding path that would reintroduce the undefined conversion of #40.
FLAGS += ["-fsanitize=float-cast-overflow"]
DEFAULT_TESTS = ["tests/test_zdd_native.py", "tests/test_audit_regressions.py",
                 "tests/test_native_limits.py", "tests/test_backends.py",
                 "tests/test_equivalence.py"]


def runtime(compiler: str) -> str | None:
    found = subprocess.run([compiler, "-print-file-name=libasan.so"], capture_output=True,
                           text=True, check=False).stdout.strip()
    return found if found and Path(found).is_file() else None


def main() -> int:
    compiler = shutil.which(os.environ.get("CC", "gcc"))
    library = runtime(compiler) if compiler else None
    if compiler is None or library is None:
        print("no compiler with an AddressSanitizer runtime", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="symq-asan-") as scratch:
        src = Path(scratch) / "src"
        shutil.copytree(ROOT / "src", src,
                        ignore=shutil.ignore_patterns("*.so", "__pycache__"))
        suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
        output = src / "symq" / "backends" / f"_zdd{suffix}"
        command = [compiler, *FLAGS, f"-I{sysconfig.get_paths()['include']}",
                   str(src / "symq" / "backends" / "_zdd.c"), "-o", str(output)]
        print(" ".join(command), file=sys.stderr)
        subprocess.run(command, check=True)
        env = dict(os.environ, PYTHONPATH=str(src), LD_PRELOAD=library,
                   ASAN_OPTIONS="detect_leaks=0:abort_on_error=1",
                   UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1")
        probe = subprocess.run(
            [sys.executable, "-c", "import symq.backends._zdd as z; print(z.__file__)"],
            env=env, capture_output=True, text=True, check=True).stdout.strip()
        if not probe.startswith(str(src)):
            print(f"sanitized build not imported: {probe}", file=sys.stderr)
            return 1
        tests = sys.argv[1:] or DEFAULT_TESTS
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               *tests], cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
