"""Development qualification of exact Boolean-first / shift-diagonal ancilla effects.

All cases are explored development inputs, never an untouched holdout. The
comparison is against the pinned in-repository Pauli checker and the bounded
forward density oracle, not the fastest external verification system.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from importlib import metadata
from pathlib import Path

from benchmarks import backward_ancilla as previous
from benchmarks.environment import machine, receipt
from symq.experimental.hybrid import HOp, HybridProgram, coherence_image
from symq.labs import backward_ancilla as pauli
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal
from symq.resources import Budget

ROOT = Path(__file__).resolve().parents[1]
BASELINE_HEAD = "4dacab8a97112826a0db355f6eb31c13e50eb2f2"
BASELINE_PINS = {
    "src/symq/labs/backward_ancilla.py":
        "e4a3ccf64eae3a84bf785cbdaa2e81f745a4127f17e740b42757620f01ec566e",
    "benchmarks/backward_ancilla.py":
        "c404849f99e0aae5cba275672e20788974d27cd839665426071510c07967d9c4",
}
METHODS = ("pauli", "shift_diagonal", "density")


@dataclass(frozen=True)
class Case:
    name: str
    family: str
    program: HybridProgram
    target: int
    expected: str
    origin: str = "constructed development example"
    max_terms: int = 4096
    limits: pauli.AncillaLimits = field(default_factory=pauli.AncillaLimits)
    shift_expected: str | None = None


def _controlled(program: HybridProgram, wires: list[int], condition: str | None = None) -> None:
    name = {1: "x", 2: "cx", 3: "ccx"}.get(len(wires), "mcx")
    getattr(program, name)(*wires, condition=condition)


def cases() -> tuple[list[Case], list[dict]]:
    public, sources = previous._public_cases()
    result = [Case(c.name, "public_qualtran", c.program, c.target, c.expected, c.origin)
              for c in public]
    for controls in (2, 3, 5):
        wires = list(range(controls + 1))
        program = HybridProgram(controls, 1).mcx(*wires).x(0).mcx(*wires).mcx(
            *wires[1:]).x(0)
        result.append(Case(f"changed-controls-{controls}", "changed_controls", program,
                           controls, "clean"))
        mutant = HybridProgram(controls, 1, program.ops[:3] + program.ops[4:])
        result.append(Case(f"changed-controls-{controls}-missing-compensation", "changed_controls",
                           mutant, controls, "not_clean"))
    for controls in (2, 4, 5):
        target = controls + 1
        wires = [*range(controls), target]
        program = HybridProgram(controls + 1, 1).mcx(*wires).cx(target, controls).mcx(*wires)
        result.append(Case(f"compute-use-uncompute-{controls}", "compute_use", program,
                           target, "clean"))
        result.append(Case(f"compute-use-uncompute-{controls}-missing-cleanup", "compute_use",
                           HybridProgram(program.data, 1, program.ops[:-1]), target, "not_clean"))
    for controls in (1, 3, 5):
        program = HybridProgram(controls, 1)
        _controlled(program, list(range(controls + 1)))
        program.measure_z(0, "b0")
        _controlled(program, list(range(1, controls + 1)), "b0")
        result.append(Case(f"measured-control-{controls}", "measurement_correlation", program,
                           controls, "clean"))
        overwritten = HybridProgram(controls, 1, program.ops[:-1] + [
            HOp("store", (), slot="b0", value=0)] + program.ops[-1:])
        result.append(Case(f"measured-control-{controls}-overwritten-slot", "measurement_correlation",
                           overwritten, controls, "not_clean"))
    for controls in (2, 3, 5):
        program = HybridProgram(controls, 1).mcx(*range(controls + 1)).cz(0, 1).hmr(
            0, "b0").x(controls, condition="b0")
        result.append(Case(f"coherent-feedback-{controls}", "coherent_feedback", program,
                           controls, "not_clean"))
    routed = HybridProgram(3, 2).cx(0, 3).cx(1, 4).cswap(2, 3, 4).cswap(2, 0, 1).cx(
        0, 3).cx(1, 4)
    result.append(Case("conditional-routing", "conditional_routing", routed, 3, "clean"))
    mutant = HybridProgram(3, 2, routed.ops[:3] + routed.ops[4:])
    result.append(Case("conditional-routing-missing-data-route", "conditional_routing", mutant,
                       3, "not_clean"))
    for parity in (2, 4, 8):
        program = HybridProgram(parity + 1, 1).hmr(0, "b0")
        for q in range(1, parity + 1):
            program.cx(q, parity + 1)
        program.x(parity + 1, condition="b0")
        result.append(Case(f"parity-hmr-{parity}", "parity_hmr_boundary", program,
                           parity + 1, "not_clean"))
        if parity == 8:
            result.append(Case("parity-hmr-8-cap64", "parity_hmr_boundary", program,
                               parity + 1, "not_clean", max_terms=64,
                               shift_expected="inconclusive"))
    return result, sources


def _identity() -> dict:
    source_hashes = {}
    files = (*BASELINE_PINS, "src/symq/labs/shift_diagonal_ancilla.py",
             "src/symq/experimental/hybrid.py", "src/symq/resources.py",
             "benchmarks/shift_diagonal_ancilla.py")
    for name in files:
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        source_hashes[name] = digest
        if name in BASELINE_PINS and digest != BASELINE_PINS[name]:
            raise ValueError(f"pinned baseline source changed: {name}")
    versions = {}
    for name in ("symq", "pytest", "hypothesis", "ruff", "python-sat"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {"stacked_on_pr": 145, "baseline_head": BASELINE_HEAD,
            "baseline_pin_status": "exact file bytes verified",
            "source_sha256": source_hashes, "dependencies": versions}


def _source_hash(case: Case) -> str:
    rows = [[op.kind, list(op.wires), op.slot, op.condition, op.source, op.value]
            for op in case.program.ops]
    raw = json.dumps({"data": case.program.data, "ancillas": case.program.ancillas, "ops": rows},
                     sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _check_pauli(case: Case, seconds: float) -> dict:
    result = pauli.check_clean_ancilla(case.program, case.target,
                                     budget=Budget(max_terms=case.max_terms, max_seconds=seconds),
                                     limits=case.limits)
    return {"status": result.status, "reason": result.reason, "peak_terms": result.peak_terms,
            "products": result.pauli_products, "checked_operations": result.checked_operations,
            "certificate": result.certificate.to_dict() if result.certificate else None,
            "witness": ({"assignment": result.witness.assignment,
                         "probability": str(result.witness.probability)} if result.witness else None)}


def _check_shift(case: Case, seconds: float) -> dict:
    result = check_shift_diagonal(case.program, case.target,
                                 budget=Budget(max_terms=case.max_terms, max_seconds=seconds),
                                 limits=case.limits)
    return {"status": result.status, "reason": result.reason, "source_sha256": result.source_sha256,
            "peak_terms": result.peak_terms, "peak_shifts": result.peak_shifts,
            "products": result.products, "promotions": result.promotions, "mode": result.mode,
            "checked_operations": result.checked_operations,
            "witness": ({"assignment": result.assignment, "probability": str(result.probability)}
                        if result.assignment is not None else None)}


def _probability(case: Case, assignment: int, deadline: float) -> Fraction:
    image = coherence_image(case.program, assignment, assignment, max_width=6,
                            budget=Budget(max_terms=case.max_terms, absolute_deadline=deadline))
    return sum((c for (a, b), c in image.items() if a == b and a >> case.target & 1), Fraction(0))


def _density(case: Case, seconds: float) -> dict:
    if case.program.width > 6:
        return {"status": "unsupported", "reason": "declared density width cap 6",
                "checked_basis_inputs": 0}
    deadline = time.perf_counter() + seconds
    for assignment in range(1 << case.program.data):
        probability = _probability(case, assignment, deadline)
        if probability:
            return {"status": "not_clean", "checked_basis_inputs": assignment + 1,
                    "witness": {"assignment": assignment, "probability": str(probability)}}
    return {"status": "clean", "checked_basis_inputs": 1 << case.program.data}


def _witness_check(case: Case, witness: dict | None, seconds: float) -> dict:
    if witness is None:
        return {"status": "not_applicable"}
    if case.program.width > 6:
        return {"status": "unsupported", "reason": "declared density width cap 6"}
    probability = _probability(case, witness["assignment"], time.perf_counter() + seconds)
    valid = probability > 0 and str(probability) == witness["probability"]
    return {"status": "verified" if valid else "rejected", "probability": str(probability)}


def _summary(trials: list[dict]) -> dict:
    summary = {"status_counts": {name: dict(Counter(t[name]["status"] for t in trials))
                                 for name in METHODS}, "cases": []}
    for case in dict.fromkeys(t["case"] for t in trials):
        rows = [t for t in trials if t["case"] == case]
        medians = {name: statistics.median(t[name]["wall_seconds"] for t in rows)
                   for name in METHODS}
        paired = [t["pauli"]["wall_seconds"] / t["shift_diagonal"]["wall_seconds"] for t in rows
                  if t["passed"] and t["pauli"]["status"] == t["shift_diagonal"]["status"]
                  and t["pauli"]["status"] in {"clean", "not_clean"}]
        summary["cases"].append({"case": case, "family": rows[0]["family"],
                                 "median_wall_seconds": medians, "successful_paired_ratios": paired})
    return summary


def run(*, repetitions: int = 3, seconds: float = 10) -> dict:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    Budget(max_seconds=seconds)
    report = {"schema_version": 1, "scope": "one final zero ancilla; no data-channel identity",
              "cohort": "explored development only; no holdout or external SOTA claim",
              "machine": machine(), "code": receipt(), "trials": [],
              "measurement": "whole public calls including source snapshots, lifts, witnesses and cleanup; "
                             "JSON encoding excluded; shared case construction separately measured",
              "memory": "Python traced peak per call; RSS is cumulative process high-water",
              "new_api": "research result only; no portable certificate or replay API",
              "limits": {"seconds_per_call": seconds, "default_terms": 4096, "density_width": 6,
                         "structural_default": asdict(pauli.AncillaLimits()),
                         "term_units": "representation-specific explicit terms, not equivalent work"},
              "qualification_passed": False}
    try:
        report["provenance"] = _identity()
        built, setup = previous._timed(cases)
        report["shared_case_construction"] = setup
        if built is None or "error" in setup:
            raise ValueError("case construction failed; see retained setup error and cost")
        selected, sources = built
        report["public_sources"] = sources
    except (OSError, ValueError, TypeError) as error:
        report["setup_error"] = f"{type(error).__name__}: {error}"
        return report
    for case_index, case in enumerate(selected):
        for repetition in range(repetitions):
            offset = (case_index + repetition) % len(METHODS)
            order = METHODS[offset:] + METHODS[:offset]
            trial = {"case": case.name, "family": case.family, "origin": case.origin,
                     "repetition": repetition, "order": list(order), "data": case.program.data,
                     "ancillas": case.program.ancillas, "target": case.target,
                     "operations": len(case.program.ops), "program_sha256": _source_hash(case),
                     "expected": {"pauli": case.expected,
                                  "shift_diagonal": case.shift_expected or case.expected,
                                  "density": case.expected if case.program.width <= 6 else "unsupported"},
                     "max_terms": case.max_terms, "limits": asdict(case.limits), "passed": False}
            functions = {"pauli": lambda case=case: _check_pauli(case, seconds),
                         "shift_diagonal": lambda case=case: _check_shift(case, seconds),
                         "density": lambda case=case: _density(case, seconds)}
            for name in order:
                value, timing = previous._timed(functions[name])
                trial[name] = {**(value or {"status": "error"}), **timing}
            checks_ok = all("error" not in trial[name] for name in METHODS)
            # These independent checks have separate costs, outside all three primary calls.
            trial["witness_checks"] = {}
            for name in ("pauli", "shift_diagonal"):
                value, timing = previous._timed(lambda name=name, case=case, trial=trial: _witness_check(
                    case, trial[name].get("witness"), seconds))
                trial["witness_checks"][name] = {**(value or {"status": "error"}), **timing}
                checks_ok &= value is not None and value["status"] not in {"rejected", "error"}
                if trial[name]["status"] == "not_clean" and not trial[name].get("witness"):
                    checks_ok = False
            certificate = trial["pauli"].get("certificate")
            if trial["pauli"]["status"] == "clean" and not certificate:
                trial["pauli_fresh_replay"] = {
                    "status": "missing_certificate",
                    "reason": "clean Pauli result omitted its required replay certificate",
                }
                checks_ok = False
            elif certificate:
                value, timing = previous._timed(lambda case=case, certificate=certificate: pauli.replay_clean_ancilla(
                    case.program, certificate, target=case.target,
                    budget=Budget(max_seconds=seconds, max_terms=case.max_terms), limits=case.limits))
                trial["pauli_fresh_replay"] = {"status": value.status if value else "error", **timing}
                checks_ok &= value is not None and value.clean
            shifted = trial["shift_diagonal"]
            if shifted["status"] in {"clean", "not_clean"}:
                checks_ok &= shifted.get("source_sha256") == trial["program_sha256"]
            else:
                checks_ok &= shifted.get("witness") is None
            trial["passed"] = bool(checks_ok and all(trial[name]["status"] == trial["expected"][name]
                                                    for name in METHODS))
            report["trials"].append(trial)
    report["summary"] = _summary(report["trials"])
    report["qualification_passed"] = bool(report["trials"]) and all(t["passed"] for t in report["trials"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(repetitions=args.repetitions, seconds=args.seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if report["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
