"""Reproducible, development-only table-to-emitted-circuit qualification.

Run via python -m benchmarks.table_xor_contract from the public checkout.
The input table and candidate are separate files; they must be independently
supplied and pinned by a consumer. Never import the emitter's PASS verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
import tracemalloc
from pathlib import Path

from benchmarks.environment import machine, receipt
from symq.circuit import circuit_from_dict
from symq.hashing import canonical_sha256
from symq.labs.table_xor_contract import (
    TableXorContract,
    check_table_xor,
    replay_table_xor,
)
from symq.resources import Budget, VerificationSession


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _read(path: Path):
    raw = path.read_bytes()
    return json.loads(raw, object_pairs_hook=_unique_pairs), hashlib.sha256(raw).hexdigest()


def run(source: Path, contract: Path, *, backend: str, repetitions: int,
        max_seconds: float, max_states: int,
        expected_source_sha256: str | None = None,
        expected_contract_sha256: str | None = None) -> dict:
    if type(repetitions) is not int or not 1 <= repetitions <= 30:
        raise ValueError("repetitions must be 1..30")
    if type(max_seconds) is not float or not 0 < max_seconds <= 300:
        raise ValueError("each call needs a max_seconds in (0,300]")
    report = {
        "schema_version": 1, "kind": "symq_table_xor_qualification",
        "origin": "synthetic development example, no holdout",
        "environment": machine(), "provenance": receipt(),
        "backend": backend, "repetitions": repetitions, "trials": [],
        "qualified": False,
    }
    try:
        spec_data, spec_hash = _read(contract)
        source_data, source_hash = _read(source)
        spec = TableXorContract.from_dict(spec_data)
        candidate = circuit_from_dict(source_data)
        consumer_pins = expected_source_sha256 is not None and expected_contract_sha256 is not None
        if (expected_source_sha256 is None) != (expected_contract_sha256 is None):
            raise ValueError("supply both consumer pins or neither")
        if not consumer_pins:
            # Without external pins the replay can only re-check the files read here.
            expected_source_sha256 = canonical_sha256(candidate.to_dict())
            expected_contract_sha256 = spec.sha256
        report["inputs"] = {
            "contract_file_sha256": spec_hash, "source_file_sha256": source_hash,
            "contract_sha256": spec.sha256,
            "source_sha256": canonical_sha256(candidate.to_dict()),
            "pins": {"origin": ("consumer" if consumer_pins
                                else "self-derived from the input files"),
                     "source_sha256": expected_source_sha256,
                     "contract_sha256": expected_contract_sha256},
        }
    except Exception as exc:  # noqa: BLE001 - an invalid input must leave JSON evidence
        report["setup_error"] = {"type": type(exc).__name__, "reason": str(exc)}
        return report

    for repetition in range(repetitions):
        row = {"repetition": repetition, "qualified": False}
        started = time.perf_counter()
        tracemalloc.start()
        try:
            with VerificationSession(Budget(max_seconds=max_seconds)):
                result = check_table_xor(
                    candidate, spec, backend=backend,
                    budget=Budget(max_seconds=max_seconds), max_states=max_states)
                row["result"] = result.to_dict()
                if result.equivalent:
                    replay_started = time.perf_counter()
                    replayed = replay_table_xor(
                        candidate, spec, result.to_dict(),
                        expected_source_sha256=expected_source_sha256,
                        expected_contract_sha256=expected_contract_sha256,
                        backend=backend, budget=Budget(max_seconds=max_seconds),
                        max_states=max_states)
                    row["replay"] = replayed.to_dict()
                    row["replay_seconds"] = time.perf_counter() - replay_started
                    row["qualified"] = replayed.equivalent
        except Exception as exc:  # noqa: BLE001 - every failed trial is retained
            row["error"] = {"type": type(exc).__name__, "reason": str(exc)}
        finally:
            row["elapsed_seconds"] = time.perf_counter() - started
            row["python_peak_bytes"] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            row["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            report["trials"].append(row)
    report["qualified"] = all(row["qualified"] for row in report["trials"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--backend", choices=["sat", "exhaustive"], default="sat")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-seconds", type=float, default=10.0)
    parser.add_argument("--max-states", type=int, default=65536)
    parser.add_argument("--expected-source-sha256",
                        help="consumer pin of the canonical source (with the contract pin)")
    parser.add_argument("--expected-contract-sha256",
                        help="consumer pin of the canonical contract (with the source pin)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.source, args.contract, backend=args.backend,
                 repetitions=args.repetitions, max_seconds=args.max_seconds,
                 max_states=args.max_states,
                 expected_source_sha256=args.expected_source_sha256,
                 expected_contract_sha256=args.expected_contract_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
