"""Small paired native experiments; isolated workers, raw timings and source hashes.

Run: python benchmarks/native_roadmap.py --repetitions 3 --out /tmp/native-roadmap.json
These development fixtures are not an independent performance qualification corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (("rename", "rename_many"), ("hmr_python", "hmr_fused"), ("clone_anf", "clone_dag"))


def _worker(strategy: str, seed: int) -> dict:
    from symq import Budget, PhaseProgram
    from symq.backends import make_algebra

    rng = random.Random(seed)
    start = time.perf_counter()
    algebra = make_algebra("zdd-native", 24, Budget(max_nodes=1_000_000, max_seconds=10))
    roots = []
    mapping = list(range(12, 24)) + list(range(12))
    program = None
    if strategy.startswith(("rename", "clone")):
        family = 1
        for q in range(8 if strategy.startswith("rename") else 12):
            family = algebra.product((family, algebra.xor(1, algebra.variable(q))))
        roots = [family] * 128 if strategy.startswith("rename") else [family]
    else:
        program = PhaseProgram(6, 3)
        for _ in range(40):
            a, b = rng.sample(range(6), 2)
            ancilla = rng.randrange(6, 9)
            program.ccx(a, b, ancilla)
            event = program.hmr(ancilla)
            program.cz_if(event, a, b)
            program.cz(a, b)
    preparation = time.perf_counter() - start
    start = time.perf_counter()
    if strategy == "rename":
        roots = [algebra.manager.rename(root, mapping) for root in roots]
    elif strategy == "rename_many":
        roots = algebra.rename_many(roots, mapping)
    elif strategy == "clone_anf":
        fresh = make_algebra("zdd-native", 24)
        roots = [fresh.from_terms(algebra.manager.anf(root)) for root in roots]
        algebra = fresh
    elif strategy == "clone_dag":
        roots = algebra.collect_roots(roots)
    elif strategy == "hmr_fused":
        state, phase, coefficients = algebra.simulate_hmr(program)
        roots = (*state, phase, *coefficients)
    else:
        program.validate()
        state = [algebra.variable(q) if q < program.data else 0 for q in range(program.width)]
        phase, coefficients = 0, []
        for op in program.ops:
            if op.kind == "hmr":
                coefficients.append(state[op.qubits[0]])
                state[op.qubits[0]] = 0
            elif op.kind == "mcx":
                *controls, target = op.qubits
                state[target] = algebra.xor(state[target], algebra.product([state[q] for q in controls]))
            elif op.kind == "mcz":
                phase = algebra.xor(phase, algebra.product([state[q] for q in op.qubits]))
            else:
                event = op.outcome
                coefficients[event] = algebra.xor(
                    coefficients[event], algebra.product([state[q] for q in op.qubits]),
                )
        roots = (*state, phase, *coefficients)
    elapsed = time.perf_counter() - start
    start = time.perf_counter()
    # Fingerprint semantic content, never manager-local integer IDs.
    content = [sorted(algebra.to_anf(root).terms) for root in roots]
    fingerprint = hashlib.sha256(json.dumps(content).encode()).hexdigest()
    conversion = time.perf_counter() - start
    return {
        "strategy": strategy, "seed": seed, "seconds": elapsed,
        "preparation_seconds": preparation, "conversion_seconds": conversion,
        "sha256": fingerprint, "nodes": algebra.node_count,
        "memory": algebra.memory_info(),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                          (1 if sys.platform == "darwin" else 1024),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=sum(PAIRS, ()))
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--repetitions", type=int, default=15)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_worker(args.worker, args.seed)))
        return
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    rows, failures = [], []
    rng = random.Random(args.seed)
    for repetition in range(args.repetitions):
        for pair in PAIRS:
            ordered = list(pair)
            rng.shuffle(ordered)
            observed = []
            for strategy in ordered:
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--worker", strategy,
                     "--seed", str(args.seed + repetition)],
                    cwd=ROOT, text=True, capture_output=True, timeout=20,
                    check=False,
                )
                if completed.returncode:
                    failures.append({"strategy": strategy, "repetition": repetition,
                                     "stderr": completed.stderr, "returncode": completed.returncode})
                    continue
                row = json.loads(completed.stdout)
                row["repetition"] = repetition
                rows.append(row)
                observed.append(row)
            if len(observed) == 2 and observed[0]["sha256"] != observed[1]["sha256"]:
                failures.append({"pair": pair, "repetition": repetition, "error": "semantic mismatch"})
    result = {
        "schema": "symq/native-roadmap/development/v1",
        "utc": datetime.now(timezone.utc).isoformat(), "seed": args.seed,
        "repetitions": args.repetitions, "python": sys.version,
        "platform": platform.platform(), "machine": platform.machine(),
        "compiler": subprocess.run(["cc", "--version"], capture_output=True, text=True,
                                   check=False).stdout.splitlines()[0],
        "base_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                    capture_output=True, text=True, check=False).stdout.strip(),
        "sources": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in [Path(__file__), ROOT / "src/symq/backends/_zdd.c",
                                 ROOT / "src/symq/backends/zdd_native.py"]},
        "scope": "Development fixtures; paired order shuffled; one fresh process per sample."
                 " Operation and preparation/export times are separate. RSS covers the whole worker."
                 " No external-comparison or holdout performance claim.",
        "rows": rows, "failures": failures,
    }
    output = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    else:
        print(output, end="")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
