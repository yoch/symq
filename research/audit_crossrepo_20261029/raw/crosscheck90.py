"""Cross-check the PR #90 oracle against the independent dense-Kraus reference.

Every case is compared on **all** matrix units |x><y|, with ancillas both kept and traced. The
reference shares no code with the audited module: it builds dense rational matrices and applies
Kraus families, while the audited code tracks a sparse dict of (row, col) coefficients.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PR90 = Path(os.environ.get("PR90", "/tmp/audit/pr90"))
from fractions import Fraction as F

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ref90 as R

from research.hybrid_channel.oracle import HybridProgram, coherence_image


def _program(ops, data, anc):
    prog = HybridProgram(data=data, ancillas=anc)
    slots = 0
    for kind, wires in ops:
        if kind in ("hmr", "measure_z"):
            getattr(prog, kind)(*wires, f"b{slots}")
            slots += 1
        else:
            getattr(prog, kind)(*wires)
    return prog


def audited_matrix(prog, x, y, trace):
    cell = coherence_image(prog, x, y, trace_ancillas=trace, max_width=5)
    d = 1 << (prog.data if trace else prog.width)
    return [[cell.get((i, j), F(0)) for j in range(d)] for i in range(d)]


def reference_matrix(ops, data, anc, x, y, trace):
    n = data + anc
    rho = R.basis_rho(x, y, n)
    out = R.run(ops, n, rho, trace_after=data if trace else None)
    d = 1 << (data if trace else n)
    return [[out[i][j] for j in range(d)] for i in range(d)]


CASES = {
    "identity": ([], 1, 0),
    "x": ([("x", (0,))], 1, 0),
    "cx": ([("cx", (0, 1))], 2, 0),
    "ccx": ([("ccx", (0, 1, 2))], 3, 0),
    "mcx4": ([("mcx", (0, 1, 2, 3))], 4, 0),
    "swap": ([("swap", (0, 1))], 2, 0),
    "cswap": ([("cswap", (0, 1, 2))], 3, 0),
    "z": ([("z", (0,))], 1, 0),
    "cz": ([("cz", (0, 1))], 2, 0),
    "ccz": ([("ccz", (0, 1, 2))], 3, 0),
    "neg": ([("neg", ())], 1, 0),
    "reset_anc": ([("reset", (1,))], 1, 1),
    "hmr_anc": ([("hmr", (1,))], 1, 1),
    "measure_anc": ([("measure_z", (1,))], 1, 1),
    "cx_reset": ([("cx", (0, 1)), ("reset", (1,))], 1, 1),
    "cx_then_hmr": ([("cx", (0, 1)), ("hmr", (1,))], 1, 1),
    "hmr_data": ([("hmr", (0,))], 1, 0),
    "x_hmr_x_hmr": ([("x", (0,)), ("hmr", (0,))], 1, 0),
    "z_on_plus": ([("z", (0,))], 1, 0),
    "h_like": ([("hmr", (0,)), ("x", (0,))], 1, 0),
    "two_hmr": ([("hmr", (0,)), ("hmr", (0,))], 1, 0),
    "measure_then_x": ([("measure_z", (0,)), ("x", (0,))], 1, 0),
    "reset_data": ([("reset", (0,))], 1, 0),
    "ccx_reset_anc": ([("ccx", (0, 1, 2)), ("reset", (2,))], 2, 1),
}


def main() -> int:
    failures = 0
    for name, (ops, data, anc) in CASES.items():
        prog = _program(ops, data, anc)
        bad = []
        for trace in (False, True):
            for x in range(1 << data):
                for y in range(1 << data):
                    got = audited_matrix(prog, x, y, trace)
                    want = reference_matrix(ops, data, anc, x, y, trace)
                    if got != want:
                        bad.append((trace, x, y))
        status = "OK " if not bad else "MISMATCH"
        print(f"{status} {name:16s} ({len(bad)} differing units)")
        if bad:
            failures += 1
            trace, x, y = bad[0]
            print(f"      first difference at trace={trace} |{x}><{y}|")
            got = audited_matrix(prog, x, y, trace)
            want = reference_matrix(ops, data, anc, x, y, trace)
            for i in range(len(got)):
                if got[i] != want[i]:
                    print(f"        row {i}: audited={got[i]}")
                    print(f"        row {i}: ref    ={want[i]}")
                    break
    print()
    print(f"{len(CASES) - failures}/{len(CASES)} cases agree with the independent reference")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
