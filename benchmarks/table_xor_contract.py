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
from symq.labs.table_xor_contract import TableXorContract, check_table_xor
from symq.resources import Budget


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
        max_seconds: float, max_states: int) -> dict:
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
        report["inputs"] = {
            "contract_file_sha256": spec_hash, "source_file_sha256": source_hash,
            "contract_sha256": spec.sha256,
        }
    except Exception as exc:  # noqa: BLE001 - an invalid input must leave JSON evidence
        report["setup_error"] = {"type": type(exc).__name__, "reason": str(exc)}
        return report

    for repetition in range(repetitions):
        row = {"repetition": repetition, "qualified": False}
        started = time.perf_counter()
        tracemalloc.start()
        try:
            result = check_table_xor(
                candidate, spec, backend=backend,
                budget=Budget(max_seconds=max_seconds), max_states=max_states)
            row["result"] = result.to_dict()
            row["qualified"] = result.equivalent
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.source, args.contract, backend=args.backend,
                 repetitions=args.repetitions, max_seconds=args.max_seconds,
                 max_states=args.max_states)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
