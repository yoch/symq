"""Per-call cost of each engine's Python binding, for the matched loop of ``matched.py``.

The matched loop calls ``mul`` and ``add`` of every engine from Python, so its time is the
engine's work plus one binding call per operation. This script measures the second term on
its own: the time of ``mul(x0, x1)`` and ``add(x0, x1)`` on two variables after a first call
has filled the operation cache, i.e. argument passing, the cache lookup and the return. A
Python function that returns its first argument gives the floor of any call from the loop.
It also counts the ``mul``/``add`` calls the loop makes on every circuit (``simulate``), so
that the analysis can bound how much of a loop time is binding overhead.

One fresh pinned worker process per engine; ``--batches`` batches of ``--calls`` calls, the
median batch is reported in nanoseconds per call.

Usage: python benchmarks/binding_overhead.py --pin 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from matched import CORPORA, ENGINES
from run import git

from symq.backends import _zdd
from symq.corpus import load_corpus, sha256_hex

ROOT = Path(__file__).resolve().parent
ENGINE_NAMES = ("zdd-native", "polybori", "cudd-bdd", "cudd-bdd-static")


def per_call(function, left, right, calls: int, batches: int) -> float:
    function(left, right)
    samples = []
    for _ in range(batches):
        started = time.perf_counter()
        for _ in range(calls):
            function(left, right)
        samples.append((time.perf_counter() - started) / calls * 1e9)
    return statistics.median(samples)


def worker(cell: dict) -> dict:
    if cell["pin"] is not None:
        os.sched_setaffinity(0, {cell["pin"]})
    engine = ENGINES[cell["engine"]](cell["width"])
    mul, add, _, _ = engine.ops()
    left, right = engine.state[0], engine.state[1]
    calls, batches = cell["calls"], cell["batches"]
    return {"status": "ok",
            "mul_ns": per_call(mul, left, right, calls, batches),
            "add_ns": per_call(add, left, right, calls, batches),
            "python_call_floor_ns": per_call(lambda a, b: a, left, right, calls, batches)}


def loop_calls(corpus_name: str) -> dict[str, dict[str, int]]:
    """``mul`` and ``add`` calls of the matched loop on each supported circuit (simulate)."""
    counts = {}
    for entry in load_corpus(CORPORA[corpus_name]).entries:
        if not entry.supported:
            continue
        gates = entry.load().gates
        counts[entry.name] = {
            "mul": sum(max(len(g.qubits) - 2, 0) for g in gates),
            "add": len(gates),
        }
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--calls", type=int, default=200_000)
    parser.add_argument("--batches", type=int, default=7)
    parser.add_argument("--pin", type=int)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return 0

    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked files are modified; commit first")
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = git("rev-parse", "HEAD")
    target = args.out / f"{started.replace('-', '').replace(':', '')}_{commit[:12]}_binding"
    target.mkdir(parents=True, exist_ok=False)
    manifest = CORPORA["qcec"]
    native = Path(_zdd.__file__)
    if native.parent != ROOT.parent / "src" / "symq" / "backends":
        raise SystemExit(f"symq is imported from {native.parent}, not from this checkout; "
                         "set PYTHONPATH=src")
    environment = {
        "started_utc": started, "symq_commit": commit, "symq_dirty": False,
        "native_extension_sha256": sha256_hex(native.read_bytes()),
        "python": sys.version, "corpus": "qcec",
        "corpus_manifest_sha256": sha256_hex(manifest.read_bytes()),
        "protocol": {"width": args.width, "calls": args.calls, "batches": args.batches,
                     "operands": "variables x0 and x1, operation cache filled by one call",
                     "statistic": "median batch, nanoseconds per call", "pinned_cpu": args.pin},
        "command": sys.argv,
    }
    (target / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    rows = []
    for engine in ENGINE_NAMES:
        cell = {"engine": engine, "width": args.width, "calls": args.calls,
                "batches": args.batches, "pin": args.pin}
        done = subprocess.run([sys.executable, __file__, "--worker", json.dumps(cell)],
                              capture_output=True, text=True, check=False)
        outcome = (json.loads(done.stdout) if done.returncode == 0
                   else {"status": "error", "returncode": done.returncode,
                         "stderr": done.stderr[-2000:]})
        rows.append({"engine": engine, **outcome})
        print(json.dumps(rows[-1]), file=sys.stderr)
    (target / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary = {"loop_calls": {name: loop_calls(name) for name in ("qcec", "blind")}}
    (target / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    names = ["environment.json", "results.jsonl", "summary.json"]
    (target / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256((target / n).read_bytes()).hexdigest()}  {n}\n" for n in names))
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
