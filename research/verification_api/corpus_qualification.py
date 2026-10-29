"""Real-circuit qualification over the pinned public QCEC corpus.

**Provenance.** `benchmarks/corpus/qcec/MANIFEST.json` pins the upstream repository, commit
`98d6784176bfeb6ef923d4d0220e8d486dc1982f`, the MIT licence and a per-file SHA-256. These are
**real circuits distributed by a public tool project** (TUM MQT's QCEC test set), reused here as-is.
They are reversible gate lists with **no measurements**, so they qualify `FULL_CLASSICAL` claims only.

## Two width limits, which are not the same

This distinction was got wrong in a first draft and is the reason this module exists in its current
shape:

* ``symq.equivalence.check_equivalence`` builds ``make_algebra(backend, left.width)``, so the native
  C ZDD sees **one variable per wire** and is limited to **64 wires**. ``c2_181`` (35) and
  ``rd84_313`` (34) are therefore **native-eligible**.
* ``research.hmr_native_channel.check_full_channel`` represents **two coherent copies** of the data
  registers, so it needs ``2 * n_data`` variables and is limited to **32 data bits**.

The two numbers are unrelated. This module benchmarks the **classical** path and labels it as such; it
makes no HMR claim about these circuits.

## What the per-case outcome means

``check_equivalence`` short-circuits: it compares output polynomials first, and returns on the first
differing wire without ever building a dephasing kernel or a relative-phase comparison (there is no
phase in this grammar). So a ``different`` verdict here is **an output mismatch, never a kernel or
phase mismatch**, and it is *not* evidence about the HMR path. Reporting the categories separately is
the whole point.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from symq.corpus import CorpusEntry, load_corpus
from symq.equivalence import check_equivalence
from symq.generators import mutate
from symq.resources import Budget, ResourceLimitExceeded

MANIFEST = Path("benchmarks/corpus/qcec/MANIFEST.json")

CLASSICAL_NATIVE_MAX_WIRES = 64
"""``make_algebra(backend, width)``: one ZDD variable per wire, ``uint64_t`` mask."""

COHERENT_PAIR_MAX_DATA = 32
"""``check_full_channel``: two coherent copies, so ``2 * n_data <= 64``. Unused here."""

OUTCOMES = (
    "equivalent",  # both backends decided the permutations are equal
    "output_difference",  # a differing output wire was found (short-circuit; nothing else was checked)
    "inconclusive",  # budget or node limit reached without a decision
    "unsupported",  # the file is outside the accepted gate grammar
)
"""The four categories this harness reports. There is deliberately no `kernel_difference` or
`phase_difference`: the classical grammar has no phase, and `check_equivalence` never builds a
dephasing kernel. Those belong to the HMR harness and must not be mixed in here."""


@dataclass(frozen=True)
class CaseResult:
    name: str
    width: int
    gates: int
    split: str
    backend: str
    outcome: str
    seconds: float | None
    detail: str = ""

    @property
    def decided(self) -> bool:
        return self.outcome in ("equivalent", "output_difference")


def _circuit_seed(seed: int, name: str) -> int:
    """Campaign seed mixed with the circuit name.

    ``random.Random(seed)`` restarted on every file would draw the same first
    mutation kind for the whole corpus. Folding the name in keeps the draw
    deterministic and lets one campaign cover more than one edit.
    """
    mixed = seed & 0xFFFFFFFF
    for character in name:
        mixed = (mixed * 16777619 + ord(character)) & 0xFFFFFFFF
    return mixed


def _run(entry: CorpusEntry, backend: str, *, max_seconds: float, seed: int) -> CaseResult:
    """Compare one corpus circuit against a deterministic mutant of itself."""
    try:
        circuit = entry.load()
    except Exception as exc:  # noqa: BLE001 - an unparsable file is unsupported, not a verdict
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            "unsupported",
            None,
            f"load failed: {type(exc).__name__}",
        )
    if backend == "zdd-native" and entry.width > CLASSICAL_NATIVE_MAX_WIRES:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            "inconclusive",
            None,
            f"width {entry.width} exceeds the {CLASSICAL_NATIVE_MAX_WIRES}-wire native mask",
        )
    mutant, kind = mutate(circuit, random.Random(_circuit_seed(seed, entry.name)))
    started = perf_counter()
    try:
        verdict = check_equivalence(
            circuit, mutant, backend=backend, budget=Budget(max_seconds=max_seconds)
        )
    except ResourceLimitExceeded as exc:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            "inconclusive",
            perf_counter() - started,
            str(exc)[:60],
        )
    except Exception as exc:  # noqa: BLE001 - never promote an error to a verdict
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            "unsupported",
            perf_counter() - started,
            type(exc).__name__,
        )
    elapsed = perf_counter() - started
    outcome = "equivalent" if verdict.equivalent else "output_difference"
    detail = kind
    if not verdict.equivalent:
        # `output` is the first differing output wire; the witness replays it by concrete execution.
        detail = f"{kind}; first differing output wire {verdict.output}, witness {verdict.witness}"
    return CaseResult(
        entry.name, entry.width, entry.gates, entry.split, backend, outcome, elapsed, detail
    )


def qualify(
    *,
    max_seconds: float = 30.0,
    backends: tuple[str, ...] = ("zdd", "zdd-native"),
    seed: int = 1234,
):
    """Run every supported corpus entry on every backend; return manifest rows and coverage."""
    corpus = load_corpus(MANIFEST)
    rows: list[CaseResult] = []
    for entry in corpus.entries:
        if not entry.supported:
            rows.append(
                CaseResult(
                    entry.name,
                    entry.width,
                    entry.gates,
                    entry.split,
                    "-",
                    "unsupported",
                    None,
                    entry.reason or "manifest",
                )
            )
            continue
        for backend in backends:
            rows.append(_run(entry, backend, max_seconds=max_seconds, seed=seed))
    return corpus.manifest, rows


def agreement(rows: list[CaseResult]) -> tuple[int, int, list[str]]:
    """Pairs where both backends reached the **same decided** verdict.

    Two ``inconclusive`` rows are not agreement: neither decided anything, so counting them as a match
    would let a fully undecided corpus look green.
    """
    per_circuit: dict[str, list[CaseResult]] = {}
    for row in rows:
        if row.backend == "-":
            continue
        per_circuit.setdefault(row.name, []).append(row)
    agree = comparable = 0
    disagreements: list[str] = []
    for name, cases in per_circuit.items():
        decided = [c for c in cases if c.decided]
        if len(decided) < 2:
            continue
        comparable += 1
        if len({c.outcome for c in decided}) == 1:
            agree += 1
        else:
            disagreements.append(name)
    return agree, comparable, disagreements


def summary(rows: list[CaseResult]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[f"{row.backend}:{row.outcome}"] = counts.get(f"{row.backend}:{row.outcome}", 0) + 1
    agree, comparable, disagreements = agreement(rows)
    per_backend: dict[str, dict[str, object]] = {}
    for backend in sorted({row.backend for row in rows} - {"-"}):
        cases = [row for row in rows if row.backend == backend]
        durations = [row.seconds for row in cases if row.seconds is not None]
        per_backend[backend] = {
            "cases": len(cases),
            "decided": len([row for row in cases if row.decided]),
            "equivalent": len([row for row in cases if row.outcome == "equivalent"]),
            "output_difference": len([row for row in cases if row.outcome == "output_difference"]),
            "inconclusive": len([row for row in cases if row.outcome == "inconclusive"]),
            "median_seconds": sorted(durations)[len(durations) // 2] if durations else None,
        }
    by_split: dict[str, int] = {}
    for row in rows:
        if row.backend == "-":
            by_split[f"{row.split}:manifest"] = by_split.get(f"{row.split}:manifest", 0) + 1
    return {
        "proof_class": "FULL_CLASSICAL (no measurement, no phase)",
        "rows": len(rows),
        "counts": counts,
        "agreeing": agree,
        "comparable": comparable,
        "disagreements": disagreements,
        "per_backend": per_backend,
        "manifest_only_rows": by_split,
    }


def split_totals(rows: list[CaseResult]) -> dict[str, dict[str, int]]:
    """Per-split counts of distinct circuits, so DEV/holdout/extension stay visibly separate."""
    totals: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for row in rows:
        if row.name in seen:
            continue
        seen.add(row.name)
        bucket = totals.setdefault(row.split, {"circuits": 0, "decided": 0, "undecided": 0})
        bucket["circuits"] += 1
        if row.outcome in ("equivalent", "output_difference"):
            bucket["decided"] += 1
        else:
            bucket["undecided"] += 1
    return totals


def rows_as_dicts(rows: list[CaseResult]) -> list[dict[str, object]]:
    return [asdict(row) for row in rows]


if __name__ == "__main__":  # pragma: no cover - reporting helper
    import json

    manifest, rows = qualify()
    print(
        json.dumps(
            {
                "provenance": {
                    "repository": manifest["source"]["repository"],
                    "commit": manifest["source"]["commit"],
                    "license": manifest["source"]["license"],
                    "reused": True,
                    "note": "reversible QASM corpus; no HMR, no measurement",
                },
                "summary": summary(rows),
                "splits": split_totals(rows),
            },
            indent=2,
        )
    )
