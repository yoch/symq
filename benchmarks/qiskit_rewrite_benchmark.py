"""Reproducible full-call Qiskit→SymQ paired pilot measurements.

Each observation executes in its own fresh Python subprocess: the parent
records interpreter startup-inclusive wall time and the child records the
transpiler + parser + SAT contextual proof + replay phases and peak RSS.
No performance superiority or quantum-channel theorem is inferred.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import resource
import subprocess
import sys
import time

from benchmarks.qiskit_transpiler_pilot import transpiled_cases
from symq import Circuit
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import Weights
from symq.labs.rewrite_prepare import prepare_local_classical
from symq.labs.rewrite_request import replay_report, run_request

_NAMES = ("conjugated_swap_cx", "double_swap_ccx")


def _run_trial(name: str) -> dict:
    start = time.perf_counter()
    cpu_start = time.process_time()
    case = next(iter(transpiled_cases(only=name)))
    compiled = time.perf_counter()
    source = Circuit(case["source"].width + 2).x(0)
    for gate in case["source"].gates:
        source.append(gate.name, *(q + 2 for q in gate.qubits))
    source.cx(0, 1)
    plan = prepare_local_classical(
        source, case["source"], case["candidate"],
        contract=SubstitutionContract(), engine="sat",
        weights=Weights.from_mapping({"cx": 1, "ccx": 32}),
        require_saving=True,
    )
    if not plan.ready:
        raise RuntimeError("full-block source was not uniquely located")
    prepared = time.perf_counter()
    receipt = run_request(plan.request)
    proven = time.perf_counter()
    if receipt["result"]["outcome"] != "equivalent" or receipt["application"] != "applied":
        raise RuntimeError("the SAT proof did not authorize the candidate")
    replay = replay_report(receipt)
    finished = time.perf_counter()
    if not replay["replay"]["reverified"]:
        raise RuntimeError("the proof report was not freshly reverified")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "case": name,
        "qiskit_version": case["qiskit_version"],
        "qasm_sha256": case["qasm_sha256"],
        "original_gates": case["original_gates"],
        "candidate_gates": case["candidate_gates"],
        "compiler_parse_seconds": compiled - start,
        "preparation_seconds": prepared - compiled,
        "proof_seconds": proven - prepared,
        "replay_seconds": finished - proven,
        "inprocess_total_seconds": finished - start,
        "inprocess_cpu_seconds": time.process_time() - cpu_start,
        # Linux GitHub-hosted runners expose ru_maxrss in KiB. This is
        # process-wide high-water mark, not an incremental per-call estimate.
        "process_peak_rss_kib_linux": rss,
        "proof_theorem": receipt["result"]["theorem"],
        "status": "equivalent_replayed",
    }


def _benchmark(repetitions: int) -> None:
    if not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be between 1 and 100")
    rng = random.Random(20261103)
    for repetition in range(repetitions):
        names = list(_NAMES)
        rng.shuffle(names)
        for order, name in enumerate(names):
            started = time.perf_counter()
            proc = subprocess.run(
                [sys.executable, "-m", "benchmarks.qiskit_rewrite_benchmark",
                 "--trial", name],
                check=True, capture_output=True, text=True,
            )
            row = json.loads(proc.stdout)
            row["repetition"] = repetition
            row["pair_order"] = order
            row["startup_inclusive_wall_seconds"] = time.perf_counter() - started
            row["runner_os"] = platform.system()
            row["python_version"] = platform.python_version()
            print(json.dumps(row, sort_keys=True), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--trial", choices=_NAMES)
    mode.add_argument("--benchmark", action="store_true")
    parser.add_argument("--repetitions", type=int, default=15)
    args = parser.parse_args()
    if args.trial:
        print(json.dumps(_run_trial(args.trial), sort_keys=True))
    else:
        _benchmark(args.repetitions)


if __name__ == "__main__":
    main()
