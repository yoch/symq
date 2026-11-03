"""Prepare an exact local classical rewrite for the existing proof CLI.

This is a structural *preparation*, NOT a proof. All accepted spans and
local-to-global maps must come from one exact, complete occurrence of the
original block. The global replacement is lowered mechanically, then the
normal checker proves the actual contextual/total theorem.

No ancilla cleanliness, input-domain restriction, borrowed-wire restoration
or engine capability is inferred. A caller supplies an explicit contract.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from symq.circuit import Circuit, Gate
from symq.experimental.serialization import encode_json
from symq.hashing import canonical_sha256
from symq.labs.classical_transcript import Program, digest
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import Weights
from symq.labs.rewrite_locator import locate_exact
from symq.labs.rewrite_request import (
    CLASSICAL_ENGINES,
    MAX_INPUT_BYTES,
    REQUEST_KIND,
    RewriteRequest,
    request_from_dict,
    request_to_dict,
)

__all__ = ["PreparedLocalRewrite", "prepare_local_classical", "write_prepared_rewrite"]


@dataclass(frozen=True)
class PreparedLocalRewrite:
    """Immutable decision about preparation; a report is NEVER a proof receipt."""

    location: dict[str, Any]
    request: RewriteRequest | None
    source_sha256: str
    reference_sha256: str
    local_candidate_sha256: str
    location_sha256: str
    request_sha256: str | None

    @property
    def ready(self) -> bool:
        return self.request is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "kind": "symq_rewrite_preparation",
            "status": "ready_for_proof" if self.ready else self.location["status"],
            "advisory_only": True, "proved": False, "candidate_authorized": False,
            "ready_for_proof": self.ready,
            "location": self.location,
            "source_sha256": self.source_sha256,
            "reference_sha256": self.reference_sha256,
            "local_candidate_sha256": self.local_candidate_sha256,
            "location_sha256": self.location_sha256,
            "request_sha256": self.request_sha256,
        }


def _map_gates(circuit: Circuit, wires: tuple[int, ...], global_width: int) -> Circuit:
    if type(circuit) is not Circuit or type(wires) is not tuple:
        raise TypeError("a Circuit and an explicit tuple wire map are required")
    circuit.validate()
    if (len(wires) != circuit.width or len(set(wires)) != len(wires)
            or any(type(q) is not int or not 0 <= q < global_width for q in wires)):
        raise ValueError("the complete local-to-global map must be injective and in range")
    return Circuit(global_width, [
        Gate(gate.name, tuple(wires[q] for q in gate.qubits))
        for gate in circuit.gates
    ])


def prepare_local_classical(
    source: Circuit, reference: Circuit, replacement: Circuit, *,
    contract: SubstitutionContract, weights: Weights | None = None,
    engine: str = "sat", require_saving: bool = False,
    max_candidates: int = 128, max_compares: int = 2_000_000,
) -> PreparedLocalRewrite:
    """Find exactly one complete reference occurrence; build a frozen global request.

    Repeated or partially mapped occurrences return a non-actionable record,
    never a guessed choice. A wrong local replacement is still *prepared* but
    will be rejected by the proof engine, not by the locator.
    """
    if any(type(x) is not Circuit for x in (source, reference, replacement)):
        raise TypeError("source/reference/replacement must be classical reversible Circuits")
    for circuit in (source, reference, replacement):
        circuit.validate()
    if replacement.width != reference.width:
        raise ValueError("local original and replacement must have the same wire width")
    if type(contract) is not SubstitutionContract:
        raise TypeError("pass an explicit SubstitutionContract, even when empty")
    contract.validate(source.width)
    if type(engine) is not str or engine not in CLASSICAL_ENGINES:
        raise ValueError("unsupported classical rewrite engine")
    if engine not in ("sat", "auto") and contract != SubstitutionContract():
        raise ValueError("symbolic total engines cannot discharge contextual cut contracts")
    if type(require_saving) is not bool:
        raise ValueError("require_saving must be Boolean")
    if weights is None:
        weights = Weights()
    if type(weights) is not Weights:
        raise TypeError("weights must be typed Weights")

    # Freeze NOW. A caller mutating its original Circuit after preparation
    # cannot silently change the proof request.
    frozen_source = Program.freeze(source).circuit()
    frozen_reference = Program.freeze(reference).circuit()
    frozen_candidate = Program.freeze(replacement).circuit()
    location = locate_exact(
        frozen_source, frozen_reference,
        max_candidates=max_candidates, max_compares=max_compares,
    )
    candidate_hash = digest(Program.freeze(frozen_candidate))
    reference_hash = digest(Program.freeze(frozen_reference))
    source_hash = digest(Program.freeze(frozen_source))
    location_hash = canonical_sha256(location)
    if location["status"] != "unique":
        return PreparedLocalRewrite(
            location, None, source_hash, reference_hash, candidate_hash,
            location_hash, None,
        )
    match = location["matches"][0]
    wires = tuple(match["wires"])
    # Complete map, exact contiguous reference. This is a defensive check,
    # independent of the locator's returned status string.
    original_mapped = _map_gates(frozen_reference, wires, frozen_source.width)
    start, stop = match["span"]
    if tuple(original_mapped.gates) != tuple(frozen_source.gates[start:stop]):
        raise ValueError("the mapped local original does not equal the located source interval")

    candidate_mapped = _map_gates(frozen_candidate, wires, frozen_source.width)
    request = RewriteRequest(
        "classical", frozen_source, candidate_mapped,
        (start, stop), contract, weights, require_saving, engine,
    )
    # Validate *exactly* the same request parser that the proof CLI uses.
    doc = request_to_dict(request)
    checked = request_from_dict(doc)
    if checked != request:
        raise ValueError("the prepared rewrite did not round-trip through the proof schema")
    return PreparedLocalRewrite(
        location, request, source_hash, reference_hash, candidate_hash,
        location_hash, canonical_sha256(doc),
    )


def write_prepared_rewrite(
    prepared: PreparedLocalRewrite, directory: str | Path,
    *, file_sha256: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a new directory containing a proof-READY request, but NO proof.

    Never replace anything. Every file is serialized and size-checked first, in
    memory (the same bytes `save_json` writes). The destination is then claimed with
    ``os.mkdir`` (fails on ANY existing entry, including an empty directory, a
    file or a symlink), and each file is created with exclusive ``'x'`` mode.
    Files are written and fsynced one at a time in ``PUBLICATION_ORDER``:
    ``source.json`` and ``replacement.json`` before ``request.json``, which
    names them, and the ``preparation.json`` record last. This is no-replace
    publication, NOT atomic visibility of the whole directory: a concurrent
    reader or a crash can observe a prefix of that sequence. The marker is
    therefore advisory metadata (it records the emitted file hashes), not a
    lock. ``symq rewrite`` never relies on it: on any intermediate state it
    either refuses the input (missing or truncated file) or proves exactly
    the complete bytes it read, and a preparation never authorizes a
    candidate. On failure after the claim, only the files this call created
    are removed, then the directory if it is still empty. The input
    provenance is historical SHA-256 data, not a certificate of equivalence.
    """
    if type(prepared) is not PreparedLocalRewrite or not prepared.ready:
        raise ValueError("only a unique complete match can be written")
    request = prepared.request
    assert request is not None
    # The returned object contains mutable Circuit lists and location dictionaries.
    # Revalidate all pins at publication time; no stale or edited preparation
    # may claim the hashes of an earlier source/candidate.
    if (digest(Program.freeze(request.source)) != prepared.source_sha256
            or canonical_sha256(prepared.location) != prepared.location_sha256
            or canonical_sha256(request_to_dict(request)) != prepared.request_sha256):
        raise ValueError("prepared source, mapping or candidate changed after freezing")
    root = Path(directory)
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"refusing to overwrite prepared rewrite: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    inlined = request_to_dict(request)
    on_disk = {
        "schema_version": 1, "kind": REQUEST_KIND,
        **{key: value for key, value in inlined.items()
           if key not in ("source", "replacement")},
        "source": "source.json", "replacement": "replacement.json",
    }
    payload = {
        "source.json": request.source.to_dict(),
        "replacement.json": request.replacement.to_dict(),
        "request.json": on_disk,
    }
    record = {
        **prepared.to_dict(),
        "files": {},
        "input_file_sha256": dict(file_sha256 or {}),
        "provenance_status": "historical inputs, not authenticated by a proof replay",
        "proof_command": "symq rewrite request.json --report proof.json",
        "proof_status": "unproved",
    }
    contents: dict[str, bytes] = {}
    for name, document in payload.items():
        file_bytes = encode_json(document).encode("ascii")
        if len(file_bytes) > MAX_INPUT_BYTES:
            raise ValueError(
                f"prepared {name} exceeds the proof CLI {MAX_INPUT_BYTES}-byte input limit; "
                "split the circuit or use a direct checker on a smaller block"
            )
        record["files"][name] = hashlib.sha256(file_bytes).hexdigest()
        contents[name] = file_bytes
    contents["preparation.json"] = encode_json(record).encode("ascii")
    _publish_exclusive(root, contents)
    return record


# The proof entry point is created only after the inputs it names are complete;
# the advisory record that lists their hashes comes last.
PUBLICATION_ORDER = ("source.json", "replacement.json", "request.json", "preparation.json")


def _publish_exclusive(root: Path, contents: dict[str, bytes]) -> None:
    """No-replace publication: exclusive mkdir claim, exclusive file creation.

    ``os.rename`` is NOT used: on POSIX it silently replaces an empty directory
    created concurrently after an existence check. ``os.mkdir`` and
    ``open(..., 'xb')`` are the portable exclusive primitives.
    """
    if set(contents) != set(PUBLICATION_ORDER):
        raise ValueError(f"unexpected prepared files: {sorted(contents)}")
    try:
        os.mkdir(root)
    except FileExistsError:
        raise FileExistsError(f"refusing to overwrite prepared rewrite: {root}") from None
    created: list[Path] = []
    try:
        for name in PUBLICATION_ORDER:
            target = root / name
            with open(target, "xb") as handle:
                created.append(target)
                handle.write(contents[name])
                handle.flush()
                os.fsync(handle.fileno())
    except BaseException:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            root.rmdir()   # only if nothing foreign was added meanwhile
        except OSError:
            pass
        raise
