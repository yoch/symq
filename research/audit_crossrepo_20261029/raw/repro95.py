"""Independent reproduction of the PR #95 native-vs-Python channel benchmark.

Differences from the PR harness, deliberately:

* each measurement runs in a **fresh subprocess**, so no allocator state is shared;
* backend order is **randomised per repetition**, to remove warm-cache bias;
* more repetitions (15 instead of 5), with median and interquartile spread reported;
* a negative workload (different programs) is included to check the verdict is not
  hard-coded to "equivalent";
* peak RSS is read from the child, so it is the child's peak, not the parent's.
"""

from __future__ import annotations

"""Audit harness (see ../README.md). Requires a checkout of PR #95 at its audited SHA.

Usage:
    PR95=/path/to/pr95-worktree python repro95.py

The environment variable PR95 must point at a worktree checked out at
af8a874db66a8176e14419cda13cff13c6db0ef2 with the native extension built
(python tools/build_native.py).
"""
import os
from pathlib import Path

PR95 = Path(os.environ.get("PR95", "/tmp/audit/pr95"))

import json
import os
import random
import statistics
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("PR95", "/tmp/audit/pr95"))
PY = os.environ.get("AUDIT_PYTHON", "python3")

CHILD = r"""
import json, os, resource, sys, time
from pathlib import Path
ROOT = Path(os.environ["PR95"])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from research.hmr_native_channel.native_channel import check_full_channel
from symq.phase import PhaseProgram
from symq.resources import Budget
import random

def case(data, hmr, family, mutant=False):
    program = PhaseProgram(data, 1)
    reference = PhaseProgram(data, 1)
    if family == "affine":
        for index in range(hmr):
            q = index % data
            program.cx(q, data)
            m = program.hmr(data)
            program.z_if(m, q)
        if mutant:
            reference.cx(0, data)
        return program, reference
    rng = random.Random(20261029)
    for _ in range(hmr):
        a, b, target = rng.sample(range(data), 3)
        program.ccx(a, b, target)
        reference.ccx(a, b, target)
        program.ccx(a, b, data)
        event = program.hmr(data)
        program.cz_if(event, a, b)
    if mutant:
        reference.ccx(0, 1, 2)
    return program, reference

backend, data, hmr, family, mutant = json.loads(sys.argv[1])
left, right = case(data, hmr, family, mutant)
started = time.perf_counter()
verdict = check_full_channel(
    left, right, backend=backend, budget=Budget(max_seconds=30, max_nodes=2_000_000))
elapsed = time.perf_counter() - started
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"equivalent": verdict.equivalent, "seconds": elapsed, "rss_kib": peak,
                  "reason": verdict.reason}))
"""


def run(backend, data, hmr, family, mutant=False):
    payload = json.dumps([backend, data, hmr, family, mutant])
    out = subprocess.run(
        [PY, "-c", CHILD, payload],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
        env={**os.environ, "PR95": str(ROOT)},
    )
    if out.returncode != 0:
        return {"error": out.stderr.strip().splitlines()[-1] if out.stderr else "unknown"}
    return json.loads(out.stdout)


def main():
    reps = 15
    cases = [
        ("affine", 8, 130),
        ("affine", 16, 500),
        ("nonlinear", 8, 70),
        ("nonlinear", 12, 25),
    ]
    report = {"reps": reps, "cases": []}
    rng = random.Random(7)
    for family, data, hmr in cases:
        samples = {"zdd": [], "zdd-native": []}
        errors = []
        for _ in range(reps):
            order = ["zdd", "zdd-native"]
            if rng.random() < 0.5:
                order.reverse()
            for backend in order:
                got = run(backend, data, hmr, family)
                if "error" in got:
                    errors.append((backend, got["error"]))
                else:
                    samples[backend].append(got)
        entry = {"family": family, "data": data, "hmr": hmr}
        for backend in ("zdd", "zdd-native"):
            vals = [s["seconds"] for s in samples[backend]]
            rss = [s["rss_kib"] for s in samples[backend]]
            if vals:
                entry[backend] = {
                    "n": len(vals),
                    "median_s": statistics.median(vals),
                    "min_s": min(vals),
                    "max_s": max(vals),
                    "iqr_s": (
                        statistics.quantiles(vals, n=4)[2] - statistics.quantiles(vals, n=4)[0]
                        if len(vals) >= 4
                        else None
                    ),
                    "median_rss_kib": statistics.median(rss),
                    "all_equivalent": all(s["equivalent"] for s in samples[backend]),
                }
        if entry.get("zdd") and entry.get("zdd-native"):
            entry["python_over_native"] = entry["zdd"]["median_s"] / entry["zdd-native"]["median_s"]
        if errors:
            entry["errors"] = errors[:3]
        report["cases"].append(entry)
        print(json.dumps(entry, indent=1), flush=True)

    # Negative control: a genuinely different pair must be rejected by both backends.
    print("\nnegative control (different programs):", flush=True)
    for backend in ("zdd", "zdd-native"):
        got = run(backend, 8, 20, "nonlinear", mutant=True)
        print(
            f"  {backend}: equivalent={got.get('equivalent')} reason={got.get('reason')}",
            flush=True,
        )

    target = Path(__file__).resolve().parent / "pr95_repro.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
