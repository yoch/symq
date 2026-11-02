"""Bounded program phase-difference qualification; no holdout or speedup claim.

Run ``python -m benchmarks.phase_delta_binding --output evidence/phase-delta-binding.json``.
The public inc8 prefix of ``benchmarks.phase_quotient`` is authenticated against
its manifest. Two constructed dyadic programs then differ only by a global phase
on its image: Z-type phases on each Toffoli target against CZ on its controls,
written with different moduli (k = 4 and k = 3) and a global T-gadget. The
certificate delta is written from that construction, not from the extractor.
Every trial records outcome, reason, receipt, a fresh replay and the exhaustive
scalar oracle of ``tests/testkit/phase_delta_oracle.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from benchmarks.environment import machine, receipt
from benchmarks.phase_quotient import public_case
from symq.anf import ANF
from symq.circuit import Circuit
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_delta_binding import (
    check_program_phase_difference,
    replay_program_phase_difference,
)
from symq.labs.phase_quotient import PhaseQuotientCertificate, certificate_to_dict
from symq.resources import Budget
from tests.testkit import phase_delta_oracle

LIMITS = {"max_terms": 100_000, "max_seconds": 5}
EXHAUSTED = {"max_terms": 8}


@dataclass(frozen=True)
class Case:
    name: str
    prefix: Circuit
    left: DyadicPhaseProgram
    right: DyadicPhaseProgram
    certificate: PhaseQuotientCertificate
    constants: tuple[tuple[int, int], ...]
    expected: str
    claim_true: bool  # Exhaustive truth of "left and right differ by a global phase on F(D)".
    expected_constant: int | None = None
    limits: tuple[tuple[str, int], ...] = tuple(sorted(LIMITS.items()))


def _programs(prefix: Circuit, global_gadget: bool) -> tuple[DyadicPhaseProgram, ...]:
    left = DyadicPhaseProgram(prefix.width, k=4)
    right = DyadicPhaseProgram(prefix.width, k=3)
    for gate in prefix.gates:
        left.phase(gate.target, Fraction(-1, 2))  # -1/2 turn, canonical 8 modulo 16
        right.cz(*gate.controls)
    if global_gadget:
        right.x(0).t(0).x(0).t(0)  # (1 - x0)/8 + x0/8 = 1/8 turn on every input
    return left, right


def _certificate(prefix: Circuit, invariants: tuple[ANF, ...], k: int,
                 global_gadget: bool) -> PhaseQuotientCertificate:
    """delta = sum 8*t_j - 8*c1c2_j - 2*[gadget] (mod 16) = c + sum 8*lift(t_j XOR c1c2_j)."""
    modulus = 1 << k
    delta: dict[int, int] = {}
    for gate in prefix.gates:
        for mask, coefficient in ((1 << gate.target, 8), (sum(1 << q for q in gate.controls), -8)):
            delta[mask] = (delta.get(mask, 0) + coefficient) % modulus
    constant = (-2 if global_gadget else 0) % modulus
    delta[0] = (delta.get(0, 0) + constant) % modulus
    multiplier = ((0, 8 % modulus),) if 8 % modulus else ()
    return PhaseQuotientCertificate(
        prefix.width, k, tuple(sorted((m, c) for m, c in delta.items() if c)), invariants,
        tuple(multiplier for _ in invariants), constant)


def cases() -> tuple[list[Case], dict]:
    prefix, public, constants, provenance = public_case()
    left, right = _programs(prefix, True)
    certificate = _certificate(prefix, public.invariants, 4, True)
    _, stale_right = _programs(prefix, False)
    stale = _certificate(prefix, public.invariants, 4, False)
    swapped_outputs = DyadicPhaseProgram(right.width, list(right.gates), right.k).cx(0, 1)
    shorter = Circuit(prefix.width, prefix.gates[:-1])
    coarse = _certificate(prefix, public.invariants, 3, True)
    return [
        Case("public_programs", prefix, left, right, certificate, constants, "proved", True, 14),
        Case("stale_delta_for_other_right", prefix, left, right, stale, constants,
             "not_proved", True),
        Case("certificate_at_min_k", prefix, left, right, coarse, constants, "not_proved", True),
        Case("stale_certificate_holds_for_its_own_programs", prefix, left, stale_right, stale,
             constants, "proved", True, 0),
        Case("different_outputs", prefix, left, swapped_outputs, certificate, constants,
             "not_proved", False),
        Case("missing_last_ccx", shorter, left, right, certificate, constants,
             "not_proved", False),
        Case("last_ancilla_arbitrary", prefix, left, right, certificate, constants[:-1],
             "not_proved", False),
        Case("budget_exhausted", prefix, left, right, certificate, constants,
             "inconclusive", True, 14, tuple(sorted(EXHAUSTED.items()))),
    ], provenance


def _oracle(case: Case) -> dict:
    truth = phase_delta_oracle.compare(case.prefix, case.left, case.right, case.constants)
    turn = truth["global_turn"]
    return {"inputs": truth["inputs"], "output_mismatches": truth["output_mismatches"],
            "phase_turns": [str(t) for t in truth["phase_turns"]],
            "global_turn": None if turn is None else str(turn)}


def _trial(case: Case, oracle: dict, repetition: int) -> dict:
    """Retain and qualify one trial, including a failed verdict or replay."""
    trial: dict = {"repetition": repetition, "outcome": "error", "reason": None,
                   "receipt": None, "replay": {"status": "not_run", "receipt": None},
                   "failures": []}
    proof = None
    budget = Budget(**dict(case.limits))
    tracemalloc.start()
    start = time.perf_counter()
    try:
        proof = check_program_phase_difference(
            case.prefix, case.left, case.right, case.certificate,
            initial_constants=case.constants, expected_constant=case.expected_constant,
            budget=budget)
        trial.update(outcome=proof.outcome, reason=proof.reason, receipt=proof.to_dict())
    except Exception as error:  # noqa: BLE001 - failed trials must survive in the artifact
        trial["failures"].append({"stage": "verification", "type": type(error).__name__,
                                  "detail": str(error)})
    finally:
        trial["seconds_full_call"] = time.perf_counter() - start
        trial["peak_tracemalloc_bytes"] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

    if trial["outcome"] != case.expected:
        trial["failures"].append({"stage": "expected_outcome", "expected": case.expected,
                                  "observed": trial["outcome"]})
    if (oracle["global_turn"] is not None) != case.claim_true:
        trial["failures"].append({"stage": "fixture_truth",
                                  "detail": "the exhaustive oracle disagrees with claim_true"})
    # Soundness: a proof must state the global turn the exhaustive oracle sees. A refusal or
    # inconclusive result is sound for any claim and is checked only against expectations.
    if (proof is not None and proof.outcome == "proved"
            and oracle["global_turn"] != str(Fraction(proof.constant, 1 << proof.k))):
        trial["failures"].append({"stage": "scalar_oracle",
                                      "detail": "proved constant disagrees with the oracle"})
    if proof is not None:
        try:
            replayed = replay_program_phase_difference(
                case.prefix, case.left, case.right, case.certificate, trial["receipt"],
                initial_constants=case.constants, expected_constant=case.expected_constant,
                budget=Budget(**LIMITS))
            trial["replay"] = {"status": "matched" if replayed == proof else "mismatch",
                               "receipt": replayed.to_dict()}
            if replayed != proof or proof.outcome == "inconclusive":
                trial["failures"].append({"stage": "replay",
                                          "detail": "replay changed or accepted the result"})
        except Exception as error:  # noqa: BLE001 - preserve failed replay evidence too
            refused = (proof.outcome == "inconclusive" and type(error) is ValueError
                       and "no replayable claim" in str(error))
            trial["replay"] = {"status": "refused" if refused else "error", "receipt": None,
                               "type": type(error).__name__, "detail": str(error)}
            if not refused:
                trial["failures"].append({"stage": "replay", "type": type(error).__name__,
                                          "detail": str(error)})
    trial["passed"] = not trial["failures"]
    return trial


def run(repetitions: int = 3) -> dict:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    selected, provenance = cases()
    rows = []
    for case in selected:
        oracle = _oracle(case)
        trials = [_trial(case, oracle, repetition + 1) for repetition in range(repetitions)]
        samples = [trial["seconds_full_call"] for trial in trials]
        outcomes = {trial["outcome"] for trial in trials}
        common_receipt = trials[0]["receipt"]
        if any(trial["receipt"] != common_receipt for trial in trials):
            common_receipt = None
        failures = [{"repetition": trial["repetition"], **failure}
                    for trial in trials for failure in trial["failures"]]
        rows.append({"id": case.name, "expected_outcome": case.expected,
                     "claim_true": case.claim_true, "expected_constant": case.expected_constant,
                     "outcome": next(iter(outcomes)) if len(outcomes) == 1 else "mixed",
                     "passed": all(trial["passed"] for trial in trials), "oracle": oracle,
                     "receipt": common_receipt, "limits": dict(case.limits),
                     "certificate": certificate_to_dict(case.certificate),
                     "prefix": case.prefix.to_dict(), "initial_constants":
                         [list(pair) for pair in case.constants],
                     "repetitions": repetitions, "seconds_full_call": samples,
                     "median_seconds_full_call": statistics.median(samples),
                     "peak_tracemalloc_bytes": max(trial["peak_tracemalloc_bytes"]
                                                   for trial in trials),
                     "failures": failures, "trials": trials})
    return {
        "schema_version": 1, "kind": "symq_phase_delta_binding_qualification",
        "passed": all(row["passed"] for row in rows),
        "failed_trials": sum(not trial["passed"] for row in rows for trial in row["trials"]),
        "scope": "one public prefix, constructed program pairs and adverse cases; exact scalar "
                 "qualification, no speedup claim",
        "machine": machine(), "source": receipt(), "fixture": provenance,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limits": {**LIMITS, "max_seconds_per_full_call": LIMITS["max_seconds"],
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
