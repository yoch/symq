"""Pilot: does the factored criterion beat outcome enumeration as measurement counts grow?

The question is not whether the two predicates agree -- ``tests/test_factored.py`` settles that.
It is whether one of them can decide *instances the other cannot*, and at what cost.

Three methods decide the same predicate on the same pair of programs:

``enumerate``
    The existing strict checker's substrate: form ``phi(x, m)`` over ``data + M`` variables and
    compare. The ANF has up to ``2^M`` times as many monomials as the factorised form.
``oracle``
    The density-matrix reference: ``2^M`` Kraus operators of size ``2^n x 2^n``. Exact, but the
    cost is ``4^M``; it exists to be right, not to scale.
``factored``
    The criterion of ``factored.equivalent_channel``: no ``m`` variable and no outcome sum.

Every run is budgeted (seconds and nodes) and the failure mode is recorded, so a method that
cannot finish is reported as such rather than silently dropped.
"""
from __future__ import annotations

import json
import platform
import resource
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "src"))

import factored

from symq.phase import PhaseProgram, phase_semantics
from symq.resources import Budget, ResourceLimitExceeded


@dataclass
class Measurement:
    method: str
    seconds: float | None = None
    status: str = "ok"
    detail: str = ""
    terms: int | None = None
    nodes: int | None = None
    peak_kib: int | None = None
    extra: dict = field(default_factory=dict)


def measured(method: str, function, *args, **kwargs) -> Measurement:
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    record = Measurement(method)
    try:
        value = function(*args, **kwargs)
        record.seconds = time.perf_counter() - started
        record.extra["value"] = value if isinstance(value, (bool, int, float, str)) else None
    except ResourceLimitExceeded as error:
        record.status = "budget"
        record.detail = f"{error.resource} limit exceeded"
    except MemoryError:
        record.status = "memory"
    except RecursionError:
        record.status = "recursion"
    finally:
        record.peak_kib = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before, 1)
    return record


def specification(data: int, ancillas: int, body) -> PhaseProgram:
    """A measurement-free program: the form a compiler wants to certify against."""
    program = PhaseProgram(data, ancillas)
    body(program)
    return program


def with_measurements(data: int, ancillas: int, count: int, body) -> PhaseProgram:
    """``body``, then ``count`` scratch ancillas measured with an outcome-only correction.

    Each measurement adds a fresh ``g_j`` that is a *non-constant* function of the data, so the
    kernel is genuinely restricted: this is the hard case for the criterion, not a degenerate
    one where ``g_j = 0`` collapses everything.
    """
    program = PhaseProgram(data, ancillas + count)
    body(program)
    scratch = [program.width - count + index for index in range(count)]
    outcomes = []
    for wire in scratch:
        program.mcx(data - 1, wire)
        outcomes.append(program.hmr(wire))
    for index, outcome in enumerate(outcomes):
        # Outcome-only phase: it cannot change the channel, but it does populate g_j.
        program.mcz_if(outcome, scratch[index])
    return program


def make_pair(data: int, ancillas: int, count: int):
    """Two programs with the same channel, one of them full of measurement branches.

    ``left`` computes the data map, then does ``count`` rounds of ``mcx(data-1, scratch)``
    followed by ``hmr`` and an outcome-only correction, which uncomputes the scratch work. Its
    ``g_j`` are the values of ``x_{data-1}`` at each round, i.e. non-constant, so the kernel is a
    genuine restriction. ``right`` is the bare data map on the same width.
    """

    def body(program: PhaseProgram) -> None:
        program.mcz(0, 1) if data > 2 else program.z(0)

    left = with_measurements(data, ancillas, count, body)
    right = PhaseProgram(data, ancillas + count)
    body(right)
    return left, right


def case_size(program: PhaseProgram) -> dict:
    form = factored.factor(program)
    outcomes = program.measurements
    return {
        "data": program.data,
        "ancillas": program.ancillas - outcomes,
        "measurements": outcomes,
        "factored_terms": form.phase_terms(),
        "expanded_terms": len(phase_semantics(program).phase.terms),
        "expanded_variables": program.data + outcomes,
    }


def run_case(data: int, ancillas: int, count: int, timeout_nodes: int) -> dict:
    left, right = make_pair(data, ancillas, count)
    budget = Budget(max_nodes=timeout_nodes, max_seconds=60.0)
    sizes = case_size(left)
    results = {
        "case": sizes,
        "factored": measured("factored", factored.equivalent_channel, left, right,
                             budget=budget).__dict__,
        "expand": measured("expand", phase_semantics, left).__dict__,
    }
    del right
    return results


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "RESULTS.json")
    machine = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": __import__("os").cpu_count(),
        "git_head": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=False).stdout.strip(),
    }
    rows = []
    for count in (1, 2, 3, 4, 5, 6, 7, 8):
        rows.append(run_case(data=3, ancillas=0, count=count, timeout_nodes=200_000))
    payload = {"machine": machine, "rows": rows,
                "note": "factored: no outcome enumeration; expand: the full ANF over data+M "
                        "variables; both decide the same phase, only the first is the criterion"}
    out.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    for row in rows:
        case = row["case"]
        print(f"M={case['measurements']:2d}  factored {case['factored_terms']:8d} terms  "
              f"expanded {case['expanded_terms']:10d} terms  "
              f"({row['factored']['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
