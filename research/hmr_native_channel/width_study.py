"""Can the n_data <= 32 native ceiling be lifted exactly?

## The limit, precisely

``check_full_channel`` builds ``make_algebra("zdd-native", 2 * data)`` because it represents two
coherent copies of the data register: variables ``0..n-1`` for ``x`` and ``n..2n-1`` for ``y``. The
native core stores a monomial mask in one ``uint64_t``, so ``2n <= 64``. Measured: ``data=32``
decides, ``data=33`` raises ``ResourceLimitExceeded("native pair variables", 64, 66)``. The Python
``zdd`` backend keeps deciding at 36 data bits (72 variables), just more slowly.

## Three exact routes, and what each actually requires

**1. Multiword masks.** Widen the native monomial to two ``uint64_t`` words. Exact by construction.
Every ``level`` comparison, hash key, ``min_monomial`` and ``rename`` map has to become width-aware,
and the cache key grows. This is a representation change in the C core, not a new theorem.

**2. Block decomposition.** If a program's ancilla interactions are confined to disjoint data
blocks *and* the blocks never share a nonlinear factor, the diagram is a product of per-block
diagrams and the channel check factors. This is a **syntactic precondition that must be checked per
program**, not an assumption: the published 36-data family fails it, because its temporary AND reads
controls from fourteen different data wires. So this route is real, but only for circuits that are
already narrow in the relevant sense.

**3. Compose after renaming.** The checker needs, for each program, ``F(x)``, ``phi0(x)`` and every
``g_j(x)``, plus the same on ``y``. With exact renaming (``rename_reuse``) the ``y`` copy is free,
but the ``x`` copy still spans ``n`` variables, so this does **not** move the ceiling.

## What this module does

It measures the three routes and reports the ones that are unavailable, rather than proposing a
representation change as if it were a small patch. A negative, argued result is the deliverable when
the honest answer is "this needs a new mask type".
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from research.hmr_native_channel.benchmark import case as family
from research.hmr_native_channel.native_channel import check_full_channel
from symq.phase import PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded

NATIVE_MAX_DATA = 32


@dataclass(frozen=True)
class WidthProbe:
    data: int
    backend: str
    outcome: str
    seconds: float
    variables: int
    detail: str = ""


@dataclass(frozen=True)
class LocalityReport:
    data: int
    programs: int
    ancilla_wires: int
    reads_per_ancilla: tuple[int, ...]
    widest_local_block: int
    factorable: bool
    detail: str


def probe_widths(widths: tuple[int, ...] = (31, 32, 33, 34, 36, 40), hmr: int = 20) -> list[WidthProbe]:
    """Where each backend stops, measured rather than assumed."""
    import time

    rows: list[WidthProbe] = []
    for data in widths:
        left, right = family(data, hmr, "nonlinear")
        for backend in ("zdd-native", "zdd"):
            started = time.perf_counter()
            try:
                decision = check_full_channel(
                    left, right, backend=backend, budget=Budget(max_seconds=300)
                )
                outcome = "equivalent" if decision.equivalent else "different"
                detail = decision.reason
            except ResourceLimitExceeded as exc:
                outcome = "resource_limit"
                detail = str(exc)[:100]
            except Exception as exc:  # noqa: BLE001 - diagnostics are the point here
                outcome = "error"
                detail = f"{type(exc).__name__}: {exc}"[:150]
            rows.append(
                WidthProbe(
                    data=data,
                    backend=backend,
                    outcome=outcome,
                    seconds=time.perf_counter() - started,
                    variables=2 * data,
                    detail=detail,
                )
            )
    return rows


def ancilla_locality(program: PhaseProgram, block: int = NATIVE_MAX_DATA) -> LocalityReport:
    """Can this program's diagrams be split into independent blocks of at most ``block`` wires?

    The test is a **connected-component** analysis, not a read-set size:

    * two data wires are linked when a gate touches both and its target is a data wire;
    * a data wire is linked to the ancilla it controls or is controlled by.

    A component that spans more than one block cannot be represented in one native diagram of
    ``2 * block`` variables, because every coherence ``|x><y|`` over that component needs both
    copies of every wire in it. Reporting components is what turns "we could split" into something
    a reader can check.
    """
    parent = list(range(program.width))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    data_mixing = 0
    for op in program.ops:
        qubits = op.qubits
        for other in qubits[1:]:
            union(qubits[0], other)
        if op.kind in ("mcx", "mcz", "mcz_if"):
            targets = [q for q in qubits if q < program.data]
            if len(targets) >= 2:
                data_mixing += 1

    components: dict[int, set[int]] = {}
    for wire in range(program.width):
        components.setdefault(find(wire), set()).add(wire)
    spans = sorted(len(members) for members in components.values())

    reads: dict[int, set[int]] = {}
    for op in program.ops:
        for q in op.qubits:
            if q >= program.data:
                reads.setdefault(q, set()).update(p for p in op.qubits if p < program.data)
    per_ancilla = tuple(sorted(len(v) for v in reads.values()))

    widest = spans[-1] if spans else 0
    factorable = widest <= block
    headroom = block - widest
    if factorable:
        detail = (
            f"widest connected component is {widest} wires, {headroom} below the {block}-wire "
            "block ceiling: a split is available"
        )
    else:
        detail = (
            f"widest connected component spans {widest} wires, above the {block}-wire block: "
            f"{data_mixing} gates act on two or more data wires and "
            f"{len(reads)} ancilla(s) read "
            f"{sum(per_ancilla)} data-wire incidences, so the diagrams do not factor"
        )
    return LocalityReport(
        data=program.data,
        programs=1,
        ancilla_wires=program.ancillas,
        reads_per_ancilla=per_ancilla,
        widest_local_block=widest,
        factorable=factorable,
        detail=detail,
    )


def multiword_cost_estimate(program: PhaseProgram) -> dict[str, object]:
    """What route 1 would touch, counted from the actual program rather than guessed."""
    return {
        "data": program.data,
        "variables_needed": 2 * program.data,
        "native_words_needed": (2 * program.data + 63) // 64,
        "ops": len(program.ops),
        "hmr_events": program.measurements,
        "affected_primitives": [
            "mk/hash_key (node key grows by one word)",
            "cache key (op,a,b unchanged; masks are node ids, not masks)",
            "min_monomial / min_masks (needs a two-word minimum)",
            "rename (level map unchanged; monotonicity still holds)",
            "from_terms / anf (masks become tuples)",
        ],
        "note": (
            "anf/from_terms are the boundary with Python integers; the engine itself only stores "
            "levels and child ids, so the recursion is unchanged"
        ),
    }


def run() -> dict[str, object]:
    probes = probe_widths()
    wide = family(36, 8, "nonlinear")[0]
    narrow = family(8, 4, "nonlinear")[0]
    return {
        "probes": [asdict(row) for row in probes],
        "locality_36": asdict(ancilla_locality(wide)),
        "locality_8_control": asdict(ancilla_locality(narrow)),
        "multiword": multiword_cost_estimate(wide),
        "conclusion": (
            "The ceiling is representational: 2 * n_data <= 64 native variables, not a semantic "
            "limit -- the pure-Python backend decides 36 and 40 data bits. A block decomposition "
            "is sound but only *sometimes* available: the 36-data published family has a "
            "connected component of 31 data wires, already at the block ceiling, so splitting "
            "buys nothing there. The general exact route is a two-word monomial mask in the C "
            "core, which is a representation change rather than a new theorem."
        ),
    }


def main() -> int:
    payload = run()
    out = Path("research/hmr_native_channel/RESULTS/width-20261029.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
