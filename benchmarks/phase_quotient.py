"""Bounded public-prefix phase qualification; no holdout or speedup claim.

Run ``python -m benchmarks.phase_quotient --output evidence/phase-quotient.json``.
The existing licensed inc8 fixture is authenticated before extracting its first
five reversible gates. Certificates are constructed, not automatically discovered.
Results belong in CI artifacts rather than in version control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from benchmarks.environment import machine, receipt
from symq.anf import ANF
from symq.circuit import Circuit, Gate
from symq.kickmix import parse_kmx
from symq.labs.phase_quotient import (
    PhaseQuotientCertificate,
    certificate_to_dict,
    check_prefix_phase,
    replay_prefix_phase,
)
from symq.resources import Budget, ResourceLimitExceeded

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "corpus" / "kickmix"


def public_case() -> tuple[Circuit, PhaseQuotientCertificate, tuple[tuple[int, int], ...], dict]:
    manifest = json.loads((CORPUS / "MANIFEST.json").read_text())
    entry = next(row for row in manifest["files"] if row["file"] == "inc8.kmx")
    raw = (CORPUS / entry["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"] or len(raw) != entry["bytes"]:
        raise ValueError("public inc8 source does not match its provenance manifest")
    program = parse_kmx(raw.decode()).to_phase_program(range(8))
    selected = program.ops[:5]
    if len(selected) != 5 or any(op.kind != "mcx" or len(op.qubits) != 3 for op in selected):
        raise ValueError("the public prefix is not the expected five Toffoli gates")
    prefix = Circuit(program.width, [Gate("ccx", op.qubits) for op in selected])
    invariants, multipliers, delta = [], [], {}
    for gate in prefix.gates:
        product = sum(1 << q for q in gate.controls)
        target = 1 << gate.target
        invariants.append(ANF(frozenset({product, target})))
        multipliers.append(((0, 1), (product, 6)))
        for mask, coefficient in ((target, 1), (product, 7)):
            delta[mask] = (delta.get(mask, 0) + coefficient) % 8
    certificate = PhaseQuotientCertificate(
        prefix.width, 3, tuple(sorted((m, c) for m, c in delta.items() if c)),
        tuple(invariants), tuple(multipliers),
    )
    constants = tuple((q, 0) for q in range(program.data, program.width))
    provenance = {**manifest["source"], **entry,
                  "fixture_manifest_sha256": hashlib.sha256(
                      (CORPUS / "MANIFEST.json").read_bytes()).hexdigest(),
                  "selected_operations": [0, 5], "input_data_wires": list(range(program.data)),
                  "status": "previously explored public fixture; not a holdout"}
    return prefix, certificate, constants, provenance


def _oracle(prefix: Circuit, certificate: PhaseQuotientCertificate,
            constants: tuple[tuple[int, int], ...]) -> dict:
    """Independent scalar basis execution; no certificate arithmetic is reused."""
    fixed = dict(constants)
    free = [q for q in range(prefix.width) if q not in fixed]
    if len(free) > 12:
        raise ValueError("scalar qualification oracle is limited to 12 free bits")
    fixed_ones = sum(1 << q for q, bit in constants if bit)
    violations = phase_differences = 0
    phases: set[int] = set()
    for index in range(1 << len(free)):
        value = fixed_ones | sum(((index >> j) & 1) << q for j, q in enumerate(free))
        output = prefix.run(value)
        violations += any(p.evaluate(output) for p in certificate.invariants)
        phase = sum(c for mask, c in certificate.delta if mask & output == mask) % (1 << certificate.k)
        phases.add(phase)
        phase_differences += phase != certificate.constant
    return {"inputs": 1 << len(free), "invariant_violations": violations,
            "phase_differences": phase_differences, "phases": sorted(phases)}


def _trial(source: Circuit, certificate: PhaseQuotientCertificate,
           initial: tuple[tuple[int, int], ...], expected: str, oracle: dict,
           repetition: int) -> dict:
    """Retain and qualify one trial, including a failed verdict or replay."""
    trial = {"repetition": repetition, "outcome": "error", "receipt": None,
             "replay": {"status": "not_run", "receipt": None}, "failures": []}
    proof = None
    tracemalloc.start()
    start = time.perf_counter()
    try:
        proof = check_prefix_phase(source, certificate,
                                    Budget(max_terms=100_000, max_seconds=5),
                                    initial_constants=initial)
        trial["outcome"] = proof.outcome
        trial["receipt"] = proof.to_dict()
    except Exception as error:  # noqa: BLE001 - failed trials must survive in the artifact
        trial["outcome"] = "inconclusive" if isinstance(error, ResourceLimitExceeded) else "error"
        trial["failures"].append({"stage": "verification", "type": type(error).__name__,
                                  "detail": str(error)})
    finally:
        trial["seconds_full_call"] = time.perf_counter() - start
        trial["peak_tracemalloc_bytes"] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

    if trial["outcome"] != expected:
        trial["failures"].append({"stage": "expected_outcome", "expected": expected,
                                  "observed": trial["outcome"]})
    if expected == "not_proved" and (oracle["invariant_violations"] == 0
                                     and oracle["phases"] == [certificate.constant]):
        # A refusal of a true claim would be sound; an adverse case must really be false.
        trial["failures"].append({"stage": "adverse_fixture",
                                  "detail": "the exhaustive oracle says this claim holds"})
    if proof is not None and trial["receipt"] is not None:
        # Soundness: a proof must state the constant the oracle sees, with true invariants.
        # not_proved is sound for any claim, so it is never checked against the oracle.
        if proof.outcome == "proved" and (oracle["invariant_violations"] != 0
                                          or oracle["phases"] != [proof.constant]):
            trial["failures"].append({"stage": "scalar_oracle",
                                      "detail": "proved constant or invariants disagree with "
                                                "the exhaustive oracle"})
        try:
            replayed = replay_prefix_phase(source, certificate, trial["receipt"],
                                            Budget(max_terms=100_000, max_seconds=5),
                                            initial_constants=initial)
            trial["replay"] = {"status": "matched" if replayed == proof else "mismatch",
                                "receipt": replayed.to_dict()}
            if replayed != proof:
                trial["failures"].append({"stage": "replay",
                                          "detail": "replay changed the result"})
        except Exception as error:  # noqa: BLE001 - preserve failed replay evidence too
            trial["replay"] = {"status": "error", "receipt": None,
                                "type": type(error).__name__, "detail": str(error)}
            trial["failures"].append({"stage": "replay", "type": type(error).__name__,
                                      "detail": str(error)})
    trial["passed"] = not trial["failures"]
    return trial


def run(repetitions: int = 3) -> dict:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    prefix, certificate, constants, provenance = public_case()
    changed_delta = dict(certificate.delta)
    changed_delta[0] = 1
    cases = [
        ("public_prefix", prefix, certificate, constants, "proved"),
        ("missing_last_ccx", Circuit(prefix.width, prefix.gates[:-1]), certificate,
         constants, "not_proved"),
        ("last_ancilla_arbitrary", prefix, certificate, constants[:-1], "not_proved"),
        ("mutated_phase", prefix, replace(certificate, delta=tuple(sorted(changed_delta.items()))),
         constants, "not_proved"),
    ]
    rows = []
    for name, source, cert, initial, expected in cases:
        oracle = _oracle(source, cert, initial)
        trials = [_trial(source, cert, initial, expected, oracle, repetition + 1)
                  for repetition in range(repetitions)]
        samples = [trial["seconds_full_call"] for trial in trials]
        outcomes = {trial["outcome"] for trial in trials}
        common_receipt = trials[0]["receipt"]
        if any(trial["receipt"] != common_receipt for trial in trials):
            common_receipt = None
        failures = [{"repetition": trial["repetition"], **failure}
                    for trial in trials for failure in trial["failures"]]
        rows.append({"id": name, "expected_outcome": expected,
                     "outcome": next(iter(outcomes)) if len(outcomes) == 1 else "mixed",
                     "passed": all(trial["passed"] for trial in trials), "oracle": oracle,
                     "receipt": common_receipt, "certificate": certificate_to_dict(cert),
                     "repetitions": repetitions, "seconds_full_call": samples,
                     "median_seconds_full_call": statistics.median(samples),
                     "peak_tracemalloc_bytes": max(trial["peak_tracemalloc_bytes"]
                                                    for trial in trials),
                     "failures": failures, "trials": trials})
    return {
        "schema_version": 1, "kind": "symq_phase_quotient_qualification",
        "passed": all(row["passed"] for row in rows),
        "failed_trials": sum(not trial["passed"] for row in rows for trial in row["trials"]),
        "scope": "one public prefix, three adverse cases; exact scalar qualification, no speedup claim",
        "machine": machine(), "source": receipt(), "fixture": provenance,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limits": {"max_terms": 100_000, "max_seconds_per_full_call": 5,
                   "memory_measurement": "tracemalloc Python allocations; not total RSS"},
        "cases": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Write all trial evidence before returning failure for any mismatch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    arguments = parser.parse_args(argv)
    result = run(arguments.repetitions)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(encoded, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
