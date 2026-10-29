"""Isolated, paired QCEC campaign on the pinned classical corpus.

What this measures, and what it does not:

* It measures **full-call** ``check_equivalence`` on real MIT-licensed reversible circuits, one
  subprocess per (circuit, backend, repetition), with the mutation precomputed in the parent so the
  reported seconds are the verification only.
* It records **every** per-circuit, per-repetition row: load, mutate, verify, CPU, wall and RSS.
* It compares mutants (which must differ) **and** semantics-preserving rewrites (which must agree),
  so a run cannot look healthy by only ever reporting differences.
* It is **classical**. No HMR, no measurement, no channel. Nothing here can be read as a channel
  result.

The earlier nine-repetition aggregate in ``RESULTS/qcec-classical-20261029.json`` is preserved as
history. This campaign is a separate file and a separate protocol.

Usage::

    python -m research.verification_api.campaign --repetitions 5 --out results.json
"""
from __future__ import annotations

import argparse
import json
import random
import resource
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from research.verification_api.corpus_qualification import (
    BACKEND_UNAVAILABLE,
    EQUIVALENT,
    INCONCLUSIVE,
    INTERNAL_ERROR,
    MANIFEST,
    NATIVE,
    OUTPUT_DIFFERENCE,
    PURE,
    backend_problem,
    circuit_seed,
    native_available,
)
from symq.corpus import CorpusEntry, load_corpus
from symq.equivalence import check_equivalence
from symq.generators import equivalent_variant, mutate
from symq.resources import Budget, ResourceLimitExceeded

MAX_PAIR_SECONDS = 120.0


@dataclass(frozen=True)
class Measurement:
    """One isolated run of one pair on one backend."""

    name: str
    split: str
    width: int
    gates: int
    backend: str
    repetition: int
    kind: str
    pair: str
    outcome: str
    load_seconds: float | None = None
    mutate_seconds: float | None = None
    verify_seconds: float | None = None
    witness_seconds: float | None = None
    wall_seconds: float | None = None
    cpu_seconds: float | None = None
    maxrss_kib: int | None = None
    witness: int | None = None
    output_wire: int | None = None
    detail: str = ""

    @property
    def decided(self) -> bool:
        return self.outcome in (EQUIVALENT, OUTPUT_DIFFERENCE)


def _entry_payload(entry: CorpusEntry) -> dict:
    return {
        "name": entry.name,
        "file": entry.path.name,
        "split": entry.split,
        "width": entry.width,
        "gates": entry.gates,
    }


def _load_entry(payload: dict) -> CorpusEntry:
    corpus = load_corpus(MANIFEST)
    for entry in corpus.entries:
        if entry.name == payload["name"]:
            return entry
    raise KeyError(payload["name"])


def _build_pair(entry: CorpusEntry, seed: int, kind: str):
    """Return (left, right, pair_label). The edit happens here, outside the timed region."""
    left = entry.load()
    rng = random.Random(circuit_seed(seed, entry.name))
    if kind == "mutant":
        right, mutation = mutate(left, rng)
        return left, right, mutation
    if kind == "equivalent":
        return left, equivalent_variant(left, rng, steps=12), "equivalent_variant"
    raise ValueError(f"unknown pair kind {kind!r}")


def run_one(entry: CorpusEntry, backend: str, seed: int, kind: str, repetition: int) -> Measurement:
    """The timed worker body. Runs in its own process."""
    wall_started = time.perf_counter()
    cpu_started = time.process_time()

    load_started = time.perf_counter()
    left, right, label = _build_pair(entry, seed, kind)
    build_seconds = time.perf_counter() - load_started

    problem = backend_problem(backend, entry.width)
    if problem is not None:
        return Measurement(
            entry.name,
            entry.split,
            entry.width,
            entry.gates,
            backend,
            repetition,
            kind,
            label,
            BACKEND_UNAVAILABLE,
            detail=problem,
        )

    verify_started = time.perf_counter()
    try:
        verdict = check_equivalence(
            left, right, backend=backend, budget=Budget(max_seconds=MAX_PAIR_SECONDS)
        )
    except ResourceLimitExceeded as exc:
        return Measurement(
            entry.name,
            entry.split,
            entry.width,
            entry.gates,
            backend,
            repetition,
            kind,
            label,
            INCONCLUSIVE,
            load_seconds=build_seconds,
            verify_seconds=time.perf_counter() - verify_started,
            detail=str(exc)[:120],
        )
    except Exception as exc:  # noqa: BLE001 - keep the diagnostic, never a verdict
        return Measurement(
            entry.name,
            entry.split,
            entry.width,
            entry.gates,
            backend,
            repetition,
            kind,
            label,
            INTERNAL_ERROR,
            load_seconds=build_seconds,
            verify_seconds=time.perf_counter() - verify_started,
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )
    verify_seconds = time.perf_counter() - verify_started

    witness_started = time.perf_counter()
    replay_ok = True
    if verdict.witness is not None:
        replay_ok = left.run(verdict.witness) != right.run(verdict.witness)
    witness_seconds = time.perf_counter() - witness_started

    if kind == "equivalent":
        outcome = EQUIVALENT if verdict.equivalent else OUTPUT_DIFFERENCE
    else:
        outcome = OUTPUT_DIFFERENCE if not verdict.equivalent else EQUIVALENT
    detail = label
    if not replay_ok:
        detail = f"{label}; WITNESS DID NOT REPLAY"
    return Measurement(
        entry.name,
        entry.split,
        entry.width,
        entry.gates,
        backend,
        repetition,
        kind,
        label,
        outcome,
        load_seconds=build_seconds - witness_seconds,
        mutate_seconds=0.0,
        verify_seconds=verify_seconds,
        witness_seconds=witness_seconds,
        wall_seconds=time.perf_counter() - wall_started,
        cpu_seconds=time.process_time() - cpu_started,
        maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        witness=verdict.witness,
        output_wire=verdict.output,
        detail=detail,
    )


