"""Bounded synthetic stage qualification; no real-source performance claim.

python -m benchmarks.indexed_substitution --output /tmp/indexed-composition.json
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import platform
import random
import resource
import sys
import tempfile
import time
from pathlib import Path

from symq import Circuit
from symq.hashing import canonical_sha256
from symq.labs.indexed_substitution import (
    check_indexed_substitution,
    replay_indexed_substitution,
)
from symq.labs.kmx_source_index import build_kmx_index
from symq.resources import Budget


def run(repetitions=3):
    rows = []
    schedule = [(size, repeat) for repeat in range(repetitions) for size in (100, 10_000)]
    random.Random(20261108).shuffle(schedule)
    for size, repeat in schedule:
        with tempfile.TemporaryDirectory(prefix="symq-composition-dev-") as temporary:
            path = Path(temporary) / "source.kmx"
            raw = b"X q5\n" * size + b"CX q0 q2\nCX q2 q3\n" + b"X q5\n" * size
            path.write_bytes(raw)
            source_pin = hashlib.sha256(raw).hexdigest()
            request = {
                "kind": "symq_indexed_classical_substitution", "schema_version": 1,
                "source_file_sha256": source_pin, "prefix_start_op": 0,
                "op_span": [size + 1, size + 2],
                "replacement": Circuit(1).to_dict(), "replacement_wires": [3],
                "contract": {"initial_assumption": {"kind": "eq",
                    "left": {"kind": "var", "name": "x.0"},
                    "right": {"kind": "var", "name": "x.2"}}, "clean_at_cut": [2]},
            }
            pins = {"expected_source_sha256": source_pin,
                    "expected_request_sha256": canonical_sha256(request)}
            stages = []

            def measure(name, operation, stages=stages):
                wall, cpu = time.perf_counter(), time.process_time()
                status, detail = "ok", None
                try:
                    value = operation()
                    if isinstance(value, dict):
                        status = value.get("status", "ok")
                    return value
                except Exception as error:
                    status, detail = type(error).__name__, str(error)
                    raise
                finally:
                    stages.append({"stage": name, "status": status, "detail": detail,
                                   "wall_seconds": time.perf_counter() - wall,
                                   "cpu_seconds": time.process_time() - cpu,
                                   "process_peak_rss_kib": resource.getrusage(
                                       resource.RUSAGE_SELF).ru_maxrss})
            try:
                index = measure("copy_hash_parse_index", functools.partial(build_kmx_index,
                    path, expected_source_sha256=source_pin, budget=Budget(max_seconds=10)))
                with index:
                    disk_bytes = sum(p.stat().st_size for p in Path(index._directory.name).iterdir())
                    proof = measure("cold_extractions_and_proof", functools.partial(
                        check_indexed_substitution, index, request, **pins,
                        budget=Budget(max_seconds=10)))
                    again = measure("repeated_extractions_and_fresh_proof", functools.partial(
                        check_indexed_substitution, index, request, **pins,
                        budget=Budget(max_seconds=10)))
                    assert proof == again
                replay = measure("rebuild_extract_prove_replay", functools.partial(
                    replay_indexed_substitution, path, request, proof, **pins,
                    budget=Budget(max_seconds=10)))
                assert replay == proof
                row = {"proof_sha256": canonical_sha256(proof),
                       "dependencies_sha256": proof.get("dependencies_sha256"),
                       "extraction_work": {k: v["work"]
                                           for k, v in proof.get("extractions", {}).items()},
                       "index_main_file_bytes": disk_bytes,
                       "status": proof["status"]}
            except Exception as error:  # noqa: BLE001 - retain every failed trial
                row = {"status": "failed", "error": str(error)}
            rows.append({"source_sha256": source_pin, "source_bytes": len(raw),
                         "source_ops": 2 * size + 2, "repeat": repeat,
                         "stages": stages, **row})
    return {"kind": "indexed_composition_synthetic_development_qualification", "version": 1,
            "python": sys.version, "platform": platform.platform(),
            "license": "MIT authored synthetic fixtures", "seed": 20261108,
            "stage_seconds_cap": 10, "independent_oracle": "see test_indexed_substitution.py",
            "rss_semantics": "cumulative_process_peak_not_stage_delta",
            "disk_semantics": "main SQLite file; unlinked snapshot adds source_bytes",
            "not_measured": ["storage_device_bytes", "complete_candidate_economics",
                             "real_corpus_performance"], "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3, choices=range(1, 11))
    args = parser.parse_args()
    report = run(args.repetitions)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if all(r["status"] == "equivalent" for r in report["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
