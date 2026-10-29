"""Compatibility profile API backed by the installed public verifier.

Stage clocks are exclusive: nested work is subtracted from its parent.
The whole-call total includes orchestration, validation and instrumentation.
There is no second channel-equivalence implementation in this driver.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from symq.experimental.channel import _scalar, _scalar_kernel, _sha
from symq.experimental.contracts import VerificationContract
from symq.experimental.profiling import ExclusiveTimer, profile
from symq.phase import PhaseProgram
from symq.resources import Budget

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
    orchestration: float = 0.0
    outputs_compare: float = 0.0
    validation: float = 0.0
    reduction: float = 0.0
    rename: float = 0.0
    conversions: float = 0.0
    diagnostics: float = 0.0
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
    """Legacy timer interface, with exclusive stack-based accounting."""

    def __init__(self, stages: StageTimes) -> None:
        self.stages = stages
        self._timer = ExclusiveTimer()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        try:
            with self._timer.stage(name):
                yield
        finally:
            for stage_name, seconds in self._timer.seconds.items():
                setattr(self.stages, stage_name, seconds)

    def reconcile(self, total: float) -> None:
        self._timer.finish(total)
        for stage_name, seconds in self._timer.seconds.items():
            setattr(self.stages, stage_name, seconds)
        self.stages.total = total


def profile_channel(left: PhaseProgram, right: PhaseProgram, *,
                    backend: str = "zdd-native", budget: Budget | None = None) -> Profile:
    """Adapt the real public profile into the historical research result shape."""
    report = profile(left, right, VerificationContract(backend=backend), budget=budget)
    result = report.result
    stages = StageTimes(total=report.total_seconds)
    for name, seconds in report.stage_seconds:
        setattr(stages, name, seconds)
    counters = dict(report.counters)
    work = WorkCounters(data=left.data, variables=2 * left.data,
                        events=left.measurements + right.measurements,
                        operations=len(left.ops) + len(right.ops))
    for name in ("products", "xors", "is_zero_calls", "min_monomial_calls", "kernel_rounds"):
        setattr(work, name, int(counters.get(name, 0)))
    for name in ("mcz", "hmr", "mcz_if"):
        setattr(work, name + "_ops", sum(op.kind == name for p in (left, right) for op in p.ops))
    for name in ("zero_phase_final", "zero_coefficients_final"):
        if name in counters:
            setattr(work, name, bool(counters[name]))
    if result.equivalent:
        observed = "equivalent"
    elif result.outcome != "different":
        observed = result.outcome
    elif "output wire" in result.reason:
        observed = "output_difference:" + result.reason.split("output wire ", 1)[1].split()[0]
    elif "kernels" in result.reason:
        observed = "kernel_difference"
    else:
        observed = "phase_difference"
    return Profile(case=f"{left.data}d/{left.measurements}e/{backend}",
                   left=_sha(left), right=_sha(right), backend=backend,
                   expected="equivalent" if result.equivalent else result.witness_kind or result.outcome,
                   observed=observed, matched=result.outcome in {"equivalent", "different"},
                   stages=stages, work=work, peak_terms=counters.get("peak_terms"),
                   terms_after={"kernel_x": None})


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

    Every pair is passed to the installed public verifier; the adapter reports
    that exact result and does not run a separate channel algorithm.
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
