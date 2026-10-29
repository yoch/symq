"""Real-circuit qualification over the pinned public QCEC corpus.

**Provenance.** `benchmarks/corpus/qcec/MANIFEST.json` pins the upstream repository, commit
`98d6784176bfeb6ef923d4d0220e8d486dc1982f`, the MIT licence and a per-file SHA-256. These are
**real circuits distributed by a public tool project** (TUM MQT's QCEC test set), reused as-is.
They are reversible gate lists with **no measurements**, so they qualify `FULL_CLASSICAL` claims only.

## Two width limits, which are not the same

* ``symq.equivalence.check_equivalence`` builds ``make_algebra(backend, left.width)``, so the native
  C ZDD sees **one variable per wire** and is limited to **64 wires**. ``c2_181`` (35) and
  ``rd84_313`` (34) are therefore **native-eligible**.
* ``research.hmr_native_channel.check_full_channel`` represents **two coherent copies** of the data
  registers, so it needs ``2 * n_data`` variables and is limited to **32 data bits**.

The two numbers are unrelated. This module benchmarks the **classical** path and labels it as such;
it makes no HMR claim about these circuits.

## Five outcomes, five different meanings

The first version of this harness caught every exception and wrote ``unsupported``. That made an
**uninstalled backend** look like an **out-of-grammar circuit**, and the pure-Python CI job reported
19 supported circuits as unsupported with zero comparisons. The categories are now separate:

``equivalent`` / ``output_difference``
    A real decision. ``output_difference`` is the first differing output wire; this grammar has no
    phase and ``check_equivalence`` never builds a dephasing kernel.
``backend_unavailable``
    The requested engine is not installed. This is a property of the *environment*, not of the
    circuit, and it never counts as a comparison.
``inconclusive``
    The budget or a node limit was reached without a decision.
``internal_error``
    The engine raised something it should not have. The exception type and message are kept.
``unsupported_input``
    The manifest marks the file out of the accepted gate grammar (``c2_182``).

``UNSUPPORTED_INPUT`` and ``BACKEND_UNAVAILABLE`` must never be aliased: one is about the input,
the other about the machine.
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from symq.backends import BACKENDS, has_native
from symq.circuit import UnsupportedOperation
from symq.corpus import CorpusEntry, load_corpus
from symq.equivalence import check_equivalence
from symq.generators import mutate
from symq.resources import Budget, ResourceLimitExceeded

MANIFEST = Path("benchmarks/corpus/qcec/MANIFEST.json")

CLASSICAL_NATIVE_MAX_WIRES = 64
"""``make_algebra(backend, width)``: one ZDD variable per wire, ``uint64_t`` mask."""

COHERENT_PAIR_MAX_DATA = 32
"""``check_full_channel``: two coherent copies, so ``2 * n_data <= 64``. Unused here."""

EQUIVALENT = "equivalent"
OUTPUT_DIFFERENCE = "output_difference"
INCONCLUSIVE = "inconclusive"
INTERNAL_ERROR = "internal_error"
UNSUPPORTED_INPUT = "unsupported_input"
BACKEND_UNAVAILABLE = "backend_unavailable"

OUTCOMES = (
    EQUIVALENT,
    OUTPUT_DIFFERENCE,
    INCONCLUSIVE,
    INTERNAL_ERROR,
    UNSUPPORTED_INPUT,
    BACKEND_UNAVAILABLE,
)
"""Every outcome this harness can report. There is deliberately no ``unsupported`` catch-all and no
``kernel_difference`` or ``phase_difference``: the classical grammar has no phase."""

DECIDED = (EQUIVALENT, OUTPUT_DIFFERENCE)

NATIVE = "zdd-native"
PURE = "zdd"


def native_available() -> bool:
    """Whether the C extension is importable right now."""
    return has_native() and NATIVE in BACKENDS


@dataclass(frozen=True)
class CaseResult:
    """One (circuit, backend, repetition) measurement."""

    name: str
    width: int
    gates: int
    split: str
    backend: str
    outcome: str
    load_seconds: float | None = None
    mutate_seconds: float | None = None
    verify_seconds: float | None = None
    detail: str = ""
    witness: int | None = None
    """Concrete input assignment on which the pair differs, as reported by the checker."""
    repetition: int = 0
    mutation: str = ""
    equivalent_pair: bool = False
    """True when the compared pair is a semantics-preserving rewrite, not a mutant."""

    @property
    def decided(self) -> bool:
        return self.outcome in DECIDED

    @property
    def seconds(self) -> float | None:
        """Verification time only, so it is comparable across repetitions."""
        return self.verify_seconds


def circuit_seed(seed: int, name: str) -> int:
    """Campaign seed mixed with the circuit name.

    ``random.Random(seed)`` restarted on every file would draw the same first mutation kind for the
    whole corpus. Folding the name in keeps the draw deterministic and lets one campaign cover more
    than one edit.
    """
    mixed = seed & 0xFFFFFFFF
    for character in name:
        mixed = (mixed * 16777619 + ord(character)) & 0xFFFFFFFF
    return mixed


def backend_problem(backend: str, width: int) -> str | None:
    """Why this backend cannot run this circuit, or ``None`` when it can.

    A missing engine and an out-of-range width are both *capability* statements. They are reported as
    ``backend_unavailable`` and never as an unsupported input.
    """
    if backend == NATIVE and not native_available():
        return "native C extension not built"
    if backend not in BACKENDS:
        return f"unknown backend {backend!r}"
    if backend == NATIVE and width > CLASSICAL_NATIVE_MAX_WIRES:
        return f"width {width} exceeds the {CLASSICAL_NATIVE_MAX_WIRES}-wire native mask"
    return None


def _run(
    entry: CorpusEntry,
    backend: str,
    *,
    max_seconds: float,
    seed: int,
    repetition: int = 0,
    equivalent_pair: bool = False,
) -> CaseResult:
    """Compare one corpus circuit against a deterministic edit of itself."""
    problem = backend_problem(backend, entry.width)
    if problem is not None:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            BACKEND_UNAVAILABLE,
            detail=problem,
            repetition=repetition,
            equivalent_pair=equivalent_pair,
        )
    started = time.perf_counter()
    try:
        circuit = entry.load()
    except UnsupportedOperation as exc:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            UNSUPPORTED_INPUT,
            detail=str(exc)[:120],
            repetition=repetition,
        )
    except OSError as exc:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            INTERNAL_ERROR,
            detail=f"{type(exc).__name__}: {exc}"[:120],
            repetition=repetition,
        )
    load_seconds = time.perf_counter() - started

    if equivalent_pair:
        from symq.generators import equivalent_variant

        started = time.perf_counter()
        edited = equivalent_variant(circuit, random.Random(circuit_seed(seed, entry.name)), steps=12)
        kind = "equivalent_variant"
    else:
        started = time.perf_counter()
        edited, kind = mutate(circuit, random.Random(circuit_seed(seed, entry.name)))
    mutate_seconds = time.perf_counter() - started

    started = time.perf_counter()
    try:
        verdict = check_equivalence(
            circuit, edited, backend=backend, budget=Budget(max_seconds=max_seconds)
        )
    except ResourceLimitExceeded as exc:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            INCONCLUSIVE,
            load_seconds,
            mutate_seconds,
            time.perf_counter() - started,
            str(exc)[:120],
            repetition=repetition,
            mutation=kind,
            equivalent_pair=equivalent_pair,
        )
    except UnsupportedOperation as exc:
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            UNSUPPORTED_INPUT,
            load_seconds,
            mutate_seconds,
            time.perf_counter() - started,
            str(exc)[:120],
            repetition=repetition,
            mutation=kind,
            equivalent_pair=equivalent_pair,
        )
    except Exception as exc:  # noqa: BLE001 - keep the diagnostic, never a verdict
        return CaseResult(
            entry.name,
            entry.width,
            entry.gates,
            entry.split,
            backend,
            INTERNAL_ERROR,
            load_seconds,
            mutate_seconds,
            time.perf_counter() - started,
            f"{type(exc).__name__}: {exc}"[:200],
            repetition=repetition,
            mutation=kind,
            equivalent_pair=equivalent_pair,
        )
    verify_seconds = time.perf_counter() - started
    outcome = EQUIVALENT if verdict.equivalent else OUTPUT_DIFFERENCE
    detail = kind
    witness = getattr(verdict, "witness", None)
    if not verdict.equivalent:
        detail = f"{kind}; first differing output wire {verdict.output}"
    return CaseResult(
        entry.name,
        entry.width,
        entry.gates,
        entry.split,
        backend,
        outcome,
        load_seconds,
        mutate_seconds,
        verify_seconds,
        detail,
        witness if isinstance(witness, int) else None,
        repetition,
        kind,
        equivalent_pair,
    )


def requested_backends(*, require_native: bool = False) -> tuple[str, ...]:
    """Which engines this environment can actually exercise.

    ``require_native=True`` is for the environment that *did* build the C core: a silent fallback
    there would turn a broken build into a green run, so it is an error.
    """
    if require_native and not native_available():
        raise RuntimeError(
            "require_native=True but the native C extension is not importable; "
            "this is an environment failure, not an unsupported circuit"
        )
    return (PURE, NATIVE) if native_available() else (PURE,)


def qualify(
    *,
    max_seconds: float = 30.0,
    backends: tuple[str, ...] | None = None,
    seed: int = 1234,
    repetitions: int = 1,
    equivalent_pairs: bool = False,
    require_native: bool = False,
):
    """Run every supported corpus entry on every available backend; return manifest rows and coverage."""
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    chosen = backends if backends is not None else requested_backends(require_native=require_native)
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
                    UNSUPPORTED_INPUT,
                    detail=entry.reason or "manifest",
                )
            )
            continue
        for repetition in range(repetitions):
            order = list(chosen)
            random.Random(circuit_seed(seed, entry.name) + repetition).shuffle(order)
            for backend in order:
                rows.append(
                    _run(
                        entry,
                        backend,
                        max_seconds=max_seconds,
                        seed=seed,
                        repetition=repetition,
                        equivalent_pair=equivalent_pairs,
                    )
                )
    return corpus.manifest, rows


def agreement(rows: list[CaseResult]) -> tuple[int, int, list[str]]:
    """Circuits where both backends reached the **same decided** verdict.

    A pair needs two *available* engines and two *decided* rows. Two ``inconclusive`` rows are not
    agreement, and an unavailable backend is not a disagreement -- it is no comparison at all.
    """
    per: dict[tuple[str, int], dict[str, CaseResult]] = {}
    for row in rows:
        if row.backend == "-":
            continue
        per.setdefault((row.name, row.repetition), {})[row.backend] = row
    agree = comparable = 0
    disagreements: list[str] = []
    for (name, _repetition), by_backend in per.items():
        decided = {backend: row for backend, row in by_backend.items() if row.decided}
        if len(decided) < 2:
            continue
        comparable += 1
        if len({row.outcome for row in decided.values()}) == 1:
            agree += 1
        else:
            disagreements.append(name)
    return agree, comparable, disagreements


def summary(rows: list[CaseResult]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row.backend}:{row.outcome}"
        counts[key] = counts.get(key, 0) + 1
    agree, comparable, disagreements = agreement(rows)
    per_backend: dict[str, dict[str, object]] = {}
    for backend in sorted({row.backend for row in rows} - {"-"}):
        cases = [row for row in rows if row.backend == backend]
        durations = [row.verify_seconds for row in cases if row.verify_seconds is not None]
        per_backend[backend] = {
            "cases": len(cases),
            "decided": len([row for row in cases if row.decided]),
            "equivalent": len([row for row in cases if row.outcome == EQUIVALENT]),
            "output_difference": len([row for row in cases if row.outcome == OUTPUT_DIFFERENCE]),
            "inconclusive": len([row for row in cases if row.outcome == INCONCLUSIVE]),
            "internal_error": len([row for row in cases if row.outcome == INTERNAL_ERROR]),
            "backend_unavailable": len(
                [row for row in cases if row.outcome == BACKEND_UNAVAILABLE]
            ),
            "median_seconds": sorted(durations)[len(durations) // 2] if durations else None,
        }
    return {
        "proof_class": "FULL_CLASSICAL (no measurement, no phase)",
        "native_available": native_available(),
        "rows": len(rows),
        "counts": counts,
        "agreeing": agree,
        "comparable": comparable,
        "disagreements": disagreements,
        "per_backend": per_backend,
    }


def split_totals(rows: list[CaseResult]) -> dict[str, dict[str, int]]:
    """Per-split counts of distinct circuits, so DEV/holdout/extension stay visibly separate."""
    totals: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for row in rows:
        if row.name in seen:
            continue
        seen.add(row.name)
        bucket = totals.setdefault(
            row.split, {"circuits": 0, "decided": 0, "undecided": 0, "unavailable": 0}
        )
        bucket["circuits"] += 1
        if row.decided:
            bucket["decided"] += 1
        elif row.outcome == BACKEND_UNAVAILABLE:
            bucket["unavailable"] += 1
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
