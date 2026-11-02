"""Development qualification of targeted clean-ancilla proofs, never a holdout.

The independent baseline uses exact forward density evolution on basis inputs.
Positivity makes those diagonal tests sufficient for this ONE clean-ancilla
property; they would not suffice for general channel equality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path

from benchmarks.environment import machine, receipt
from symq.experimental.hybrid import HybridProgram, coherence_image
from symq.labs.backward_ancilla import (
    AncillaLimits,
    check_clean_ancilla,
    replay_clean_ancilla,
)
from symq.labs.importers import parse_phase_stream
from symq.labs.qualtran import load_qualtran_fixture
from symq.phase import PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded

ROOT = Path(__file__).resolve().parents[1]
PINS = {1: "65ddd0635f42eb01e03ceffdd2ed13b9f2134571",
        2: "4bddfc240a3221372e04af5af70f4b13dee4bbd5"}


@dataclass(frozen=True)
class Case:
    name: str
    program: HybridProgram
    target: int
    expected: str
    origin: str = "constructed development example"
    limits: AncillaLimits = field(default_factory=AncillaLimits)
    oracle_expected: str | None = None


def _hybrid(program: PhaseProgram) -> HybridProgram:
    """Explicit lowering of the already authenticated strict sign/HMR fixture."""
    program.validate()
    out = HybridProgram(program.data, program.ancillas)
    for op in program.ops:
        if op.kind == "mcx":
            name = {1: "x", 2: "cx", 3: "ccx"}.get(len(op.qubits), "mcx")
            getattr(out, name)(*op.qubits)
        elif op.kind == "hmr":
            out.hmr(op.qubits[0], f"b{op.outcome}")
        elif op.kind in {"mcz", "mcz_if"}:
            name = {1: "z", 2: "cz", 3: "ccz"}.get(len(op.qubits))
            if name is None:
                raise ValueError("fixture phase has more than three controls")
            getattr(out, name)(*op.qubits,
                               condition=f"b{op.outcome}" if op.kind == "mcz_if" else None)
        else:
            raise ValueError("fixture outside strict sign/HMR grammar")
    return out


def _public_cases() -> tuple[list[Case], list[dict]]:
    cases, sources = [], []
    for degree, expected in PINS.items():
        path = ROOT / f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json"
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != expected:
            raise ValueError(f"public fixture m={degree} differs from its pinned Git blob")
        fixture = load_qualtran_fixture(path)
        reference, candidate = fixture.programs()
        no_phase = PhaseProgram(candidate.data, candidate.ancillas,
                                [op for op in candidate.ops if op.kind != "mcz_if"])
        no_cleanup = parse_phase_stream(fixture.preparer, data=candidate.data,
                                       ancillas=candidate.ancillas).program
        for tag, phase, verdict in (("inverse", reference, "clean"),
                                    ("hmr", candidate, "clean"),
                                    ("missing-phase-still-clean", no_phase, "clean"),
                                    ("missing-cleanup", no_cleanup, "not_clean")):
            for target in range(candidate.data, candidate.width):
                cases.append(Case(f"qualtran-m{degree}-{tag}-q{target}", _hybrid(phase),
                                  target, verdict, f"public Qualtran m={degree}; {tag}"))
        sources.append({"path": path.relative_to(ROOT).as_posix(), "git_blob_sha1": blob,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "upstream": json.loads(fixture.provenance_json),
                        "role": "already explored public development fixture; not a holdout"})
    return cases, sources


def cases() -> tuple[list[Case], list[dict]]:
    result, sources = _public_cases()
    correlated = HybridProgram(1, 1).cx(0, 1).measure_z(0, "b0").x(1, condition="b0")
    result.extend([
        Case("relational-measurement-cleanup", correlated, 1, "clean"),
        Case("missing-classical-correction", HybridProgram(1, 1, correlated.ops[:-1]),
             1, "not_clean"),
        Case("hmr-random-value-feedback", HybridProgram(1, 1).hmr(0, "b0").x(
            1, condition="b0"), 1, "not_clean"),
        Case("reset-with-data-decoherence", HybridProgram(1, 1).cx(0, 1).reset(1), 1, "clean"),
        Case("overwritten-measurement-slot", HybridProgram(1, 1).measure_z(0, "b0").x(
            1, condition="b0").store("b0", 0).x(1, condition="b0"), 1, "not_clean"),
    ])
    for data in (2, 3, 4, 5):
        program = HybridProgram(data, 1).mcx(*range(data + 1)).mcx(*range(data + 1))
        result.append(Case(f"controlled-uncompute-{data}", program, data, "clean"))
    wide = HybridProgram(128, 1)
    for q in range(120):
        wide.cx(q, q + 1)
    wide.cx(0, 128).cx(0, 128)
    result.append(Case("wide-irrelevant-cone", wide, 128, "clean", oracle_expected="unsupported"))
    hard = HybridProgram(8, 1).mcx(*range(9)).mcx(*range(9))
    result.append(Case("controlled-expansion-work-cap", hard, 8, "inconclusive",
                       limits=AncillaLimits(max_products=1000), oracle_expected="unsupported"))
    return result, sources


def _oracle(case: Case, seconds: float) -> dict:
    program = case.program
    if program.width > 6:
        return {"status": "unsupported", "reason": "declared density oracle width cap 6",
                "checked_basis_inputs": 0}
    checked = 0
    deadline = time.perf_counter() + seconds
    for assignment in range(1 << program.data):
        matrix = coherence_image(program, assignment, assignment, max_width=6,
                                 budget=Budget(absolute_deadline=deadline, max_terms=65536))
        probability = sum((value for (row, col), value in matrix.items()
                           if row == col and row >> case.target & 1), Fraction(0))
        checked += 1
        if probability:
            return {"status": "not_clean", "checked_basis_inputs": checked,
                    "witness": assignment, "probability": str(probability)}
    return {"status": "clean", "checked_basis_inputs": checked}


def _timed(function):
    tracemalloc.start()
    started, cpu = time.perf_counter(), time.process_time()
    value, error_text = None, None
    try:
        value = function()
    except Exception as error:  # noqa: BLE001 -- failed trials are recorded and fail qualification.
        error_text = f"{type(error).__name__}: {error}"
    finally:
        elapsed, consumed = time.perf_counter() - started, time.process_time() - cpu
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    timing = {"wall_seconds": elapsed, "cpu_seconds": consumed, "peak_python_bytes": peak,
              "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
              / (1024 if sys.platform == "darwin" else 1)}
    if error_text:
        timing["error"] = error_text
    return value, timing


def _check(case: Case, seconds: float) -> dict:
    result = check_clean_ancilla(case.program, case.target,
                                 budget=Budget(max_terms=4096, max_seconds=seconds), limits=case.limits)
    return {"status": result.status, "reason": result.reason, "peak_terms": result.peak_terms,
            "pauli_products": result.pauli_products, "checked_operations": result.checked_operations,
            "certificate": result.certificate.to_dict() if result.certificate else None,
            "witness": ({"assignment": result.witness.assignment,
                         "probability": str(result.witness.probability)} if result.witness else None)}


def run(*, repetitions: int = 3, seconds: float = 10) -> dict:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    Budget(max_seconds=seconds)
    report = {"schema_version": 1, "scope": "one final clean ancilla; not channel equality",
              "cohort": "development only", "machine": machine(), "code": receipt(),
              "measurement": "complete public calls with tracemalloc; result JSON encoding excluded",
              "memory": "Python traced peak per call; RSS is process cumulative high-water, not per-call",
              "limits": {"max_terms": 4096, "max_seconds_per_call": seconds,
                         "oracle_max_width": 6, "structural_default": asdict(AncillaLimits())},
              "trials": [], "qualification_passed": False}
    try:
        selected, sources = cases()
        report["public_sources"] = sources
    except (OSError, ValueError, TypeError) as error:
        report["setup_error"] = f"{type(error).__name__}: {error}"
        return report
    for case in selected:
        for repetition in range(repetitions):
            trial = {"case": case.name, "repetition": repetition, "origin": case.origin,
                     "data": case.program.data, "ancillas": case.program.ancillas,
                     "target": case.target, "operations": len(case.program.ops),
                     "expected": case.expected, "limits": asdict(case.limits), "passed": False}
            try:
                # Alternate paired order; setup/conversion is outside both timed public calls.
                functions = {"backward": lambda case=case: _check(case, seconds),
                             "oracle": lambda case=case: _oracle(case, seconds)}
                for name in (("backward", "oracle") if repetition % 2 == 0 else
                             ("oracle", "backward")):
                    value, timing = _timed(functions[name])
                    trial[name] = {**(value or {"status": "error"}), **timing}
                if any("error" in trial[name] for name in ("backward", "oracle")):
                    raise RuntimeError("a timed proof call failed; see its retained error and cost")
                checked = trial["backward"]
                # A positive needs its receipt and a negative its witness: a bare
                # status never qualifies.
                replay_ok = {"clean": checked["certificate"] is not None,
                             "not_clean": checked["witness"] is not None}.get(
                                 checked["status"], True)
                if checked["certificate"]:
                    replay, timing = _timed(lambda case=case, checked=checked: replay_clean_ancilla(
                        case.program, checked["certificate"], target=case.target,
                        budget=Budget(max_seconds=seconds), limits=case.limits))
                    trial["replay"] = {"status": replay.status if replay else "error", **timing}
                    replay_ok = replay_ok and replay is not None and replay.clean
                if checked["witness"] and case.program.width > 6:
                    # The independent dense check is capped; an unchecked witness fails.
                    trial["witness_replayed"] = None
                    replay_ok = False
                elif checked["witness"]:
                    witness = checked["witness"]
                    matrix = coherence_image(case.program, witness["assignment"],
                                             witness["assignment"], max_width=6,
                                             budget=Budget(max_seconds=seconds))
                    probability = sum((c for (a, b), c in matrix.items()
                                       if a == b and a >> case.target & 1), Fraction(0))
                    trial["witness_replayed"] = probability > 0 and str(probability) == witness[
                        "probability"]
                    replay_ok = replay_ok and trial["witness_replayed"]
                expected_oracle = case.oracle_expected or case.expected
                trial["passed"] = (checked["status"] == case.expected and replay_ok and
                                   trial["oracle"]["status"] == expected_oracle)
            except (ValueError, TypeError, ResourceLimitExceeded, RuntimeError) as error:
                trial["error"] = f"{type(error).__name__}: {error}"
            report["trials"].append(trial)
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
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
