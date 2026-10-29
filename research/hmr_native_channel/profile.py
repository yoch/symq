"""Per-phase cost profile of the native HMR full-channel checker.

`check_full_channel` is one opaque call. This module repeats the exact same algorithm while timing
each stage, so a measured speedup can be attributed to a *stage* instead of to "the native engine".

The six stages are the ones the mission names:

1. ``outputs_x`` — build the symbolic output functions ``F(x)`` for the left program.
2. ``phase0_x`` — build the measurement-free phase ``phi0(x)`` and the coefficient functions.
   The checker computes ``phi0`` and every ``g_j`` in a single pass over the operations, so the
   split below is by *operation class* (``mcz`` versus ``hmr``/``mcz_if``) inside that pass.
3. ``outputs_y`` — rebuild the second coherent half on the ``y`` variables.
4. ``kernels`` — build ``[g(x) = g(y)]`` for both programs and compare them.
5. ``phases`` — compare relative phases on the surviving coherences.
6. ``witness`` — extract and independently replay a concrete witness when something differs.

## What this instrumentation may and may not claim

Timing individual ZDD operations measures the *existing* algorithm. It does not by itself prove that
a proposed simplification is free: a phase that is zero at the end may still have cost work in the
middle. The ``null_phase`` counter in the state report exists precisely to keep that distinction
visible.

The instrumented path is checked against ``check_full_channel`` on every case: the verdict must be
identical, or the profile is not reported.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from research.hmr_native_channel.native_channel import (
    ChannelDecision,
    _kernel,
    _scalar,
    _scalar_kernel,
    _sha,
    _State,
    check_full_channel,
)
from symq.backends import make_algebra
from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard

STAGES = (
    "outputs_x",
    "phase0_x",
    "coefficients_x",
    "outputs_y",
    "phase0_y",
    "coefficients_y",
    "kernels",
    "phases",
    "witness",
)


@dataclass
class StageTimes:
    """Seconds per stage, plus the operation counts that explain them."""

    outputs_x: float = 0.0
    phase0_x: float = 0.0
    coefficients_x: float = 0.0
    outputs_y: float = 0.0
    phase0_y: float = 0.0
    coefficients_y: float = 0.0
    kernels: float = 0.0
    phases: float = 0.0
    witness: float = 0.0
    total: float = 0.0

    def add(self, stage: str, seconds: float) -> None:
        setattr(self, stage, getattr(self, stage) + seconds)


@dataclass
class WorkCounters:
    """How much symbolic work each stage actually did."""

    variables: int = 0
    data: int = 0
    events: int = 0
    operations: int = 0
    mcz_ops: int = 0
    hmr_ops: int = 0
    mcz_if_ops: int = 0
    products: int = 0
    xors: int = 0
    is_zero_calls: int = 0
    min_monomial_calls: int = 0
    kernel_rounds: int = 0
    zero_phase_final: bool | None = None
    zero_coefficients_final: bool | None = None
    """Both flags describe the *final* expressions, not the intermediate cost."""

    def merge(self, other: WorkCounters) -> None:
        for name in (
            "variables",
            "data",
            "events",
            "operations",
            "mcz_ops",
            "hmr_ops",
            "mcz_if_ops",
            "products",
            "xors",
            "is_zero_calls",
            "min_monomial_calls",
            "kernel_rounds",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class Profile:
    case: str
    left: str
    right: str
    backend: str
    expected: str
    observed: str
    matched: bool
    stages: StageTimes
    work: WorkCounters
    peak_terms: int | None = None
    terms_after: dict[str, int | None] = field(default_factory=dict)


class _Timer:
    """Adds elapsed time to one named stage.

    ``with timer.stage("outputs_x"): ...`` nests, so a stage inside another is measured on both
    clocks; the outer one then includes the inner. Only the leaf stages are reported.
    """

    def __init__(self, stages: StageTimes) -> None:
        self.stages = stages

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.stages.add(name, time.perf_counter() - started)


class _CountingAlgebra:
    """Proxy that counts the two operations which dominate cost, without changing semantics."""

    def __init__(self, inner: Any, work: WorkCounters) -> None:
        self._inner = inner
        self._work = work

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def stats(self) -> Any:
        return self._inner.stats

    def product(self, *args: Any, **kwargs: Any) -> Any:
        self._work.products += 1
        return self._inner.product(*args, **kwargs)

    def xor(self, *args: Any, **kwargs: Any) -> Any:
        self._work.xors += 1
        return self._inner.xor(*args, **kwargs)

    def is_zero(self, value: Any) -> bool:
        self._work.is_zero_calls += 1
        return self._inner.is_zero(value)

    def min_monomial(self, value: Any) -> Any:
        self._work.min_monomial_calls += 1
        return self._inner.min_monomial(value)

    def terms(self, value: Any) -> int | None:
        return self._inner.terms(value)


def _profile_symbolic(
    program: PhaseProgram,
    algebra: Any,
    offset: int,
    guard: Guard,
    timer: _Timer,
    counts: WorkCounters,
    suffix: str,
) -> _State:
    """The same loop as ``_symbolic``, with the phase work separated from the value work."""
    data = program.data
    state = [
        algebra.variable(offset + q) if q < data else algebra.zero()
        for q in range(program.width)
    ]
    phi0 = algebra.zero()
    coefficients: list[Any] = []
    for op in program.ops:
        guard.check_time()
        if op.kind == "mcx":
            with timer.stage(f"outputs_{suffix}"):
                *controls, target = op.qubits
                product = algebra.product([state[q] for q in controls])
                state[target] = algebra.xor(state[target], product)
            counts.products += 1
            counts.xors += 1
        elif op.kind == "mcz":
            with timer.stage(f"phase0_{suffix}"):
                sign = algebra.product([state[q] for q in op.qubits])
                phi0 = algebra.xor(phi0, sign)
            counts.products += 1
            counts.xors += 1
            counts.mcz_ops += 1
        elif op.kind == "hmr":
            if op.outcome != len(coefficients):
                raise UnsupportedOperation("non-fresh HMR event")
            with timer.stage(f"coefficients_{suffix}"):
                coefficients.append(state[op.qubits[0]])
                state[op.qubits[0]] = algebra.zero()
            counts.hmr_ops += 1
        elif op.kind == "mcz_if":
            if op.outcome is None or op.outcome >= len(coefficients):
                raise UnsupportedOperation("uninitialized HMR feedback")
            with timer.stage(f"coefficients_{suffix}"):
                sign = algebra.product([state[q] for q in op.qubits])
                coefficients[op.outcome] = algebra.xor(coefficients[op.outcome], sign)
            counts.products += 1
            counts.xors += 1
            counts.mcz_if_ops += 1
        else:
            raise UnsupportedOperation(f"outside sign/HMR grammar: {op.kind!r}")
        guard.check_time()
    counts.operations += len(program.ops)
    return _State(tuple(state), phi0, tuple(coefficients))


def profile_channel(
    left: PhaseProgram,
    right: PhaseProgram,
    *,
    backend: str = "zdd-native",
    budget: Budget | None = None,
) -> Profile:
    """Run the same theorem as ``check_full_channel``, stage by stage, and verify the verdict matches."""
    if type(left) is not PhaseProgram or type(right) is not PhaseProgram:
        raise TypeError("two PhaseProgram instances required")
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("matching data and ancilla widths required")
    reference: ChannelDecision = check_full_channel(
        left, right, backend=backend, budget=budget
    )

    stages = StageTimes()
    counts = WorkCounters(data=left.data, variables=2 * left.data)
    counts.events = left.measurements + right.measurements
    timer = _Timer(stages)
    guard = Guard(budget)
    started = time.perf_counter()
    algebra = _CountingAlgebra(
        make_algebra(backend, 2 * left.data, budget), counts
    )
    mask = (1 << left.data) - 1

    with timer.stage("outputs_x"):
        lx = _profile_symbolic(left, algebra, 0, guard, timer, counts, "x")
    with timer.stage("outputs_y"):
        ly = _profile_symbolic(left, algebra, left.data, guard, timer, counts, "y")
    with timer.stage("outputs_y"):
        rx = _profile_symbolic(right, algebra, 0, guard, timer, counts, "x")
    with timer.stage("outputs_y"):
        ry = _profile_symbolic(right, algebra, right.data, guard, timer, counts, "y")

    observed = "equivalent"
    witness: tuple[int, int] | None = None
    witness_wire: int | None = None
    witness_kind: str | None = None
    with timer.stage("kernels"):
        for wire, (a, b) in enumerate(zip(lx.outputs, rx.outputs)):
            difference = algebra.xor(a, b)
            if not algebra.is_zero(difference):
                observed = f"output_difference:{wire}"
                witness_wire = wire
                witness_kind = "input"
                found = algebra.min_monomial(difference)
                if found is None:
                    raise RuntimeError("nonzero output difference has no witness")
                assignment = found & mask
                witness = (assignment, assignment)
                break
    if observed == "equivalent":
        with timer.stage("kernels"):
            kl = _kernel(algebra, lx, ly, guard)
            kr = _kernel(algebra, rx, ry, guard)
            counts.kernel_rounds += len(lx.outcome_coefficients)
            kernel_mismatch = algebra.xor(kl, kr)
            kernel_differs = not algebra.is_zero(kernel_mismatch)
        if kernel_differs:
            observed = "kernel_difference"
            witness_kind = "coherence"
            with timer.stage("witness"):
                found = algebra.min_monomial(kernel_mismatch)
                if found is not None:
                    witness = (found & mask, (found >> left.data) & mask)
        else:
            with timer.stage("phases"):
                phase_x = algebra.xor(lx.phase0, rx.phase0)
                phase_y = algebra.xor(ly.phase0, ry.phase0)
                mismatch = algebra.product((kl, algebra.xor(phase_x, phase_y)))
                phase_differs = not algebra.is_zero(mismatch)
            if phase_differs:
                observed = "phase_difference"
                witness_kind = "phase"
                with timer.stage("witness"):
                    found = algebra.min_monomial(mismatch)
                    if found is not None:
                        witness = (found & mask, (found >> left.data) & mask)

    if witness is not None and witness_kind is not None:
        with timer.stage("witness"):
            _replay(left, right, witness, kind=witness_kind, wire=witness_wire)
    stages.total = time.perf_counter() - started

    counts.zero_phase_final = algebra.is_zero(lx.phase0) and algebra.is_zero(rx.phase0)
    counts.zero_coefficients_final = all(
        algebra.is_zero(coefficient)
        for coefficient in (
            lx.outcome_coefficients + ly.outcome_coefficients
            + rx.outcome_coefficients + ry.outcome_coefficients
        )
    )
    terms_after = {
        "kernel_x": algebra.terms(_kernel(algebra, lx, ly, guard)),
    }
    try:
        stats = algebra.stats
        peak_terms = getattr(stats, "peak_terms", None)
    except Exception:  # noqa: BLE001 - stats are optional diagnostics
        peak_terms = None

    expected = "equivalent" if reference.equivalent else (reference.witness_kind or "different")
    matched = (reference.equivalent and observed == "equivalent") or (
        not reference.equivalent and observed != "equivalent"
    )
    return Profile(
        case=f"{left.data}d/{left.measurements}e/{backend}",
        left=_sha(left),
        right=_sha(right),
        backend=backend,
        expected=expected,
        observed=observed,
        matched=matched,
        stages=stages,
        work=counts,
        peak_terms=peak_terms,
        terms_after=terms_after,
    )


def _replay(
    left: PhaseProgram,
    right: PhaseProgram,
    witness: tuple[int, int],
    *,
    kind: str,
    wire: int | None = None,
) -> None:
    """Independent integer replay of a witness, with the check appropriate to the difference.

    An output difference is one basis input; a kernel difference has *unequal* kernel booleans; a
    phase difference has *equal* kernels and unequal relative phases. Applying the kernel test to a
    phase witness would reject every valid one, which is exactly the mistake this signature prevents.
    """
    x, y = witness
    if kind == "input":
        if wire is None:
            raise ValueError("an output witness needs its wire")
        if (_scalar(left, x)[0] >> wire & 1) == (_scalar(right, x)[0] >> wire & 1):
            raise RuntimeError("profiled output witness fails independent integer replay")
        return
    if kind == "coherence":
        if _scalar_kernel(left, x, y) == _scalar_kernel(right, x, y):
            raise RuntimeError("profiled kernel witness fails independent scalar replay")
        return
    if kind == "phase":
        if _scalar_kernel(left, x, y) is not True or _scalar_kernel(right, x, y) is not True:
            raise RuntimeError("a phase witness must survive both kernels")
        phase_left = _scalar(left, x)[1] ^ _scalar(left, y)[1]
        phase_right = _scalar(right, x)[1] ^ _scalar(right, y)[1]
        if phase_left == phase_right:
            raise RuntimeError("profiled phase witness fails independent scalar replay")
        return
    raise ValueError(f"unknown witness kind {kind!r}")


def cases() -> dict[str, tuple[PhaseProgram, PhaseProgram]]:
    """The seven comparison kinds the mission asks for, built with the public program API.

    Every pair is checked by ``check_full_channel`` first; ``profile_channel`` only reports a profile
    when its own verdict agrees with that reference.
    """
    from research.hmr_native_channel.benchmark import case as family

    def repaired(data: int, hmr: int) -> tuple[PhaseProgram, PhaseProgram]:
        return family(data, hmr, "nonlinear")

    def unrepaired(data: int, hmr: int) -> PhaseProgram:
        """Same values and same kernel as the reference, but the CZ repair is missing."""
        import random

        program = PhaseProgram(data, 1)
        rng = random.Random(20261029)
        for _ in range(hmr):
            a, b, target = rng.sample(range(data), 3)
            program.ccx(a, b, target)
            program.ccx(a, b, data)
            program.hmr(data)
        return program

    left, right = repaired(6, 4)
    identical = _copy(left)

    # Genuinely different programs, semantically equal: insert a gate and its inverse, and swap two
    # commuting neighbours.
    equivalent = _copy(left)
    equivalent.ccx(0, 1, 2)
    equivalent.ccx(0, 1, 2)

    output_broken = _copy(left)
    output_broken.mcx(0, 1, 2)  # an extra reversible gate: the value function differs

    kernel_left = PhaseProgram(6, 1)
    kernel_left.ccx(0, 1, 6)
    kernel_left.hmr(6)
    kernel_right = PhaseProgram(6, 1)
    kernel_right.ccx(0, 2, 6)  # a different measured function: the dephasing kernel differs
    kernel_right.hmr(6)

    # Same values, same kernel, different measurement-free phase: a diagonal sign on one side only.
    phase_left = _copy(left)
    phase_left.mcz(0, 1, 2)

    return {
        "identical": (left, identical),
        "equivalent_other": (left, equivalent),
        "output_difference": (left, output_broken),
        "kernel_difference": (kernel_left, kernel_right),
        "phase_difference": (phase_left, left),
        "repaired": (left, right),
        "unrepaired": (unrepaired(6, 4), right),
    }


def _copy(program: PhaseProgram) -> PhaseProgram:
    clone = PhaseProgram(program.data, program.ancillas)
    clone.ops = list(program.ops)
    return clone


def run_suite(*, backend: str, data: int = 8, hmr: int = 70) -> dict[str, object]:
    from research.hmr_native_channel.benchmark import case as family

    rows = []
    for left, right in cases().values():
        rows.append(profile_channel(left, right, backend=backend))
    for label, family_name in (("affine", "affine"), ("nonlinear", "nonlinear")):
        left, right = family(data, hmr, family_name)
        rows.append(profile_channel(left, right, backend=backend))
    return {
        "backend": backend,
        "rows": [asdict(row) for row in rows],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="zdd-native", choices=("zdd", "zdd-native"))
    parser.add_argument("--data", type=int, default=8)
    parser.add_argument("--hmr", type=int, default=70)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    payload = run_suite(backend=args.backend, data=args.data, hmr=args.hmr)
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
