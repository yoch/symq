"""Autonomous normalized fixtures from a pinned public Qualtran decomposition.

Qualtran is optional and imported only by the regeneration tool. A fixture is
an inspectable import artifact, not a certificate of its claimed provenance.
The full channel claim is checked separately, after its zero-ancilla preparer.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from symq.circuit import UnsupportedOperation
from symq.experimental.importers import parse_phase_stream
from symq.phase import PhaseProgram

QUALTRAN_COMMIT = "638777fac4379bc62e2a1e4a52cf1a1753895d48"
QUALTRAN_SOURCE = "qualtran/bloqs/gf_arithmetic/gf2_multiplication.py"
QUALTRAN_SOURCE_SHA256 = "c9542e34532eb3ca978a3405a9947c5e49c522d519834f5d5feac1051387b229"


@dataclass(frozen=True)
class QualtranFixture:
    degree: int
    preparer: str
    cleanup: str
    provenance_json: str

    def __post_init__(self):
        if type(self.degree) is not int or self.degree not in (1, 2):
            raise UnsupportedOperation("qualified Qualtran fixture degree must be 1 or 2")
        if any(type(value) is not str for value in (
                self.preparer, self.cleanup, self.provenance_json)):
            raise UnsupportedOperation("fixture streams and provenance must be strings")

    def programs(self) -> tuple[PhaseProgram, PhaseProgram]:
        """Prepared reversible inverse versus prepared measurement cleanup."""
        prep = parse_phase_stream(self.preparer, data=2 * self.degree,
                                  ancillas=self.degree).program
        candidate = parse_phase_stream(self.preparer + "\n" + self.cleanup,
                                       data=prep.data, ancillas=prep.ancillas).program
        # Every preparer opcode is a self-inverse permutation gate. This is the
        # inverse of the imported circuit, not another multiplication algorithm.
        reference = PhaseProgram(prep.data, prep.ancillas, prep.ops + list(reversed(prep.ops)))
        reference.validate()
        return reference, candidate


def fixture_digest(preparer: str, cleanup: str) -> str:
    return hashlib.sha256((preparer + "\n---\n" + cleanup).encode()).hexdigest()


def load_qualtran_fixture(path: str | Path) -> QualtranFixture:
    payload = json.loads(Path(path).read_text())
    if type(payload) is not dict or set(payload) != {
            "schema_version", "degree", "preparer", "cleanup", "provenance", "contract"}:
        raise UnsupportedOperation("invalid Qualtran fixture fields")
    if payload["schema_version"] != 1 or type(payload["schema_version"]) is not int:
        raise UnsupportedOperation("unsupported Qualtran fixture schema")
    degree = payload["degree"]
    if type(degree) is not int or degree not in (1, 2):
        raise UnsupportedOperation("autonomous qualification supports degrees 1 and 2")
    if any(type(payload[k]) is not str for k in ("preparer", "cleanup")):
        raise UnsupportedOperation("fixture streams must be strings")
    provenance = payload["provenance"]
    if (type(provenance) is not dict or provenance.get("commit") != QUALTRAN_COMMIT
            or provenance.get("license") != "Apache-2.0"
            or provenance.get("source") != QUALTRAN_SOURCE
            or provenance.get("source_sha256") != QUALTRAN_SOURCE_SHA256
            or provenance.get("normalized_sha256") != fixture_digest(
                payload["preparer"], payload["cleanup"])):
        raise UnsupportedOperation("fixture provenance or normalized digest mismatch")
    trace = json.dumps(provenance.get("decomposition_trace"), sort_keys=True)
    if provenance.get("decomposition_trace_sha256") != hashlib.sha256(trace.encode()).hexdigest():
        raise UnsupportedOperation("decomposition trace digest mismatch")
    expected = {
        "data": 2 * degree, "zero_ancillas": degree,
        "precondition": "result register prepared by imported GF2Multiplication",
        "comparison": "full channel on all data coherences after preparation",
        "embedding": "consumed MeasureX wires are returned as terminal |0> wires by HMR",
        "classical_outputs": "discarded",
    }
    contract = payload["contract"]
    if (type(contract) is not dict or contract != expected
            or any(type(contract[k]) is not type(v) for k, v in expected.items())):
        raise UnsupportedOperation("fixture preparation/terminal embedding contract mismatch")
    result = QualtranFixture(degree, payload["preparer"], payload["cleanup"],
                             json.dumps(provenance, sort_keys=True))
    result.programs()  # Validate grammar and invariant-based lowering eagerly.
    return result
