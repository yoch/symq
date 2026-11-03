"""Isolated SAT-miter *producer*, deliberately separate from the trusted consumer.

This module executes only behind a Linux RLIMIT_AS/RLIMIT_CPU bootstrap.
Even if it returns "proposal", the parent must re-encode the original
source and verify the proof with its solver-free RUP checker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    try:
        if len(sys.argv) != 9:
            raise ValueError("worker arguments unavailable")
        path = Path(sys.argv[1])
        duration = float(sys.argv[2])
        request_limit = int(sys.argv[3])
        numbers = tuple(int(n) for n in sys.argv[4:])
        if not 0 < duration <= 300 or not 1 <= request_limit <= 1048576:
            raise ValueError("worker duration/input size outside range")
        if path.stat().st_size > request_limit:
            raise ValueError("worker input file too large")
        with path.open("rb") as stream:
            request = stream.read(request_limit + 1)
        if len(request) > request_limit:
            raise ValueError("worker input limit")

        from symq.labs.isolated_miter import parse_isolated_miter_request
        from symq.labs.lrat_rup import Limits
        from symq.labs.miter_proof_bundle import export_classical_miter_proof
        from symq.resources import Budget

        left, right, contract = parse_isolated_miter_request(
            request, max_request_bytes=request_limit,
        )
        bound = Limits(
            max_bytes=numbers[0], max_variables=numbers[1],
            max_clauses=numbers[2], max_steps=numbers[3],
            max_visits=numbers[4], max_seconds=duration,
        )
        outcome = export_classical_miter_proof(
            left, right, contract, budget=Budget(max_seconds=duration),
            limits=bound,
        )
        if outcome["status"] == "proved" and type(outcome.get("bundle")) is dict:
            response = {"schema_version": 1, "status": "proposal",
                        "bundle": outcome["bundle"]}
        else:
            status = outcome["status"]
            if status not in {"not_proved", "inconclusive", "unsupported", "invalid"}:
                status = "inconclusive"
            response = {"schema_version": 1, "status": status}
    except Exception:  # noqa: BLE001 - invalid/unavailable child can never certify
        # Error handling in the child is never a source-level verdict.
        response = {"schema_version": 1, "status": "inconclusive"}
    sys.stdout.buffer.write(
        json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
