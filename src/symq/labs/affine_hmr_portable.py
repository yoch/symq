"""Portable, solver-free proof pilot for a STRICT affine HMR channel fragment.

All inputs and claims are closed JSON. The standalone checker imports only
the Python standard library, reconstructs the exact affine Boolean state
and quadratic sign phase, and accepts ONLY if every Kraus branch is a
scalar multiple of one supplied phase-free reversible reference isometry
on the explicit affine coherent input span.

This is a restricted source-level symbolic checker, NOT an LRAT checker,
a Lean-verified runtime, or a general HMR/table-loader certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any

_KIND = "symq_affine_hmr_proof"
_THEOREM = "full_output_channel_on_affine_data_span"
_SLOT = re.compile(r"b(0|[1-9][0-9]*)\Z")
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_ARITY = {"x": 1, "cx": 2, "ccx": 3, "swap": 2,
          "z": 1, "cz": 2, "ccz": 3, "neg": 0, "hmr": 1}
_STATES = {"x", "cx", "ccx", "mcx", "swap"}
_SIGNS = {"z", "cz", "ccz", "neg"}
_CLASSICAL = {"store", "invert", "oxor"}
_PROOF_KEYS = frozenset({
    "kind", "schema_version", "theorem", "source", "reference", "support",
    "source_sha256", "reference_sha256", "support_sha256", "claim",
})


class _Unsupported(Exception):
    pass


class _Limit(Exception):
    pass


def _object(value: Any, keys: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name}: expected exactly {sorted(keys)}")
    return value


def _integer(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name}: expected plain integer in [{low}, {high}]")
    return value


def _slot(value: Any) -> str:
    if type(value) is not str or _SLOT.fullmatch(value) is None:
        raise ValueError("canonical classical slot bN required")
    return value


def _condition(value: Any, memory: dict[str, int]) -> int:
    if value is None:
        return 1
    if type(value) is not str:
        raise ValueError("condition must be a classical slot")
    key = value.removeprefix("!")
    _slot(key)
    if key not in memory:
        raise ValueError("condition read before write")
    return memory[key] ^ (1 if value.startswith("!") else 0)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def digest(value: Any) -> str:
    """Canonical source identity; it is NOT authenticated without an external pin."""
    return hashlib.sha256(_canonical(value)).hexdigest()


def _terms(form: int) -> set[int]:
    out: set[int] = set()
    for bit in range(form.bit_length()):
        if (form >> bit) & 1:
            out.add(0 if bit == 0 else 1 << (bit - 1))
    return out


def _linearize(polynomial: set[int]) -> int:
    if any(term.bit_count() > 1 for term in polynomial):
        raise _Unsupported("non-affine quantum state under this legal input support")
    result = 0
    for term in polynomial:
        result ^= 1 if term == 0 else 1 << term.bit_length()
    return result


class _Clock:
    def __init__(self, max_seconds: float, max_terms: int):
        if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
                or max_seconds <= 0):
            raise ValueError("positive finite max_seconds required")
        _integer(max_terms, 1, 10_000_000, "max_terms")
        self.deadline = time.perf_counter() + max_seconds
        self.max_terms = max_terms

    def check(self) -> None:
        if time.perf_counter() >= self.deadline:
            raise _Limit("whole-call deadline expired")

    def product(self, forms: list[int]) -> set[int]:
        poly = {0}
        for form in forms:
            self.check()
            terms = _terms(form)
            nxt: set[int] = set()
            for index, a in enumerate(poly):
                if index % 1024 == 0:
                    self.check()
                for b in terms:
                    t = a | b
                    if t in nxt:
                        nxt.remove(t)
                    else:
                        nxt.add(t)
                    if len(nxt) > self.max_terms:
                        raise _Limit("polynomial term cap")
            poly = nxt
        if any(t.bit_count() > 2 for t in poly):
            raise _Unsupported("product has degree >2 outside the admitted certificate grammar")
        return poly


def _xor(phase: set[int], terms: set[int], clock: _Clock) -> None:
    phase.symmetric_difference_update(terms)
    if len(phase) > clock.max_terms:
        raise _Limit("retained phase term cap")
    clock.check()


def _support(value: Any, data: int) -> tuple[int, list[int]]:
    doc = _object(value, {"kind", "offset", "columns"}, "support")
    if doc["kind"] != "affine_data_span" or type(doc["columns"]) is not list:
        raise ValueError("support requires affine_data_span and explicit columns")
    offset = _integer(doc["offset"], 0, (1 << data) - 1, "offset")
    if len(doc["columns"]) > data:
        raise ValueError("rank cannot exceed data width")
    basis: dict[int, int] = {}
    columns = []
    for entry in doc["columns"]:
        v = _integer(entry, 1, (1 << data) - 1, "column")
        x = v
        while x:
            lead = x.bit_length() - 1
            if lead not in basis:
                basis[lead] = x
                break
            x ^= basis[lead]
        if not x:
            raise ValueError("dependent columns: support coordinates must be injective")
        columns.append(v)
    return offset, columns


def _reference(doc: Any, width: int, state: list[int], clock: _Clock) -> None:
    v = _object(doc, {"kind", "width", "gates"}, "reference")
    if (v["kind"] != "classical_reversible" or type(v["width"]) is not int
            or v["width"] != width):
        raise ValueError("phase-free reference width/grammar mismatch")
    if type(v["gates"]) is not list or len(v["gates"]) > 100_000:
        raise ValueError("reference gate cap")
    for item in v["gates"]:
        clock.check()
        if (type(item) is not list or len(item) != 2 or type(item[0]) is not str
                or type(item[1]) is not list):
            raise ValueError("reference gate grammar")
        kind, wires = item
        if kind not in {"x", "cx", "ccx", "mcx"}:
            raise _Unsupported("reference must be X/CX/CCX/MCX and affine on support")
        min_len = {"x": 1, "cx": 2, "ccx": 3, "mcx": 2}[kind]
        if ((kind != "mcx" and len(wires) != min_len)
                or (kind == "mcx" and len(wires) < min_len)):
            raise ValueError("reference arity")
        if any(type(q) is not int or q < 0 or q >= width for q in wires):
            raise ValueError("reference wire")
        if len(set(wires)) != len(wires):
            raise ValueError("repeated reference wire")
        *controls, target = wires
        state[target] ^= _linearize(clock.product([state[q] for q in controls]))


def _source(doc: Any, state: list[int], rank: int, clock: _Clock,
            max_events: int, max_ops: int) -> tuple[set[int], int]:
    v = _object(doc, {"schema_version", "kind", "data", "ancillas", "ops"}, "source")
    if (type(v["schema_version"]) is not int or v["schema_version"] != 1
            or v["kind"] != "hybrid"):
        raise ValueError("expected hybrid source schema v1")
    width = len(state)
    if (type(v["data"]) is not int or type(v["ancillas"]) is not int
            or v["data"] < 1 or v["ancillas"] < 0
            or v["data"] + v["ancillas"] != width):
        raise ValueError("invalid source quantum width")
    if type(v["ops"]) is not list:
        raise ValueError("source ops must be a list")
    if len(v["ops"]) > max_ops:
        raise _Limit("source operation cap")
    memory: dict[str, int] = {}
    phase: set[int] = set()
    events = 0
    for op in v["ops"]:
        clock.check()
        _object(op, {"kind", "wires", "slot", "condition", "source", "value"}, "HOp")
        kind = op["kind"]
        if type(kind) is not str or kind not in _STATES | _SIGNS | {"hmr"} | _CLASSICAL:
            raise _Unsupported("unsupported hybrid operation")
        wires = op["wires"]
        if type(wires) is not list or any(type(q) is not int or
                                         q < 0 or q >= width for q in wires):
            raise ValueError("invalid HOp wires")
        if len(set(wires)) != len(wires):
            raise ValueError("repeated quantum wire")
        if kind in _ARITY and len(wires) != _ARITY[kind]:
            raise ValueError("HOp arity")
        if kind == "mcx" and len(wires) < 2:
            raise ValueError("MCX requires controls and target")
        condition = op["condition"]
        slot = op["slot"]
        if kind in _STATES | _SIGNS | {"hmr"}:
            if op["source"] is not None or op["value"] is not None:
                raise ValueError("unexpected quantum metadata")
            if kind == "hmr":
                if condition is not None:
                    raise ValueError("guarded HMR is forbidden")
                name = _slot(slot)
                if events >= max_events:
                    raise _Limit("HMR event cap")
                measure = 1 << (rank + events + 1)
                events += 1
                _xor(phase, clock.product([measure, state[wires[0]]]), clock)
                state[wires[0]] = 0
                memory[name] = measure
                continue
            if slot is not None:
                raise ValueError("unexpected quantum output slot")
            cond = _condition(condition, memory)
            if kind in {"x", "cx", "ccx", "mcx"}:
                *controls, target = wires
                state[target] ^= _linearize(
                    clock.product([cond, *[state[q] for q in controls]])
                )
            elif kind == "swap":
                if condition is not None:
                    raise _Unsupported("conditioned SWAP is not in the affine grammar")
                a, b = wires
                state[a], state[b] = state[b], state[a]
            else:
                _xor(phase, clock.product(
                    [cond, *[state[q] for q in wires]]
                ), clock)
            continue
        if wires:
            raise ValueError("classical operation must not address quantum wires")
        if kind == "store":
            if condition is not None or op["source"] is not None:
                raise ValueError("store has no guard/source")
            name = _slot(slot)
            memory[name] = _integer(op["value"], 0, 1, "stored bit")
        elif kind == "invert":
            name = _slot(slot)
            if op["source"] is not None or op["value"] is not None or name not in memory:
                raise ValueError("uninitialized/invalid invert")
            memory[name] ^= _condition(condition, memory)
        else:
            name, source = _slot(slot), _slot(op["source"])
            if (condition is not None or op["value"] is not None
                    or name not in memory or source not in memory):
                raise ValueError("uninitialized/invalid classical XOR")
            memory[name] ^= memory[source]
    clock.check()
    return phase, events


def _analyse(source: dict, reference: dict, support: dict, *,
             max_seconds: float, max_terms: int, max_events: int,
             max_width: int, max_ops: int) -> dict:
    _integer(max_events, 1, 2048, "max_events")
    _integer(max_width, 1, 4096, "max_width")
    _integer(max_ops, 1, 10_000_000, "max_ops")
    clock = _Clock(max_seconds, max_terms)
    if type(source) is not dict:
        raise ValueError("source must be an object")
    data = _integer(source.get("data"), 1, max_width, "data")
    anc = _integer(source.get("ancillas"), 0, max_width - data, "ancillas")
    width = data + anc
    offset, columns = _support(support, data)
    rank = len(columns)
    initial = [
        ((offset >> q) & 1)
        ^ sum(1 << (j + 1) for j, col in enumerate(columns) if col >> q & 1)
        for q in range(data)
    ] + [0] * anc
    actual = initial.copy()
    ideal = initial.copy()
    _reference(reference, width, ideal, clock)
    phase, events = _source(source, actual, rank, clock, max_events, max_ops)
    for wire, (left, right) in enumerate(zip(actual, ideal)):
        if left != right:
            return {"status": "not_proved", "obligation": "quantum_output",
                    "wire": wire}
    input_mask = (1 << rank) - 1
    if any(term & input_mask for term in phase):
        return {"status": "not_proved", "obligation": "input_dependent_branch_phase"}
    clock.check()
    return {"status": "proved", "theorem": _THEOREM, "rank": rank,
            "events": events, "output_forms": actual,
            "branch_phase_terms": sorted(phase)}


def export_affine_hmr_certificate(
    source: dict, reference: dict, support: dict, *,
    max_seconds: float = 10.0, max_terms: int = 100_000,
    max_events: int = 256, max_width: int = 128, max_ops: int = 100_000,
    max_bundle_bytes: int = 8_000_000,
) -> dict:
    """Produce an UNTRUSTED self-contained solver-free algebraic certificate."""
    try:
        _integer(max_bundle_bytes, 1, 100_000_000, "max_bundle_bytes")
        statement = _analyse(source, reference, support, max_seconds=max_seconds,
                             max_terms=max_terms, max_events=max_events,
                             max_width=max_width, max_ops=max_ops)
        if statement["status"] != "proved":
            return statement
        bundle = {
            "kind": _KIND, "schema_version": 1, "theorem": _THEOREM,
            "source": source, "reference": reference, "support": support,
            "source_sha256": digest(source),
            "reference_sha256": digest(reference),
            "support_sha256": digest(support), "claim": statement,
        }
        if len(_canonical(bundle)) > max_bundle_bytes:
            raise _Limit("portable bundle byte cap")
        return {"status": "exported", "bundle": bundle}
    except _Unsupported as error:
        return {"status": "unsupported", "reason": str(error)}
    except _Limit as error:
        return {"status": "inconclusive", "reason": str(error)}
    except (TypeError, ValueError, OverflowError) as error:
        return {"status": "invalid", "reason": str(error)}


def check_affine_hmr_certificate(
    bundle: dict, *, expected_source_sha256: str,
    expected_reference_sha256: str, expected_support_sha256: str,
    max_seconds: float = 10.0, max_terms: int = 100_000,
    max_events: int = 256, max_width: int = 128, max_ops: int = 100_000,
    max_bundle_bytes: int = 8_000_000,
) -> dict:
    """Verify raw source semantics again without SAT or the original producer.

    A hash carried in the bundle is not proof of its source identity. All three
    expected hashes MUST be independently obtained from the trusted caller.
    """
    try:
        for pin in (expected_source_sha256, expected_reference_sha256,
                    expected_support_sha256):
            if type(pin) is not str or _PIN.fullmatch(pin) is None:
                raise ValueError("independent lowercase SHA-256 pins required")
        if type(bundle) is not dict or set(bundle) != _PROOF_KEYS:
            raise ValueError("invalid closed proof bundle")
        if (bundle["kind"] != _KIND
                or type(bundle["schema_version"]) is not int
                or bundle["schema_version"] != 1 or bundle["theorem"] != _THEOREM):
            raise ValueError("wrong theorem or schema")
        _integer(max_bundle_bytes, 1, 100_000_000, "max_bundle_bytes")
        if len(_canonical(bundle)) > max_bundle_bytes:
            raise _Limit("proof bundle byte cap")
        for key, expected in (("source", expected_source_sha256),
                              ("reference", expected_reference_sha256),
                              ("support", expected_support_sha256)):
            actual = digest(bundle[key])
            if actual != expected or bundle[key + "_sha256"] != actual:
                raise ValueError(f"stale or untrusted {key} identity")
        statement = _analyse(bundle["source"], bundle["reference"], bundle["support"],
                             max_seconds=max_seconds, max_terms=max_terms,
                             max_events=max_events, max_width=max_width, max_ops=max_ops)
        if (statement["status"] != "proved"
                or _canonical(statement) != _canonical(bundle["claim"])):
            raise ValueError("the certificate contradicts a fresh source check")
        return {"status": "verified", "verified_channel": True, "theorem": _THEOREM,
                "rank": statement["rank"], "events": statement["events"]}
    except _Unsupported as error:
        return {"status": "unsupported", "verified_channel": False, "reason": str(error)}
    except _Limit as error:
        return {"status": "inconclusive", "verified_channel": False, "reason": str(error)}
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return {"status": "invalid", "verified_channel": False, "reason": str(error)}


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--source-pin", required=True)
    parser.add_argument("--reference-pin", required=True)
    parser.add_argument("--support-pin", required=True)
    args = parser.parse_args()
    try:
        with args.bundle.open("rb") as stream:
            data = stream.read(8_000_001)
        if len(data) > 8_000_000:
            raise ValueError("bundle file exceeds byte cap")
        bundle = json.loads(data, object_pairs_hook=_unique_pairs,
                            parse_constant=_reject_constant)
        result = check_affine_hmr_certificate(
            bundle, expected_source_sha256=args.source_pin,
            expected_reference_sha256=args.reference_pin,
            expected_support_sha256=args.support_pin,
        )
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        result = {"status": "invalid", "verified_channel": False, "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
