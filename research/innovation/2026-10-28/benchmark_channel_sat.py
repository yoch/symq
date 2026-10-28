"""Matched, predeclared small HMR-channel pilot: SAT vs pure-Python pair-input ZDD.

Each call includes factorization and complete decision, with no measurement-outcome
enumeration and no cross-repository runtime dependency. Small deterministic cases,
not a general performance claim. Run with --repetitions 7 and preserve raw timings.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from symq.phase import PhaseProgram
from symq.resources import Budget
from symq.sat import available, versions

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent / "prototype"))

import channel_sat  # noqa: E402
import factored  # noqa: E402


def and_release(*, second: bool = False, corrected: bool = True):
    source = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    first = source.hmr(3)
    source.cz_if(first, 0, 1)
    target = PhaseProgram(3, 1).ccx(0, 1, 2)
    if second:
        source.ccx(1, 2, 3).cx(3, 0)
        second_outcome = source.hmr(3)
        if corrected:
            source.cz_if(second_outcome, 1, 2)
        target.ccx(1, 2, 0)
    return source, target


def cases():
    """Frozen case names, grammar and claims; never select by favorable timings."""
    sign = PhaseProgram(1, 1).x(1)
    sign.hmr(1)
    dephasing = PhaseProgram(1, 1).cx(0, 1)
    dephasing.hmr(1)

    linear_left = PhaseProgram(2, 2).cx(0, 2).cx(1, 3)
    linear_left.hmr(2)
    linear_left.hmr(3)
    linear_right = PhaseProgram(2, 2).cx(0, 2).cx(1, 3).cx(0, 3)
    linear_right.hmr(2)
    linear_right.hmr(3)

    correct, target = and_release()
    two, two_target = and_release(second=True)
    broken, broken_target = and_release(second=True, corrected=False)

    return (
        ("identity", PhaseProgram(2), PhaseProgram(2)),
        ("outcome_only_global_sign", sign, PhaseProgram(1, 1)),
        ("and_release_equal", correct, target),
        ("and_release_missing_cz", PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2), target),
        ("dephasing_kernel_diff", dephasing, PhaseProgram(1, 1)),
        ("output_diff", PhaseProgram(3).ccx(0, 1, 2), PhaseProgram(3)),
        ("relative_phase_diff", PhaseProgram(3).z(0), PhaseProgram(3)),
        ("same_kernel_different_syndromes", linear_left, linear_right),
        ("two_and_release_equal", two, two_target),
        ("two_and_release_missing_cz", broken, broken_target),
    )


def _sat(left, right, *, seconds):
    value = channel_sat.check_channel_sat(
        left, right, budget=Budget(max_seconds=seconds),
    )
    if value.outcome == "inconclusive":
        raise RuntimeError(f"SAT inconclusive: {value.reason}")
    return value.outcome == "equivalent", (value.clauses, value.variables)


def _zdd(left, right, *, seconds):
    value = factored.equivalent_channel(
        left, right, budget=Budget(max_seconds=seconds),
    )
    return value.equivalent, (value.pairs,)


def main(*, repetitions: int, max_seconds: float) -> dict:
    if not available():
        raise RuntimeError("optional interruptible PySAT solver is required")
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be an integer in [1,100]")
    if max_seconds <= 0:
        raise ValueError("max_seconds must be positive")
    rows = []
    for name, left, right in cases():
        # Preflight correctness and untimed warmups. No adaptive case selection.
        sat_value, sat_cost = _sat(left, right, seconds=max_seconds)
        zdd_value, zdd_cost = _zdd(left, right, seconds=max_seconds)
        if sat_value != zdd_value:
            raise AssertionError(f"disagree on {name}")
        samples = {"sat": [], "zdd": []}
        # Interleave engine order deterministically to reduce drift bias.
        for iteration in range(repetitions):
            order = ("sat", "zdd") if iteration % 2 == 0 else ("zdd", "sat")
            for engine in order:
                started = time.perf_counter()
                result, _ = (_sat if engine == "sat" else _zdd)(
                    left, right, seconds=max_seconds,
                )
                elapsed = time.perf_counter() - started
                if result != sat_value:
                    raise AssertionError(f"{engine} verdict changed on {name}")
                samples[engine].append(elapsed)
        med_sat = statistics.median(samples["sat"])
        med_zdd = statistics.median(samples["zdd"])
        rows.append({
            "case": name, "data": left.data, "ancillas": left.ancillas,
            "measurements_l": left.measurements, "measurements_r": right.measurements,
            "ops_l": len(left.ops), "ops_r": len(right.ops),
            "equivalent": sat_value,
            "sat_clauses": sat_cost[0], "sat_variables": sat_cost[1],
            "zdd_pair_space": zdd_cost[0],
            "sat_seconds": samples["sat"], "zdd_seconds": samples["zdd"],
            "sat_median_seconds": med_sat, "zdd_median_seconds": med_zdd,
            "sat_over_zdd_median_ratio": med_sat / med_zdd if med_zdd else None,
        })
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "unavailable"
    return {
        "status": "EXPLORATORY_MATCHED_SMALL_CASES_NOT_HOLDOUT",
        "source_commit": sha,
        "python": platform.python_version(), "platform": platform.platform(),
        "sat_versions": versions(), "repetitions": repetitions,
        "per_call_max_seconds": max_seconds,
        "wall_clock": "time.perf_counter; full public calls, no import or startup",
        "peak_rss": "not measured; no memory comparison",
        "case_count": len(rows),
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--max-seconds", type=float, default=10.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = main(repetitions=args.repetitions, max_seconds=args.max_seconds)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        if args.out.exists():
            raise FileExistsError("refuse to overwrite an existing benchmark report")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
