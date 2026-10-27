"""Run the corpus benchmark and write an immutable result directory.

Each (circuit, workload, backend) cell runs in a fresh worker process: warmup runs, then
timed repetitions (``perf_counter``, no instrumentation), then one separate untimed run
under ``tracemalloc`` for the peak Python allocation. The worker also reports its peak RSS.

Workloads (all inputs symbolic, i.e. ``full_input``):
  simulate  symbolic outputs of the circuit;
  equiv     check against a variant built only from sound rewrites (must be equivalent);
  nonequiv  check against the circuit with one inserted MCX gate (never equivalent).
Variant and mutant generation is timed separately and excluded from the check time.

Usage: python benchmarks/run.py [--splits dev holdout extension] [--backends ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import resource
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from report import write_report

from symq import BACKENDS, Budget, ResourceLimitExceeded, check_equivalence, make_algebra
from symq import simulate as simulate_circuit
from symq.corpus import SPLITS, load_corpus, sha256_hex
from symq.generators import equivalent_variant, mutate

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "corpus" / "qcec" / "MANIFEST.json"
WORKLOADS = ("simulate", "equiv", "nonequiv")


def seed_for(name: str) -> int:
    return int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)


def fingerprint(algebra, outputs) -> str:
    digest = hashlib.sha256()
    for value in outputs:
        digest.update(",".join(map(str, sorted(algebra.to_anf(value).terms))).encode())
        digest.update(b";")
    return digest.hexdigest()


def prepare(circuit, name: str, workload: str):
    rng = random.Random(seed_for(name))
    started = time.perf_counter()
    if workload == "equiv":
        other = equivalent_variant(circuit, rng, steps=len(circuit.gates))
    elif workload == "nonequiv":
        other, _ = mutate(circuit, rng, kind="insert")
    else:
        other = None
    return other, time.perf_counter() - started


def worker(cell: dict) -> dict:
    entry = next(e for e in load_corpus(cell["manifest"]).entries if e.name == cell["circuit"])
    circuit = entry.load()
    other, generation_seconds = prepare(circuit, entry.name, cell["workload"])
    budget = Budget(max_seconds=cell["run_timeout"])
    options = cell.get("options", {})
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    def run_once():
        if cell["workload"] == "simulate":
            algebra = make_algebra(cell["backend"], circuit.width, budget, **options)
            return algebra, simulate_circuit(circuit, algebra)
        return None, check_equivalence(circuit, other, backend=cell["backend"], budget=budget)

    record = {"generation_seconds": generation_seconds}
    try:
        for _ in range(cell["warmup"]):
            run_once()
        times = []
        for _ in range(cell["repetitions"]):
            started = time.perf_counter()
            algebra, outcome = run_once()
            times.append(time.perf_counter() - started)
        tracemalloc.start()
        run_once()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    except ResourceLimitExceeded as error:
        return {**record, "status": "resource_limit", "resource": error.resource,
                "limit": error.limit, "observed": error.observed}
    record.update(status="ok", seconds=times, tracemalloc_peak_bytes=peak,
                  baseline_maxrss_kib=baseline_rss,
                  maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if cell["workload"] == "simulate":
        record["stats"] = asdict(algebra.stats)
        record["fingerprint"] = fingerprint(algebra, outcome)
        zdd = getattr(algebra, "zdd", algebra if cell["backend"] == "zdd" else None)
        if zdd is not None:
            record["zdd_nodes"] = zdd.node_count
        if hasattr(algebra, "switch_gate"):
            record["switch_gate"] = algebra.switch_gate
    else:
        expected = cell["workload"] == "equiv"
        record["stats"] = asdict(outcome.stats)
        record["equivalent"] = outcome.equivalent
        record["fingerprint"] = f"{outcome.equivalent}:{outcome.output}"
        record["witness"] = outcome.witness
        if outcome.equivalent != expected:
            record["status"] = "wrong_verdict"
    return record


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT.parent, capture_output=True, text=True,
                          check=True).stdout.strip()


def environment(args, corpus) -> dict:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memory = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                memory = int(line.split()[1])
    except OSError:
        pass
    return {
        "started_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symq_commit": git("rev-parse", "HEAD"),
        "symq_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": cpu,
        "cpu_count": os.cpu_count(),
        "cpu_affinity": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "mem_total_kib": memory,
        "corpus_manifest_sha256": sha256_hex(MANIFEST.read_bytes()),
        "corpus_source": corpus.manifest["source"],
        "protocol": {
            "splits": args.splits, "backends": args.backends, "workloads": args.workloads,
            "warmup": args.warmup, "repetitions": args.repetitions,
            "run_timeout_seconds": args.run_timeout, "cell_timeout_seconds": args.cell_timeout,
            "timing": "time.perf_counter around one run, no instrumentation",
            "memory": "tracemalloc peak from a separate untimed run; ru_maxrss of the worker",
            "isolation": "one fresh worker process per cell, cells run sequentially",
        },
        "command": sys.argv,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--splits", nargs="+", default=list(SPLITS), choices=SPLITS)
    parser.add_argument("--backends", nargs="+", default=list(BACKENDS), choices=list(BACKENDS))
    parser.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=WORKLOADS)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--run-timeout", type=float, default=60.0)
    parser.add_argument("--cell-timeout", type=float, default=900.0)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--label", default="qcec")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return 0

    corpus = load_corpus(MANIFEST)
    problems = corpus.verify()
    if problems:
        raise SystemExit("corpus verification failed:\n" + "\n".join(problems))
    env = environment(args, corpus)
    if env["symq_dirty"] and not args.allow_dirty:
        raise SystemExit("tracked files are modified; commit first or pass --allow-dirty")
    stamp = env["started_utc"].replace("-", "").replace(":", "")
    target = args.out / f"{stamp}_{env['symq_commit'][:12]}_{args.label}"
    target.mkdir(parents=True, exist_ok=False)
    (target / "environment.json").write_text(json.dumps(env, indent=2) + "\n")

    with (target / "results.jsonl").open("w") as sink:
        for entry in corpus.select(tuple(args.splits)):
            base = {"circuit": entry.name, "split": entry.split, "width": entry.width,
                    "gates": entry.gates}
            if not entry.supported:
                sink.write(json.dumps({**base, "status": "unsupported",
                                       "reason": entry.reason}) + "\n")
                continue
            for workload in args.workloads:
                for backend in args.backends:
                    cell = {"manifest": str(MANIFEST), "circuit": entry.name,
                            "workload": workload, "backend": backend, "warmup": args.warmup,
                            "repetitions": args.repetitions, "run_timeout": args.run_timeout}
                    started = time.perf_counter()
                    try:
                        done = subprocess.run(
                            [sys.executable, __file__, "--worker", json.dumps(cell)],
                            capture_output=True, text=True, timeout=args.cell_timeout,
                            check=False)
                        if done.returncode == 0:
                            outcome = json.loads(done.stdout)
                        else:
                            outcome = {"status": "error", "stderr": done.stderr[-2000:]}
                    except subprocess.TimeoutExpired:
                        outcome = {"status": "timeout", "limit": args.cell_timeout}
                    row = {**base, "workload": workload, "backend": backend, **outcome,
                           "cell_wall_seconds": time.perf_counter() - started}
                    sink.write(json.dumps(row) + "\n")
                    sink.flush()
                    print(f"{entry.name:15s} {workload:9s} {backend:16s} {row['status']}",
                          file=sys.stderr)
    print(write_report(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
