"""Run the corpus benchmark and write an immutable result directory.

Each (circuit, workload, backend) cell runs in a fresh worker process: warmup runs, then
timed repetitions (``perf_counter``, no instrumentation), then one separate untimed run
under ``tracemalloc`` for the peak Python allocation. The worker also reports its peak RSS.

Workloads (all inputs symbolic, i.e. ``full_input``):
  simulate  symbolic outputs of the circuit;
  equiv     check against a variant built only from sound rewrites (must be equivalent);
  nonequiv  check against the circuit with one inserted MCX gate (never equivalent).
Variant and mutant generation is timed separately and excluded from the check time.

Native baselines (``pip install -e ".[external]"``, see ``symq.external``):
  polybori, cudd-bdd, cudd-zdd  same ``Algebra`` contract, so the same simulate and
                                equivalence code; their ANF conversion (verification only) is
                                timed separately as ``conversion_seconds``;
  qcec                          MQT QCEC verdicts on equiv/nonequiv; ``simulate`` is recorded
                                as ``not_applicable`` and non-proof verdicts as ``inconclusive``.

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

from symq import (
    BACKENDS,
    Budget,
    ResourceLimitExceeded,
    check_equivalence,
    external,
    make_algebra,
)
from symq import simulate as simulate_circuit
from symq.corpus import SPLITS, load_corpus, sha256_hex
from symq.generators import equivalent_variant, mutate

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "corpus" / "qcec" / "MANIFEST.json"
WORKLOADS = ("simulate", "equiv", "nonequiv")
EXTERNAL_ALGEBRAS = ("polybori", "cudd-bdd", "cudd-zdd")
CHOICES = (*BACKENDS, *EXTERNAL_ALGEBRAS, "qcec")


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


def resolve(name: str):
    """A registered backend name, or the class of an available native adapter."""
    if name in BACKENDS:
        return name
    if name in external.EXTERNAL_BACKENDS:
        return external.EXTERNAL_BACKENDS[name]
    raise RuntimeError(f"{name} unavailable: {external.UNAVAILABLE.get(name)}")


def qcec_worker(cell: dict, circuit, other, record: dict) -> dict:
    if cell["workload"] == "simulate":
        return {**record, "status": "not_applicable",
                "reason": "QCEC returns equivalence verdicts, not output polynomials"}
    if external.qcec_check is None:
        raise RuntimeError(f"qcec unavailable: {external.UNAVAILABLE.get('qcec')}")
    started = time.perf_counter()
    external.to_quantum_computation(circuit)
    external.to_quantum_computation(other)
    record["conversion_seconds"] = time.perf_counter() - started
    for _ in range(cell["warmup"]):
        external.qcec_check(circuit, other, timeout=cell["run_timeout"])
    times, results = [], []
    for _ in range(cell["repetitions"]):
        started = time.perf_counter()
        results.append(external.qcec_check(circuit, other, timeout=cell["run_timeout"]))
        times.append(time.perf_counter() - started)
    verdicts = {r.verdict for r in results}
    result = results[-1]
    record.update(seconds=times, verdict=result.verdict, equivalent=result.equivalent,
                  qcec_check_seconds=[r.check_seconds for r in results],
                  qcec_preprocessing_seconds=[r.preprocessing_seconds for r in results],
                  maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  fingerprint=None)
    expected = cell["workload"] == "equiv"
    if len(verdicts) > 1 or result.equivalent is None:
        record["status"] = "inconclusive"
    elif result.equivalent != expected:
        record["status"] = "wrong_verdict"
    else:
        record["status"] = "ok"
    return record


def worker(cell: dict) -> dict:
    entry = next(e for e in load_corpus(cell["manifest"]).entries if e.name == cell["circuit"])
    circuit = entry.load()
    other, generation_seconds = prepare(circuit, entry.name, cell["workload"])
    record = {"generation_seconds": generation_seconds}
    if cell["backend"] == "qcec":
        return qcec_worker(cell, circuit, other, record)
    backend = resolve(cell["backend"])
    budget = Budget(max_seconds=cell["run_timeout"])
    options = cell.get("options", {})
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    def run_once():
        if cell["workload"] == "simulate":
            algebra = make_algebra(backend, circuit.width, budget, **options)
            return algebra, simulate_circuit(circuit, algebra)
        return None, check_equivalence(circuit, other, backend=backend, budget=budget)

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
        started = time.perf_counter()
        record["fingerprint"] = fingerprint(algebra, outcome)
        if not isinstance(backend, str):
            record["conversion_seconds"] = time.perf_counter() - started
            record["native_nodes"] = algebra.native_nodes(outcome)
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
        "external": {
            "versions": external.versions(),
            "unavailable": external.UNAVAILABLE,
            "qcec_configuration": external.QCEC_CONFIGURATION,
            "cudd_reordering": "enabled (CUDD default); disabled during ANF conversion",
            "polybori_order": "lp",
        },
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
    parser.add_argument("--backends", nargs="+", default=list(BACKENDS), choices=CHOICES)
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

    missing = [b for b in args.backends if b in external.UNAVAILABLE]
    if missing:
        raise SystemExit("unavailable native tools: " + "; ".join(
            f"{b} ({external.UNAVAILABLE[b]})" for b in missing))
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
