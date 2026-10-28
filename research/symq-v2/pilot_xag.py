"""Pilot for issue #69: SSA encoder vs affine XAG encoder, both on Glucose 4.2.

Protocol fixed before measuring:

* the same task is given to both encoders through the same solver, the same ``Contract`` and the
  same wall-clock budget; the timing is **external** and covers the whole call;
* each encoder reports its own size metrics -- variables, clauses, AND nodes, longest XOR -- which
  is what the issue asks to weigh against the end-to-end time;
* each case is checked against concrete execution on every input (widths <= 14) or against the
  other encoder plus witness replay;
* one immutable source SHA, solver version, worktree state and limits are recorded.

Families: a GF(2^12) multiplication block built here (documented as *not* the qant fixture, which
is not reachable from this environment), small adders, dense random circuits and a hard equivalent
pair. No parameter was tuned on these cases.
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from symq import Budget, Circuit, Gate
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.sat import check_sat_equivalence
from symq.sat.encoding import _solver_factory, solver_name
from symq.sat.encoding_xag import build_xag
from symq.sat.miter_xag import check_xag_equivalence

MAX_SECONDS = 60.0
REPEATS = 3


def load_adders():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("xag_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["xag_adders"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load_adders()


def gf_mul_block(bits: int) -> Circuit:
    """Schoolbook GF(2^bits) multiply-accumulate, the shape of the qant GF12 block.

    Wires: ``a[0..n-1] | b[0..n-1] | p[0..2n-1]`` with ``p <- p xor (a * b)`` computed as a sum of
    ``n`` partial products, each a chain of CCX gates. The product is *not* reduced modulo an
    irreducible polynomial: this is the pre-reduction block, which is what makes it a useful test
    of a nonlinear core surrounded by linear XOR accumulation.

    **This is not the qant fixture.** ``yoch/qant`` is not reachable from this environment (404),
    so no claim is made about that repository's block or its reference witness.
    """
    n = bits
    circuit = Circuit(4 * n)
    a = list(range(n))
    b = list(range(n, 2 * n))
    product = list(range(2 * n, 4 * n))
    for shift in range(n):
        for index in range(n):
            circuit.ccx(a[index], b[shift], product[shift + index])
    return circuit


def size_of(circuit: Circuit) -> dict:
    model = build_xag(circuit)
    return {"xag_variables": model.variables, "and_nodes": len(model.ands),
            "longest_xor": max(model.xor_lengths) if model.xor_lengths else 0}


def timed(function, *args, **kwargs) -> dict:
    started = time.perf_counter()
    try:
        verdict = function(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - an encoder failure is data
        return {"status": "error", "detail": f"{type(error).__name__}: {error}",
                "seconds": time.perf_counter() - started}
    elapsed = time.perf_counter() - started
    if verdict.outcome == "inconclusive":
        return {"status": "inconclusive", "seconds": elapsed, "detail": verdict.detail}
    return {"status": "ok", "equivalent": verdict.outcome == "equivalent", "seconds": elapsed,
            "clauses": verdict.clauses, "variables": verdict.variables,
            "solver": verdict.solver, "witness_checked": verdict.witness_checked}


def cases():
    rng = random.Random(20261028)
    out = [("gf12_mul", gf_mul_block(12), gf_mul_block(12))]
    block = gf_mul_block(12)
    out.append(("gf12_mul_mutant", block,
                Circuit(block.width, [*block.gates[:-1], Gate("x", (block.width - 1,))])))
    for bits in (8, 12):
        adder = ADDERS.adder(bits)
        out.append((f"adder_{bits}", adder, type(adder)(adder.width, list(adder.gates))))
        out.append((f"adder_{bits}_mutant", adder, mutate(adder, rng, "insert")[0]))
    for width, gates in ((10, 120), (12, 160)):
        base = random_circuit(width, gates, rng)
        out.append((f"rand{width}x{gates}_diff", base, mutate(base, rng, "insert")[0]))
        out.append((f"rand{width}x{gates}_equiv", base, equivalent_variant(base, rng, steps=5)))
    return out


def provenance() -> dict:
    def run(*args):
        return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()

    try:
        from symq.sat import versions

        solver_versions = versions()
    except Exception:  # noqa: BLE001
        solver_versions = {}
    return {"git_head": run("git", "-C", str(ROOT), "rev-parse", "HEAD"),
            "worktree_dirty": bool(run("git", "-C", str(ROOT), "status", "--porcelain",
                                       "--untracked-files=no")),
            "python": sys.version.split()[0],
            "solver_class": solver_name(_solver_factory()),
            "solver_versions": solver_versions,
            "limits": {"max_seconds_all_encoders": MAX_SECONDS, "repeats": REPEATS},
            "qant_fixture": "NOT available from this environment (404); gf_mul_block is local"}


def main() -> int:
    rows = []
    for name, left, right in cases():
        record = {"task": name, "width": left.width, "gates": len(left.gates),
                  **{f"left_{k}": v for k, v in size_of(left).items()}}
        for encoder, function in (("ssa", check_sat_equivalence), ("xag", check_xag_equivalence)):
            samples = []
            last = {}
            for _ in range(REPEATS):
                last = timed(function, left, right, budget=Budget(max_seconds=MAX_SECONDS))
                if last["status"] != "ok":
                    samples = []
                    break
                samples.append(last["seconds"])
            record[encoder] = {"status": last.get("status"),
                               "seconds": statistics.median(samples) if samples else None,
                               "clauses": last.get("clauses"),
                               "variables": last.get("variables"),
                               "equivalent": last.get("equivalent")}
        decided = [record[e]["equivalent"] for e in ("ssa", "xag")
                   if record[e]["status"] == "ok"]
        record["agree"] = len(set(decided)) <= 1
        rows.append(record)
        ssa, xag = record["ssa"], record["xag"]
        ratio = (ssa["seconds"] / xag["seconds"]) if (ssa["seconds"] and xag["seconds"]) else None
        print(f"{name:22s} ssa={ssa['status']:6s} xag={xag['status']:6s} "
              f"vars {ssa['variables']}->{xag['variables']} "
              f"clauses {ssa['clauses']}->{xag['clauses']} "
              f"speedup={ratio:.2f}" if ratio else
              f"{name:22s} ssa={ssa['status']} xag={xag['status']}", flush=True)

    paired = [r["ssa"]["seconds"] / r["xag"]["seconds"] for r in rows
              if r["ssa"].get("seconds") and r["xag"].get("seconds")]
    payload = {"provenance": provenance(), "rows": rows,
               "summary": {
                   "paired_cases": len(paired),
                   "geomean_ssa_over_xag": (statistics.geometric_mean(paired)
                                            if paired else None),
                   "xag_wins": sum(1 for value in paired if value > 1),
                   "ssa_wins": sum(1 for value in paired if value < 1),
                   "disagreements": [r["task"] for r in rows if not r["agree"]],
               }}
    (HERE.parent / "RESULTS" / "xag_pilot.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
