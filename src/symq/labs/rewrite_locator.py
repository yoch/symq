"""Conservative structural discovery of candidate substitution cuts and wire maps.

This is *not a proof*: it finds exact contiguous operation streams modulo
an injective local-to-global wire renaming. It never commutes/reorders gates,
guesses a missing wire, renames measurement records, assumes clean ancillas
or picks one of several matches. Only `symq rewrite` can certify a site.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from symq.circuit import Circuit
from symq.errors import ResourceLimitExceeded
from symq.experimental.hybrid import HybridProgram
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import FrozenHybridProgram, HybridFragment, hybrid_digest
from symq.labs.classical_transcript import Program, digest

__all__ = ["Location", "locate_exact"]


@dataclass(frozen=True)
class Location:
    span: tuple[int, int]
    wires: tuple[int | None, ...]
    unmapped_local_wires: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return not self.unmapped_local_wires

    def to_dict(self) -> dict[str, Any]:
        return {"span": list(self.span), "wires": list(self.wires),
                "unmapped_local_wires": list(self.unmapped_local_wires),
                "mapping_complete": self.complete}


def _compatible(left: Any, right: Any, *, coherent: bool) -> bool:
    if coherent:
        return (left.kind == right.kind and left.slot == right.slot
                and left.condition == right.condition and left.source == right.source
                and left.value == right.value
                and len(left.wires) == len(right.wires))
    return left.name == right.name and len(left.qubits) == len(right.qubits)


def _wires(op: Any, *, coherent: bool) -> tuple[int, ...]:
    return op.wires if coherent else op.qubits


def locate_exact(
    source: Circuit | HybridProgram,
    reference: Circuit | HybridFragment,
    *, max_candidates: int = 128, max_compares: int = 2_000_000,
) -> dict[str, Any]:
    """Find exact contiguous reference instances without interpreting their semantics.

    A complete unique mapping is offered only when EVERY local wire is used
    and exactly one structural match exists. Partial or repeated matches
    return non-actionable statuses. Explicit unmentioned wires and contracted
    assumptions remain the responsibility of the caller, not this locator.
    """
    coherent = type(source) is HybridProgram and type(reference) is HybridFragment
    classical = type(source) is Circuit and type(reference) is Circuit
    if not (coherent or classical):
        raise TypeError("classical Circuit/Circuit or coherent HybridProgram/HybridFragment required")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 1000:
        raise ValueError("max_candidates must be an integer in 1..1000")
    if type(max_compares) is not int or not 1 <= max_compares <= 10_000_000:
        raise ValueError("max_compares must be an integer in 1..10_000_000")
    source.validate()
    if classical:
        reference.validate()
    width, local_width = source.width, reference.width
    if local_width > width:
        raise ValueError("reference width exceeds the source width")
    operations = tuple(source.ops) if coherent else tuple(source.gates)
    pattern = tuple(reference.ops) if coherent else tuple(reference.gates)
    if not pattern:
        raise ValueError("empty reference has no identifiable insertion cut")
    if len(pattern) > len(operations):
        starts = range(0)
    else:
        starts = range(len(operations) - len(pattern) + 1)

    found: list[Location] = []
    compared = 0
    for start in starts:
        # Fast initial gate/signature screen; no speculative rewriting.
        if not _compatible(operations[start], pattern[0], coherent=coherent):
            continue
        if compared + len(pattern) > max_compares:
            # A search bound, not invalid input: the caller may narrow the source or raise it.
            raise ResourceLimitExceeded("structural comparisons", max_compares,
                                        compared + len(pattern))
        compared += len(pattern)
        forward: dict[int, int] = {}
        reverse: dict[int, int] = {}
        good = True
        for left, right in zip(operations[start:start + len(pattern)], pattern):
            if not _compatible(left, right, coherent=coherent):
                good = False
                break
            for local, global_ in zip(_wires(right, coherent=coherent),
                                       _wires(left, coherent=coherent)):
                if ((local in forward and forward[local] != global_)
                        or (global_ in reverse and reverse[global_] != local)):
                    good = False
                    break
                forward[local] = global_
                reverse[global_] = local
            if not good:
                break
        if not good:
            continue
        missing = tuple(q for q in range(local_width) if q not in forward)
        wires = tuple(forward.get(q) for q in range(local_width))
        found.append(Location((start, start + len(pattern)), wires, missing))
        if len(found) > max_candidates:
            raise ResourceLimitExceeded("structural cut matches", max_candidates, len(found))

    if not found:
        status = "not_found"
    elif len(found) > 1:
        status = "ambiguous"
    elif not found[0].complete:
        status = "unmapped_wires"
    else:
        status = "unique"
    source_sha = (hybrid_digest(FrozenHybridProgram.freeze(source)) if coherent
                  else digest(Program.freeze(source)))
    pattern_sha = canonical_sha256({
        "kind": "exact_cut_pattern_v1",
        "theorem": "coherent" if coherent else "classical",
        "width": local_width,
        "ops": [
            ({"kind": op.kind, "wires": list(op.wires), "slot": op.slot,
              "condition": op.condition, "source": op.source, "value": op.value}
             if coherent else [op.name, list(op.qubits)])
            for op in pattern
        ],
    })
    return {"schema_version": 1, "kind": "symq_rewrite_locations",
            "theorem": "coherent" if coherent else "classical",
            "status": status, "matches": [item.to_dict() for item in found],
            "source_sha256": source_sha, "reference_pattern_sha256": pattern_sha,
            "advisory_only": True,
            "reason": {
                "unique": "one complete exact structural location; proof and contracts still required",
                "ambiguous": "multiple exact matches: specify one span explicitly",
                "unmapped_wires": "some local wires are unused: supply their mapping explicitly",
                "not_found": "no contiguous exact match; no rewrite is inferred",
            }[status]}
