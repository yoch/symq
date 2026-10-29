"""Randomised differential test of the PR #90 oracle against the independent reference.

Generates random programs over the full accepted gate set and compares the channel on **every**
matrix unit, with ancillas kept and traced. Seeded, so any failure is reproducible.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

PR90 = Path(os.environ.get("PR90", "/tmp/audit/pr90"))
from fractions import Fraction as F

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ref90 as R
from research.hybrid_channel.oracle import HybridProgram, coherence_image


def build_ops(rng, data, anc, length):
    """Random unconditional gate list (no classical control: the reference has no slots)."""
    n = data + anc
    ops = []
    allowed = ["x", "z", "neg", "hmr", "measure_z", "reset"]
    if n >= 2:
        allowed += ["cx", "cz", "swap"]
    if n >= 3:
        allowed += ["ccx", "cswap"]
    for _ in range(length):
        kind = rng.choice(allowed)
        if kind == "x":
            ops.append(("x", (rng.randrange(n),)))
        elif kind == "z":
            ops.append(("z", (rng.randrange(n),)))
        elif kind == "neg":
            ops.append(("neg", ()))
        elif kind == "cx":
            c, t = rng.sample(range(n), 2)
            ops.append(("cx", (c, t)))
        elif kind == "cz":
            a, b = rng.sample(range(n), 2)
            ops.append(("cz", (a, b)))
        elif kind in ("swap",):
            a, b = rng.sample(range(n), 2)
            ops.append((kind, (a, b)))
        elif kind == "ccx":
            a, b, t = rng.sample(range(n), 3)
            ops.append(("ccx", (a, b, t)))
        elif kind == "cswap":
            c, a, b = rng.sample(range(n), 3)
            ops.append(("cswap", (c, a, b)))
        else:
            ops.append((kind, (rng.randrange(n),)))
    return ops


def to_program(ops, data, anc):
    prog = HybridProgram(data=data, ancillas=anc)
    slots = 0
    for kind, wires in ops:
        if kind in ("hmr", "measure_z"):
            getattr(prog, kind)(*wires, f"b{slots}")
            slots += 1
        else:
            getattr(prog, kind)(*wires)
    return prog


def audited(prog, x, y, trace):
    cell = coherence_image(prog, x, y, trace_ancillas=trace, max_width=5)
    d = 1 << (prog.data if trace else prog.width)
    return [[cell.get((i, j), F(0)) for j in range(d)] for i in range(d)]


def reference(ops, data, anc, x, y, trace):
    n = data + anc
    out = R.run(ops, n, R.basis_rho(x, y, n), trace_after=data if trace else None)
    d = 1 << (data if trace else n)
    return [[out[i][j] for j in range(d)] for i in range(d)]


def main(trials=120, seed=20261029):
    rng = random.Random(seed)
    failures = 0
    for trial in range(trials):
        data = rng.choice([1, 1, 2])
        anc = rng.choice([0, 1])
        if data + anc > 3:
            anc = 3 - data
        length = rng.randrange(1, 6)
        ops = build_ops(rng, data, anc, length)
        prog = to_program(ops, data, anc)
        for trace in (False, True):
            for x in range(1 << data):
                for y in range(1 << data):
                    got = audited(prog, x, y, trace)
                    want = reference(ops, data, anc, x, y, trace)
                    if got != want:
                        failures += 1
                        print(f"FAIL trial={trial} seed={seed} ops={ops} data={data} anc={anc}")
                        print(f"  trace={trace} unit=({x},{y})")
                        for i in range(len(got)):
                            if got[i] != want[i]:
                                print(f"   row {i} audited={got[i]}")
                                print(f"   row {i} ref    ={want[i]}")
                                break
                        if failures > 3:
                            return 1
    print(
        f"{trials} random programs x all matrix units x 2 trace modes: "
        f"{'ALL AGREE' if not failures else f'{failures} FAILURES'}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
