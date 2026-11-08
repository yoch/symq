"""Source-bound sufficient affine reclamation facts for existing KMB wires.

Only computational support is interpreted: phases are retained by the source,
but cannot turn these facts into a channel-equivalence proof. A proved graph
q = c XOR parity(parents) permits unsigned affine uncompute, use while clean,
and restoration, including correlations. No missing input is assumed zero.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.serialization import parse_json
from symq.hashing import canonical_sha256
from symq.labs import kmb_reset_cache as records
from symq.labs import kmb_resource_frontier as frontier
from symq.labs import kmb_window as binary
from symq.labs.rewrite import ReceiptMismatch, call_budget
from symq.resources import Budget, VerificationSession

__all__ = ["AffineResourceLimits", "assess_affine_kmb_resources", "replay_affine_kmb_resources"]
_KIND = "symq_kmb_affine_resources"
_DOMAIN = "all_source_quantum_states_and_classical_values"
_ZERO, _ONE = frozenset(), frozenset({0})


@dataclass(frozen=True)
class AffineResourceLimits:
    max_analysis_ops: int = 250_000
    max_reservation_ops: int = 4096
    max_global_wires: int = 4096
    max_resources: int = 32
    max_parents: int = 32
    max_atoms: int = 100_000
    max_value_terms: int = 8192
    max_retained_terms: int = 2_000_000

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


_LIMITS = AffineResourceLimits()


class _Support:
    """Exact expressions with incomplete, sound Boolean identity simplification."""

    def __init__(self, width, guard, limits):
        self.guard, self.limits = guard, limits
        self.atoms, self.retained, self.peak = 0, 0, 0
        self.products, self.memory = {}, {}
        self.values = [self.variable() for _ in range(width)]

    def check(self, name, value, maximum):
        self.guard.check_time()
        if value > maximum:
            raise ResourceLimitExceeded(name, maximum, value)

    def variable(self):
        self.atoms += 1
        self.check("support atoms", self.atoms, self.limits.max_atoms)
        return frozenset({self.atoms})

    def bit(self, slot):
        if slot not in self.memory:
            self.memory[slot] = self.variable()
        return self.memory[slot]

    def xor(self, a, b):
        # Bound the temporary union before allocating a potentially large set.
        self.check("support XOR operands", len(a) + len(b), 2 * self.limits.max_value_terms)
        value = a ^ b
        self.check("support value terms", len(value), self.limits.max_value_terms)
        self.peak = max(self.peak, len(value))
        return value

    def mul(self, a, b):
        self.guard.check_time()
        if not a or not b:
            return _ZERO
        if a == _ONE or a == b:
            return b
        if b == _ONE:
            return a
        if self.xor(a, b) == _ONE:
            return _ZERO
        key = frozenset((a, b))
        if key not in self.products:
            self.retained += len(a) + len(b)
            self.check("retained support terms", self.retained, self.limits.max_retained_terms)
            self.products[key] = next(iter(self.variable()))
        return frozenset({self.products[key]})

    def step(self, code, qs, slot, condition):
        self.guard.check_time()
        base = code & 127
        if base in (0, 6, 16, 32, 48):
            return  # Signs do not enlarge computational support.
        p = _ONE if condition is None else self.bit(condition)
        if base in (17, 33, 49):
            delta = p
            for q in qs[:-1]:
                delta = self.mul(delta, self.values[q])
            self.values[qs[-1]] = self.xor(self.values[qs[-1]], delta)
        elif base in (34, 50):
            a, b = qs[-2:]
            delta = self.mul(p, self.xor(self.values[a], self.values[b]))
            if base == 50:
                delta = self.mul(delta, self.values[qs[0]])
            self.values[a] = self.xor(self.values[a], delta)
            self.values[b] = self.xor(self.values[b], delta)
        elif base in (18, 80):
            self.values[qs[0]] = self.mul(self.xor(_ONE, p), self.values[qs[0]])
            if base == 80:
                outcome = self.variable()
                self.memory[slot] = (outcome if p == _ONE else
                    self.xor(self.bit(slot), self.mul(p, self.xor(self.bit(slot), outcome))))
        elif base in (64, 65):
            value = _ONE if base & 1 else _ZERO
            self.memory[slot] = (value if p == _ONE else
                self.xor(self.bit(slot), self.mul(p, self.xor(self.bit(slot), value))))
        elif base == 66:
            self.memory[slot] = self.xor(self.bit(slot), p)
        else:
            raise UnsupportedOperation("support window contains an unsupported instruction")


def _writes(code, qs):
    base = code & 127
    if base in (17, 18, 33, 49, 80):
        return qs[-1:]
    if base == 34:
        return qs
    if base == 50:
        return qs[1:]
    return ()


def _document(request, source_pin, request_pin, limits):
    raw = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 200_000:
        raise ResourceLimitExceeded("resource request bytes", 200_000, len(raw))
    doc = parse_json(raw)
    if (type(doc) is not dict or set(doc) != {"kind", "schema_version", "source_file_sha256",
            "analysis_window", "reservation_window", "domain", "resources"}
            or doc["kind"] != _KIND or type(doc["schema_version"]) is not int or doc["schema_version"] != 1):
        raise ValueError("closed version-1 affine resource request required")
    if canonical_sha256(doc) != request_pin or doc["source_file_sha256"] != source_pin:
        raise ReceiptMismatch("affine resource request differs from independent pins")
    if doc["domain"] != _DOMAIN:
        raise UnsupportedOperation("only the complete arbitrary source input domain is supported")
    for key, cap in (("analysis_window", limits.max_analysis_ops),
                     ("reservation_window", limits.max_reservation_ops)):
        span = doc[key]
        if (type(span) is not list or len(span) != 2 or any(type(i) is not int for i in span)
                or not 0 <= span[0] < span[1]):
            raise ValueError("ordered nonempty raw source spans required")
        if span[1] - span[0] > cap:
            raise ResourceLimitExceeded(key, cap, span[1] - span[0])
    if doc["analysis_window"][1] != doc["reservation_window"][0]:
        raise ValueError("analysis must end at the actual reservation cut")
    resources = doc["resources"]
    if type(resources) is not list or not 1 <= len(resources) <= limits.max_resources:
        raise ValueError("bounded nonempty resource list required")
    seen = set()
    for item in resources:
        if (type(item) is not dict or set(item) != {"wire", "parents", "constant"}
                or type(item["wire"]) is not int or item["wire"] < 0 or item["wire"] in seen
                or type(item["constant"]) is not int or item["constant"] not in (0, 1)
                or type(item["parents"]) is not list or len(item["parents"]) > limits.max_parents
                or any(type(q) is not int or q < 0 for q in item["parents"])
                or len(set(item["parents"])) != len(item["parents"])
                or item["wire"] in item["parents"]):
            raise ValueError("distinct wire, injective parents and Boolean constant required")
        seen.add(item["wire"])
    return doc


def assess_affine_kmb_resources(path, request, *, expected_source_sha256, expected_request_sha256,
                                limits=_LIMITS, budget: Budget | None = None):
    """Prove sufficient reclamation obligations; never apply a substitution."""
    empty = {"kind": _KIND, "schema_version": 1, "source_file_sha256": expected_source_sha256,
             "request_sha256": expected_request_sha256, "facts": [], "usable_resources": [],
             "candidate_authorized": False, "global_substitution_proved": False}
    try:
        if type(limits) is not AffineResourceLimits:
            raise TypeError("AffineResourceLimits required")
        limits.__post_init__()
        with VerificationSession(call_budget(budget)) as guard:
            if any(getattr(guard.budget, key) is not None for key in ("max_nodes", "max_terms", "max_bytes")):
                raise ValueError("use explicit affine support limits and a shared time budget")
            binary._pin(expected_source_sha256)
            binary._pin(expected_request_sha256)
            doc = _document(request, expected_source_sha256, expected_request_sha256, limits)
            import numpy as np

            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                status = os.fstat(stream.fileno())
                if not stat.S_ISREG(status.st_mode) or not 104 <= status.st_size <= 2 * 1024**3:
                    raise UnsupportedOperation("complete regular KMB source of at most 2 GiB required")
                deadline = guard.deadline if guard.deadline is not None else float("inf")
                with binary._private_snapshot(stream, status.st_size, deadline=deadline,
                        max_seconds=guard.remaining_seconds() or 30) as (view, pin):
                    if pin != expected_source_sha256:
                        raise ReceiptMismatch("whole source differs from independent pin")
                    info, packets = binary._layout(view, max_registers=100_000, max_register_entries=5_000_000,
                        max_ops=100_000_000, max_seconds_deadline=deadline)
                    if info["num_qubits"] > limits.max_global_wires:
                        raise ResourceLimitExceeded("global support wires", limits.max_global_wires, info["num_qubits"])
                    observed = sorted({q for item in doc["resources"] for q in [item["wire"], *item["parents"]]})
                    if any(q >= info["num_qubits"] for q in observed):
                        raise ValueError("resource mapping outside complete source width")
                    reservation = {"cut_op": doc["reservation_window"][0],
                        "lease_stop_op": doc["reservation_window"][1], "wires": observed, "initial_constants": []}
                    scan, work = frontier._scan(np, view, info, packets, reservation, guard, frontier.FrontierLimits())
                    analysis, _ = records._extract(np, view, info, packets, *doc["analysis_window"], guard)
                    body, _ = records._extract(np, view, info, packets, *doc["reservation_window"], guard)
                    support = _Support(info["num_qubits"], guard, limits)
                    for op in analysis:
                        support.step(*op)
                    touched = {q for _, qs, _, _ in body for q in qs}
                    written = {q for code, qs, _, _ in body for q in _writes(code, qs)}
                    facts = []
                    for item in doc["resources"]:
                        q, parents = item["wire"], item["parents"]
                        difference = support.values[q]
                        if item["constant"]:
                            difference = support.xor(difference, _ONE)
                        for parent in parents:
                            difference = support.xor(difference, support.values[parent])
                        relation = not difference
                        reserved = q not in touched
                        stable = not (set(parents) & written)
                        usable = relation and reserved and stable
                        preparation = ([["x", q]] if item["constant"] else [])
                        preparation += [["cx", p, q] for p in parents]
                        facts.append({"wire": q, "parents": parents, "constant": item["constant"],
                            "relation": "proved" if relation else "not_proved",
                            "initial_cleanliness": "proved_zero" if support.values[q] == _ZERO else
                                "proved_one" if support.values[q] == _ONE else "unknown",
                            "reservation": "proved_no_source_use" if reserved else "source_interference",
                            "parents_preserved": "proved_no_possible_write" if stable else "source_interference",
                            "clean_after_preparation": usable,
                            "borrowed_graph_and_correlations_restored_after_inverse_preparation": usable,
                            "preparation": preparation if usable else None,
                            "restoration": list(reversed(preparation)) if usable else None})
                    dependencies = frontier._dependencies(np, guard)
                    dependencies["affine_resource_analyzer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                    dependencies["record_extractor_sha256"] = hashlib.sha256(Path(records.__file__).read_bytes()).hexdigest()
                    guard.check_time()
                guard.check_time()
                return {**empty, "outcome": "proved" if any(f["clean_after_preparation"] for f in facts) else "not_proved",
                    "request": doc, "facts": facts,
                    "usable_resources": [f["wire"] for f in facts if f["clean_after_preparation"]],
                    "source_ops": info["num_ops"], "source_bytes": status.st_size,
                    "initial_domain_nonempty": True,
                    "analysis_boundary": "all quantum inputs and classical values arbitrary, including correlations; no prefix facts assumed",
                    "theorem": "computational support in an affine graph; unsigned affine uncompute and inverse restore that graph",
                    "phase_scope": "no phase equivalence inferred; a cache replacement still requires its own fresh signed/channel proof",
                    "restoration_condition": "the intervening replacement must preserve the proved parent values and return the lease wire to pure zero",
                    "independent_certificate": False, "dependencies": dependencies, "limits": asdict(limits), "work": work,
                    "support_work": {"atoms": support.atoms, "peak_value_terms": support.peak,
                        "retained_product_operand_terms": support.retained}, "source_reservation_facts": scan}
    except (ResourceLimitExceeded, UnsupportedOperation, ImportError) as error:
        return {**empty, "outcome": "inconclusive" if isinstance(error, ResourceLimitExceeded) else "unsupported",
                "reason": str(error)}


def replay_affine_kmb_resources(path, request, receipt, *, expected_source_sha256,
                                expected_request_sha256, limits=_LIMITS, budget=None):
    try:
        with VerificationSession(call_budget(budget)) as guard:
            fresh = assess_affine_kmb_resources(path, request, expected_source_sha256=expected_source_sha256,
                expected_request_sha256=expected_request_sha256, limits=limits, budget=guard.remaining_budget())
            if fresh["outcome"] in ("proved", "not_proved") and not frontier._same(receipt, fresh, guard):
                raise ReceiptMismatch("affine receipt differs from fresh source extraction and support proof")
            guard.check_time()
            return fresh
    except ResourceLimitExceeded as error:
        return {"kind": _KIND, "schema_version": 1, "outcome": "inconclusive", "reason": str(error),
                "facts": [], "usable_resources": [], "candidate_authorized": False, "global_substitution_proved": False}
