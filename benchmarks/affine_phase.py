"""Bounded development qualification of source-bound affine phase derivatives.

All repetitions, failures, whole-call preparation, Python allocation peaks and
source identities are retained. Sign-only cases compare the existing paired
channel checker; dyadic cases have no claimed native general-channel baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import time
import tracemalloc
from collections import Counter
from fractions import Fraction
from pathlib import Path

from symq.errors import ResourceLimitExceeded
from symq.experimental.channel import check_channel
from symq.labs.affine_phase import AffineSupport, check_affine_phase, replay_affine_phase
from symq.labs.dyadic_phase import DyadicPhaseProgram, symbolic
from symq.phase import PhaseProgram
from symq.phase_oracle import run_program
from symq.resources import Budget

from .environment import machine, receipt

CASES = (
    ("parity-dyadic-accepted", 3, 5, "equivalent"),
    ("parity-dyadic-refused", 2, 3, "not_proved"),
    ("correlated-domain-refused", 2, 3, "not_proved"),
    ("offset-domain-global", 2, 3, "equivalent"),
    ("feedback-cancels-dephasing", 2, 3, "not_proved"),
    ("different-output", 3, 3, "not_proved"),
    ("nonlinear-signature", 2, 3, "not_proved"),
    ("singleton-fibres-wide", 18, 20, "equivalent"),
    ("measured-parity-wide", 18, 20, "equivalent"),
    ("unmeasured-expansion-cap", 14, 20, "inconclusive"),
    ("sign-measured-parity", 10, 1, "equivalent"),
    ("sign-unmeasured-parity", 10, 1, "not_proved"),
)

# The derivative checker must decide each case for the expected reason: a refusal
# for another reason (for example a dephaser that does not restore) does not qualify.
_PROVED = "all kernel-basis phase derivatives vanish"
_VARIES = "relative phase varies on a coherence fibre"
EXPECTED_REASON = {
    "parity-dyadic-accepted": _PROVED,
    "parity-dyadic-refused": _VARIES,
    "correlated-domain-refused": _VARIES,
    "offset-domain-global": _PROVED,
    "feedback-cancels-dephasing": _VARIES,
    "different-output": "output functions differ on the support",
    "nonlinear-signature": "dephaser signature is not affine on this support",
    "singleton-fibres-wide": _PROVED,
    "measured-parity-wide": _PROVED,
    "unmeasured-expansion-cap": "terms limit exceeded",
    "sign-measured-parity": _PROVED,
    "sign-unmeasured-parity": _VARIES,
}
_WITNESSED = {_VARIES, "output functions differ on the support"}


def _dephase(width: int, rows: tuple[int, ...]) -> PhaseProgram:
    program = PhaseProgram(width, 1)
    for row in rows:
        for q in range(width):
            if row >> q & 1:
                program.cx(q, width)
        program.hmr(width)
    return program


def _parity_phase(width: int, k: int) -> DyadicPhaseProgram:
    program = DyadicPhaseProgram(width, k=k)
    for q in range(1, width):
        program.cx(q, 0)
    program.phase(0, Fraction(1, 1 << k))
    for q in range(width - 1, 0, -1):
        program.cx(q, 0)
    return program


def build_case(case: tuple) -> tuple:
    name, width, k, _ = case
    left, right, source, support = DyadicPhaseProgram(width, k=k), DyadicPhaseProgram(width, k=k), PhaseProgram(width), None
    max_terms = 4096
    if name in {"singleton-fibres-wide", "measured-parity-wide", "unmeasured-expansion-cap",
                "sign-measured-parity", "sign-unmeasured-parity", "parity-dyadic-accepted"}:
        right = _parity_phase(width, k)
        if name == "singleton-fibres-wide":
            source = _dephase(width, tuple(1 << q for q in range(width)))
        elif name in {"measured-parity-wide", "sign-measured-parity", "parity-dyadic-accepted"}:
            source = _dephase(width, ((1 << width) - 1,))
        elif name == "unmeasured-expansion-cap":
            max_terms = 128
    elif name == "parity-dyadic-refused":
        right.t(0).t(1)
        source = _dephase(width, (3,))
    elif name == "correlated-domain-refused":
        right.z(0)
        support = AffineSupport(width, 0, (3,))
    elif name == "offset-domain-global":
        right.z(0).z(1)
        support = AffineSupport(width, 1, (3,))
    elif name == "feedback-cancels-dephasing":
        right.t(0)
        source = _dephase(width, (1,))
        source.z_if(0, 0)
    elif name == "different-output":
        right.x(0)
        source = _dephase(width, tuple(1 << q for q in range(width)))
    elif name == "nonlinear-signature":
        source = PhaseProgram(width, 1).ccx(0, 1, width)
        source.hmr(width)
    else:
        raise ValueError(name)
    return left, right, source, support, max_terms


def exhaustive_fibre_reference(left, right, source, support) -> bool:
    """Independent concrete branch tables and every coherent pair (small cases only)."""
    width = left.width
    if width > 6:
        raise ValueError("the exhaustive development oracle is bounded to six data wires")
    columns = tuple(1 << q for q in range(width)) if support is None else support.columns
    offset = 0 if support is None else support.offset
    domain = []
    for z in range(1 << len(columns)):
        x = offset
        for j, column in enumerate(columns):
            if z >> j & 1:
                x ^= column
        domain.append(x)
    k, values = max(left.k, right.k), {}
    for x in domain:
        zero = run_program(source, x, 0)
        if len(zero) != 1 or x not in zero or abs(zero[x]) != 1:
            raise ValueError("oracle requires actual restored dephaser outputs")
        signature = 0
        for event in range(source.measurements):
            branch = run_program(source, x, 1 << event)
            if len(branch) != 1 or x not in branch or abs(branch[x]) != 1:
                raise ValueError("malformed dephaser branch")
            signature |= int(branch[x] != zero[x]) << event
        a, pa = left.run(x)
        b, pb = right.run(x)
        if a != b:
            return False
        delta = ((pa << (k - left.k)) - (pb << (k - right.k))) % (1 << k)
        values[x] = signature, delta
    return all(values[x][0] != values[y][0] or values[x][1] == values[y][1]
               for x in domain for y in domain)


def _append_sign(source, suffix):
    program = PhaseProgram(source.data, source.ancillas, list(source.ops))
    if suffix.k != 1:
        raise ValueError("paired sign checker accepts k=1 only")
    for gate in suffix.gates:
        if gate.name == "phase":
            coefficient = gate.angle * 2
            if int(coefficient) % 2:
                program.z(gate.wires[0])
        else:
            program.append(gate.name, *gate.wires)
    return program


def _identities(left, right, source, support) -> str:
    def dyadic(program):
        return [program.width, program.k,
                [[g.name, list(g.wires), str(g.angle)] for g in program.gates]]
    document = [dyadic(left), dyadic(right), source.data, source.ancillas,
                [[op.kind, list(op.qubits), op.outcome] for op in source.ops],
                None if support is None else [support.width, support.offset, list(support.columns)]]
    return hashlib.sha256(json.dumps(document, separators=(",", ":")).encode()).hexdigest()


def _trial(case, method, repetition, allow_native_unavailable=False):
    tracemalloc.start()
    began, cpu = time.perf_counter(), time.process_time()
    started_build = time.perf_counter()
    left, right, source, support, terms = build_case(case)
    build_seconds = time.perf_counter() - started_build
    budget = Budget(max_terms=terms, max_seconds=5.0)
    result, replayed, replay_error, details = None, None, None, {}
    try:
        if method == "derivative":
            result = check_affine_phase(left, right, source, support=support, budget=budget)
            status = result.status
            details = {**result.metrics, "reason": result.reason,
                       "witness": None if result.witness is None else list(result.witness)}
        elif method in {"paired-zdd", "paired-zdd-native"}:
            first, second = _append_sign(source, left), _append_sign(source, right)
            decision = check_channel(first, second, backend=method.removeprefix("paired-"), budget=budget)
            status = "equivalent" if decision.equivalent else "not_proved"
            details = {"reason": decision.reason}
        elif method == "expanded-phase-preparation":
            # This is explicitly a preparation stage, not a competing channel decision.
            phase = symbolic(right, budget)
            status = "prepared"
            details = {"phase_terms": len(phase.phase)}
        else:
            raise ValueError(method)
    except ResourceLimitExceeded as error:
        status, details = "inconclusive", {"reason": str(error)}
    except ImportError as error:
        status, details = "unavailable", {"reason": str(error)}
    except Exception as error:  # noqa: BLE001 -- a measured failure is retained, never called success
        status, details = "error", {"reason": f"{type(error).__name__}: {error}"}
    wall, cpu_seconds = time.perf_counter() - began, time.process_time() - cpu
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    receipt_present = result is not None and result.receipt is not None
    if receipt_present:
        try:
            replayed = replay_affine_phase(left, right, source, result.receipt.to_dict(),
                                          support=support, budget=budget).equivalent is True
        except Exception as error:  # noqa: BLE001 -- retain replay failures and continue the campaign
            replayed = False
            replay_error = f"{type(error).__name__}: {error}"
    elif method == "derivative" and status == "equivalent":
        replayed = False
        replay_error = "equivalent derivative result has no receipt"
    expected = "inconclusive" if method == "expanded-phase-preparation" else case[3]
    passed = status == expected and replayed is not False and replay_error is None
    if method == "derivative" and status == "equivalent":
        passed = passed and receipt_present and replayed is True
    if method == "derivative":
        wanted = EXPECTED_REASON[case[0]]
        reason = details.get("reason")
        passed = passed and type(reason) is str and (
            reason == wanted if wanted in (_PROVED, *_WITNESSED) else reason.startswith(wanted))
        if wanted in _WITNESSED:
            passed = passed and details.get("witness") is not None
    if method == "paired-zdd-native" and status == "unavailable":
        # Retained as unavailable and never counted as a comparison; it only
        # qualifies when the caller explicitly accepts a run without native.
        passed = allow_native_unavailable
    return {"case": case[0], "repetition": repetition, "method": method,
            "source_sha256": _identities(left, right, source, support),
            "expected": expected, "status": status, "qualification_passed": passed,
            "receipt_present": receipt_present, "fresh_replay": replayed,
            "replay_error": replay_error, "wall_seconds": wall, "cpu_seconds": cpu_seconds,
            "preparation_wall_seconds": build_seconds, "python_peak_bytes": peak_bytes,
            "process_maxrss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "budget": {"max_terms": terms, "max_seconds": 5.0}, "details": details}


def _recorded_trial(case, method, repetition, allow_native_unavailable=False):
    """A trial whose own failure (including case construction) is evidence, not a lost run."""
    try:
        return _trial(case, method, repetition, allow_native_unavailable)
    except Exception as error:  # noqa: BLE001 -- recorded as a failed trial, never success
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        return {"case": case[0], "repetition": repetition, "method": method,
                "expected": case[3], "status": "error", "qualification_passed": False,
                "details": {"reason": f"{type(error).__name__}: {error}"}}


def run_qualification(repetitions=3, *, allow_native_unavailable=False):
    if type(repetitions) is not int or not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be an integer in 1..20")
    before = receipt()
    oracles = []
    for case in CASES:
        if case[1] <= 6:
            expected = case[3] == "equivalent" or case[0] == "nonlinear-signature"
            try:
                a, b, source, support, _ = build_case(case)
                actual = exhaustive_fibre_reference(a, b, source, support)
            except Exception as error:  # noqa: BLE001 -- an oracle failure fails the campaign
                oracles.append({"case": case[0], "expected_equivalent": expected,
                                "passed": False, "error": f"{type(error).__name__}: {error}"})
                continue
            oracles.append({"case": case[0], "actual_equivalent": actual,
                            "expected_equivalent": expected, "passed": actual == expected,
                            "source_sha256": _identities(a, b, source, support)})
    tasks = []
    for case in CASES:
        methods = ["derivative"]
        if case[2] == 1:
            methods += ["paired-zdd", "paired-zdd-native"]
        if case[0] in {"singleton-fibres-wide", "measured-parity-wide", "unmeasured-expansion-cap"}:
            methods.append("expanded-phase-preparation")
        tasks.extend((case, method, rep) for rep in range(repetitions) for method in methods)
    random.Random(20261102).shuffle(tasks)
    trials = [_recorded_trial(*task, allow_native_unavailable=allow_native_unavailable)
              for task in tasks]
    after = receipt()
    root = Path(__file__).resolve().parents[1]
    files = ("src/symq/labs/affine_phase.py", "benchmarks/affine_phase.py",
             "tests/testkit/affine_phase_oracle.py")
    fingerprints = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    return {"schema": "symq.affine-phase-qualification/v1", "cohort": "constructed development",
            "untouched_holdout": False, "repetitions": repetitions,
            "allow_native_unavailable": allow_native_unavailable,
            "machine": machine(), "source_before": before, "source_after": after,
            "source_files": fingerprints, "trials": trials, "exhaustive_oracles": oracles,
            "counts": dict(Counter(f"{r['method']}:{r['status']}" for r in trials)),
            "qualification_passed": before == after and all(x["passed"] for x in oracles)
                and all(x["qualification_passed"] for x in trials),
            "limitations": ["development-only constructed families; no general speed ranking",
                            "checker modules are imported before timed trials; source conversion is timed",
                            "timings are instrumented by tracemalloc; not uninstrumented speed claims",
                            "expanded-phase-preparation is not a channel decision baseline",
                            "tracemalloc measures Python allocations, not native manager memory",
                            "process_maxrss_kib is the process-wide high-water mark, not per-trial RSS",
                            "large families use explicit analytic construction, not exhaustive oracles",
                            "all current bases are canonical RREF; no low-weight basis search"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("evidence/affine-phase.json"))
    parser.add_argument("--allow-native-unavailable", action="store_true",
                        help="qualify a run without the native ZDD extension")
    args = parser.parse_args(argv)
    try:
        document = run_qualification(args.repetitions,
                                     allow_native_unavailable=args.allow_native_unavailable)
    except Exception as error:  # noqa: BLE001 -- write the refusal before failing
        document = {"schema": "symq.affine-phase-qualification/v1", "qualification_passed": False,
                    "error": f"{type(error).__name__}: {error}", "trials": [], "counts": {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"qualification_passed": document["qualification_passed"],
                      "trials": len(document["trials"]), "counts": document["counts"]}))
    return 0 if document["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
