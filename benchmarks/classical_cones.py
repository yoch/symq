"""Reproduce bounded classical-cone qualification; no speed or holdout claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from symq import Circuit
from symq.labs.classical_cone import ConeLimits, prove_cone_predicate, replay_cone_predicate
from symq.labs.classical_transcript import Program, digest
from symq.resources import Budget
from symq.sat.assumptions import And, Eq, Var

from .environment import machine, receipt

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261107


def cases() -> list[dict]:
    source = Circuit(6)
    for index in range(1331):
        if index == 650:
            source.ccx(0, 1, 2)
        source.cx(4, 5) if index % 2 else source.x(4)
    clobbered = source.snapshot().x(2)
    return [
        {"id": "clean-interleaved", "source": source, "initial": ((2, 0),),
         "expand": True, "expected": "proved"},
        {"id": "dirty-interleaved", "source": source, "initial": (),
         "expand": True, "expected": "precondition_failed"},
        {"id": "clobbered-product", "source": clobbered, "initial": ((2, 0),),
         "expand": True, "expected": "precondition_failed"},
        {"id": "short-cut-only", "source": source, "initial": ((2, 0),),
         "expand": False, "expected": "not_proved"},
        {"id": "expansion-cap", "source": source, "initial": ((2, 0),),
         "expand": True, "limits": ConeLimits(max_attempts=1), "expected": "inconclusive"},
    ]


def _scalar(source: Circuit, value: int) -> list[int]:
    """Independent dense bit-list execution, outside the measured proof calls."""
    bits = [(value >> q) & 1 for q in range(source.width)]
    for gate in source.gates:
        if gate.name == "x":
            bits[gate.qubits[0]] ^= 1
        elif gate.name == "cx":
            a, b = gate.qubits
            bits[b] ^= bits[a]
        elif gate.name == "ccx":
            a, b, c = gate.qubits
            bits[c] ^= bits[a] * bits[b]
        else:
            raise ValueError("benchmark oracle only implements X/CX/CCX")
    return bits


def trial(case: dict, repetition: int) -> dict:
    source = case["source"]
    predicate = Eq(Var("u.2"), And(Var("u.0"), Var("u.1")))
    limits = case.get("limits", ConeLimits())
    kwargs = {"at": len(source.gates), "predicate": predicate,
              "expected_source_sha256": digest(Program.freeze(source)),
              "initial_constants": case["initial"], "limits": limits,
              "budget": Budget(max_seconds=5)}
    started, cpu = time.perf_counter(), time.process_time()
    proof = prove_cone_predicate(source, start_op=len(source.gates) - 32,
                                 expand_cut=case["expand"], **kwargs)
    proof_wall, proof_cpu = time.perf_counter() - started, time.process_time() - cpu
    replay_wall = replay_cpu = None
    replayed = None
    if proof.proved:
        started, cpu = time.perf_counter(), time.process_time()
        replayed = replay_cone_predicate(source, proof.to_dict(), **kwargs).proved
        replay_wall, replay_cpu = time.perf_counter() - started, time.process_time() - cpu
    legal = [x for x in range(1 << source.width)
             if all((x >> q) & 1 == bit for q, bit in case["initial"])]
    violations = []
    for value in legal:
        state = _scalar(source, value)
        if state[2] != state[0] * state[1]:
            violations.append(value)
    oracle_ok = proof.outcome == case["expected"] and (
        proof.proved and not violations and replayed
        or proof.outcome == "precondition_failed" and proof.counterexample_input in violations
        or proof.outcome in ("not_proved", "inconclusive") and not proof.proved
        and proof.counterexample_input is None
    )
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "case": case["id"], "repetition": repetition, "source_sha256": kwargs["expected_source_sha256"],
        "source_gates": len(source.gates), "source_width": source.width,
        "initial_constants": case["initial"], "at": kwargs["at"],
        "start_op": len(source.gates) - 32, "expand_cut": case["expand"],
        "limits": asdict(limits), "max_seconds_per_call": 5,
        "outcome": proof.outcome, "reason": proof.reason, "engine": proof.engine,
        "attempts": len(proof.attempts), "cone_gates": None if proof.cone is None
        else len(proof.cone.program.gates), "source_legal_inputs": len(legal),
        "source_violations": len(violations), "proof_wall_seconds": proof_wall,
        "proof_cpu_seconds": proof_cpu, "replay_wall_seconds": replay_wall,
        "replay_cpu_seconds": replay_cpu, "replayed": replayed,
        "process_peak_rss_bytes": int(rss if sys.platform == "darwin" else rss * 1024),
        "oracle_ok": bool(oracle_ok),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    order = [(case, rep) for rep in range(args.repetitions) for case in cases()]
    random.Random(SEED).shuffle(order)
    trials = []
    for case, repetition in order:
        try:
            trials.append(trial(case, repetition))
        except Exception as error:  # noqa: BLE001 - record failed trials, never discard them
            trials.append({"case": case["id"], "repetition": repetition, "outcome": "error",
                           "reason": f"{type(error).__name__}: {error}", "oracle_ok": False})
    record = {
        "schema_version": 1, "kind": "symq_classical_cone_development_qualification",
        "scope": "synthetic functional qualification; no holdout or performance advantage claim",
        "provenance": "original synthetic fixtures; repository MIT license; exposed development set",
        "timing": "serial randomized trials; independent oracle excluded; warm process caches",
        "memory": "cumulative process peak RSS, including imports and earlier trials",
        "seed": SEED, "machine": machine(), "software": receipt(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "module_sha256": hashlib.sha256((ROOT / "src/symq/labs/classical_cone.py").read_bytes()).hexdigest(),
        "outcomes": dict(Counter(row["outcome"] for row in trials)),
        "all_oracles_ok": all(row["oracle_ok"] for row in trials), "trials": trials,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"trials": len(trials), "outcomes": record["outcomes"],
                      "all_oracles_ok": record["all_oracles_ok"]}, sort_keys=True))
    if not record["all_oracles_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