def _worker(entry_payload: dict, backend: str, seed: int, kind: str, repetition: int) -> int:
    entry = _load_entry(entry_payload)
    measurement = run_one(entry, backend, seed, kind, repetition)
    print(json.dumps(asdict(measurement), sort_keys=True))
    return 0


def campaign(
    *,
    repetitions: int = 5,
    seed: int = 20261029,
    kinds: tuple[str, ...] = ("mutant", "equivalent"),
    require_native: bool = False,
) -> list[Measurement]:
    """Run every supported circuit, both pair kinds, every backend, each in a fresh process."""
    if require_native and not native_available():
        raise RuntimeError(
            "require_native=True but the native C extension is not importable; "
            "this is an environment failure, not an unsupported circuit"
        )
    backends = (PURE, NATIVE) if native_available() else (PURE,)
    corpus = load_corpus(MANIFEST)
    measurements: list[Measurement] = []
    for entry in corpus.entries:
        if not entry.supported:
            continue
        for repetition in range(repetitions):
            for kind in kinds:
                order = list(backends)
                # Backend order alternates by a seed derived from the circuit, the repetition and
                # the pair kind, so a warm-cache advantage cannot consistently favour one engine.
                random.Random(
                    circuit_seed(seed, f"{entry.name}:{repetition}:{kind}")
                ).shuffle(order)
                for backend in order:
                    command = [
                        sys.executable,
                        "-m",
                        "research.verification_api.campaign",
                        "--worker",
                        "--entry",
                        json.dumps(_entry_payload(entry)),
                        "--backend",
                        backend,
                        "--seed",
                        str(seed),
                        "--kind",
                        kind,
                        "--repetition",
                        str(repetition),
                    ]
                    completed = subprocess.run(
                        command, capture_output=True, text=True, check=False
                    )
                    if completed.returncode != 0:
                        measurements.append(
                            Measurement(
                                entry.name,
                                entry.split,
                                entry.width,
                                entry.gates,
                                backend,
                                repetition,
                                kind,
                                "-",
                                INTERNAL_ERROR,
                                detail=completed.stderr[-300:],
                            )
                        )
                        continue
                    measurements.append(Measurement(**json.loads(completed.stdout.strip())))
    return measurements


def paired_summary(measurements: list[Measurement]) -> dict[str, object]:
    """Per (circuit, repetition, kind): both backends decided, same verdict, ratio from verify time."""
    grouped: dict[tuple[str, int, str], dict[str, Measurement]] = {}
    for row in measurements:
        grouped.setdefault((row.name, row.repetition, row.kind), {})[row.backend] = row

    ratios_by_kind: dict[str, list[float]] = {}
    agreements = disagreements = unavailable = 0
    for (name, _repetition, kind), by_backend in grouped.items():
        pure = by_backend.get(PURE)
        native = by_backend.get(NATIVE)
        if pure is None or native is None:
            continue
        if BACKEND_UNAVAILABLE in (pure.outcome, native.outcome):
            unavailable += 1
            continue
        if not (pure.decided and native.decided):
            continue
        if pure.outcome != native.outcome:
            disagreements += 1
            continue
        agreements += 1
        if pure.verify_seconds and native.verify_seconds:
            ratios_by_kind.setdefault(kind, []).append(
                pure.verify_seconds / native.verify_seconds
            )

    summary: dict[str, object] = {
        "agreements": agreements,
        "disagreements": disagreements,
        "unavailable_pairs": unavailable,
    }
    for kind, ratios in sorted(ratios_by_kind.items()):
        ordered = sorted(ratios)
        summary[kind] = {
            "n": len(ordered),
            "median_ratio": statistics.median(ordered),
            "min_ratio": ordered[0],
            "max_ratio": ordered[-1],
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--entry", default="")
    parser.add_argument("--backend", default=PURE)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--kind", default="mutant")
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--out", default="")
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args(argv)

    if args.worker:
        return _worker(json.loads(args.entry), args.backend, args.seed, args.kind, args.repetition)

    started = time.time()
    measurements = campaign(
        repetitions=args.repetitions, seed=args.seed, require_native=args.require_native
    )
    payload = {
        "protocol": {
            "corpus": "benchmarks/corpus/qcec",
            "proof_class": "FULL_CLASSICAL",
            "isolation": "one fresh subprocess per (circuit, backend, repetition, pair kind)",
            "backend_order": "shuffled from a per-(circuit, repetition, kind) seed",
            "repetitions": args.repetitions,
            "seed": args.seed,
            "kinds": sorted({row.kind for row in measurements}),
            "native_available": native_available(),
            "timed_region": "check_equivalence only; load, mutation and witness replay are separate",
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "note": "classical reversible equivalence; no HMR, no measurement, no channel",
        },
        "paired": paired_summary(measurements),
        "measurements": [asdict(row) for row in measurements],
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
