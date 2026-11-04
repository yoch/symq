"""Fixed-code, OS-limited *trusted verifier* of untrusted SAT-miter proposals.

Runs under the Linux RLIMIT_AS/RLIMIT_CPU bootstrap from
isolated_miter_supervisor, separate from the proof-logging producer.
The caller supplies an independently authenticated source SHA, and this
process re-parses the original bytes, reconstructs the normalized CNF,
and validates the positive-hint RUP proof without importing PySAT.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _read_limited(path: str, maximum: int) -> bytes:
    file = Path(path)
    if file.stat().st_size > maximum:
        raise ValueError("verifier input exceeds byte cap")
    with file.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("verifier read exceeds byte cap")
    return data


def main() -> int:
    response: dict = {"schema_version": 1, "status": "inconclusive"}
    try:
        if len(sys.argv) != 12:
            raise ValueError("fixed verifier command arguments required")
        source_path = sys.argv[1]
        proposal_path = sys.argv[2]
        independent_sha = sys.argv[3]
        seconds = float(sys.argv[4])
        request_cap = int(sys.argv[5])
        proposal_cap = int(sys.argv[6])
        max_bytes, max_variables, max_clauses, max_steps, max_visits = (
            int(value) for value in sys.argv[7:]
        )
        if (not math.isfinite(seconds) or not 0 < seconds <= 300 or
                not 1 <= request_cap <= 1048576 or
                not 1 <= proposal_cap <= 16777216):
            raise ValueError("invalid verifier resource settings")

        # Never trust the producer's input, semantic verdict or fingerprint.
        from symq.labs.isolated_miter import parse_isolated_miter_request
        from symq.labs.isolated_miter_supervisor import _decode_response
        from symq.labs.lrat_rup import Limits
        from symq.labs.miter_proof_bundle import check_classical_miter_proof
        from symq.resources import Budget

        source = _read_limited(source_path, request_cap)
        proposal = _decode_response(_read_limited(proposal_path, proposal_cap),
                                    role="producer")
        if proposal["status"] != "proposal":
            raise ValueError("positive source theorem requires a proof proposal")
        left, right, contract = parse_isolated_miter_request(
            source, max_request_bytes=request_cap,
        )
        limits = Limits(
            max_bytes=max_bytes, max_variables=max_variables,
            max_clauses=max_clauses, max_steps=max_steps,
            max_visits=max_visits, max_seconds=seconds,
        )
        checked = check_classical_miter_proof(
            left, right, contract, proposal["bundle"],
            expected_source_sha256=independent_sha,
            budget=Budget(max_seconds=seconds), limits=limits,
        )
        if checked["status"] == "proved" and checked["independent_unsat_checked"]:
            response = {
                "schema_version": 1, "status": "verified",
                "source_sha256": checked["source_sha256"],
                "cnf_sha256": checked["cnf_sha256"],
            }
        elif checked["status"] == "inconclusive":
            response = {"schema_version": 1, "status": "inconclusive"}
        else:
            response = {"schema_version": 1, "status": "invalid"}
    except Exception:  # noqa: BLE001 - malformed proof or OS fault is never positive
        response = {"schema_version": 1, "status": "inconclusive"}
    sys.stdout.write(
        json.dumps(response, sort_keys=True, separators=(",", ":"))
    )
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
