"""Bounded signed-monomial HMR substitution after explicit fresh-wire reset.

The theorem compares the candidate with the reference tensored with reset on a
new quantum wire, forgetting only a new private classical result. Every HMR
Kraus column is checked, including its sign; this is stronger than basis-value
agreement and extends by linearity to arbitrary coherent/entangled inputs.
"""
from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict, dataclass
from pathlib import Path

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.hybrid import HOp
from symq.experimental.serialization import parse_json
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite import ReceiptMismatch, call_budget
from symq.labs.rewrite_request import fragment_from_dict, fragment_to_dict
from symq.resources import Budget, VerificationSession

__all__ = ["CacheLimits", "cache_request", "prove_reset_cache", "replay_reset_cache"]
_KIND = "symq_reset_monomial_cache"
_REVERSIBLE = {"x", "cx", "ccx", "swap", "cswap", "z", "cz", "ccz", "neg", "store", "invert", "oxor"}


@dataclass(frozen=True)
class CacheLimits:
    max_data_wires: int = 12
    max_classical_inputs: int = 4
    max_ops: int = 4096
    max_column_steps: int = 20_000_000
    max_request_bytes: int = 2_000_000

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_data_wires > 12 or self.max_classical_inputs > 4:
            raise ValueError("hard caps: 12 data wires and 4 arbitrary classical inputs")


_LIMITS = CacheLimits()


def cache_request(reference: HybridFragment, pair: tuple[int, int], *, fresh_slot: str = "b0") -> dict:
    """Build a candidate, without treating its shape as proof of equivalence."""
    if type(reference) is not HybridFragment or type(pair) is not tuple or len(pair) != 2:
        raise ValueError("frozen reference and ordered operation pair required")
    a, b = pair
    if any(type(i) is not int for i in pair) or not 0 <= a < b < len(reference.ops):
        raise ValueError("ordered in-range operation pair required")
    first, second = reference.ops[a], reference.ops[b]
    if any(op.kind != "ccx" or op.condition is not None for op in (first, second)):
        raise UnsupportedOperation("cache pair requires unconditional CCX")
    s = reference.width
    ops = [HOp("reset", (s,))]
    for i, op in enumerate(reference.ops):
        if i == a:
            ops += [HOp("ccx", (*op.wires[:2], s)), HOp("cx", (s, op.wires[2]))]
        elif i == b:
            ops += [HOp("cx", (s, op.wires[2])), HOp("hmr", (s,), slot=fresh_slot),
                    HOp("cz", op.wires[:2], condition=fresh_slot)]
        else:
            ops.append(op)
    candidate = HybridFragment(s + 1, tuple(ops), reference.classical_inputs)
    return {"kind": _KIND, "schema_version": 1, "reference": fragment_to_dict(reference),
            "candidate": fragment_to_dict(candidate), "fresh_slot": fresh_slot}


def _names(fragment):
    names = set(fragment.classical_inputs)
    for op in fragment.ops:
        names.update(x for x in (op.slot, op.source, op.condition.removeprefix("!") if op.condition else None) if x)
    return names


def _columns(ops, initial, memory, outcome, guard):
    state, phase = initial, 0
    memory = dict(memory)
    for at, op in enumerate(ops):
        if at % 64 == 0:
            guard.check_time()
        condition = op.condition
        enabled = condition is None or bool(memory[condition.removeprefix("!")]) != condition.startswith("!")
        if not enabled:
            continue
        k, q = op.kind, op.wires
        if k in {"x", "cx", "ccx"}:
            if all(state >> c & 1 for c in q[:-1]):
                state ^= 1 << q[-1]
        elif k in {"swap", "cswap"}:
            a, b = q[-2:]
            if (k == "swap" or state >> q[0] & 1) and (state >> a ^ state >> b) & 1:
                state ^= (1 << a) | (1 << b)
        elif k in {"z", "cz", "ccz", "neg"}:
            phase ^= int(all(state >> c & 1 for c in q))
        elif k == "reset":
            # Only the first fresh-wire reset is admitted. Its Kraus projectors
            # are factored out, rather than pretending reset is a permutation.
            state &= ~(1 << q[0])
        elif k == "hmr":
            phase ^= outcome & (state >> q[0] & 1)
            state &= ~(1 << q[0])
            memory[op.slot] = outcome
        elif k == "store":
            memory[op.slot] = op.value
        elif k == "invert":
            memory[op.slot] ^= 1
        else:  # validated oxor
            memory[op.slot] ^= memory[op.source]
    return state, phase, memory


def _dependencies(guard):
    import symq.errors
    import symq.experimental.hybrid
    import symq.experimental.serialization
    import symq.hashing
    import symq.labs.channel_composition
    import symq.labs.kmb_resource_frontier
    import symq.labs.rewrite
    import symq.labs.rewrite_request
    import symq.resources

    files = {"analyzer": Path(__file__)}
    for module in (symq.experimental.hybrid, symq.experimental.serialization, symq.errors, symq.hashing,
                   symq.labs.channel_composition, symq.labs.kmb_resource_frontier,
                   symq.labs.rewrite, symq.labs.rewrite_request, symq.resources):
        files[module.__name__] = Path(module.__file__)
    values = {}
    for name, path in files.items():
        guard.check_time()
        values[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"python": platform.python_version(), "source_sha256": values}


def prove_reset_cache(request, *, expected_request_sha256: str, limits: CacheLimits = _LIMITS,
                      budget: Budget | None = None) -> dict:
    """Check exact signed columns of both candidate HMR branches; no site authority."""
    budget = call_budget(budget)
    result = {"kind": _KIND, "schema_version": 1, "request_sha256": expected_request_sha256,
              "outcome": "inconclusive", "global_substitution_authorized": False}
    try:
        with VerificationSession(budget) as guard:
            if type(limits) is not CacheLimits:
                raise TypeError("CacheLimits required")
            limits.__post_init__()
            if any(getattr(guard.budget, k) is not None for k in ("max_nodes", "max_terms", "max_bytes")):
                raise ValueError("use column-step limits and shared time budget")
            if type(request) is bytes:
                if len(request) > limits.max_request_bytes:
                    raise ResourceLimitExceeded("request bytes", limits.max_request_bytes, len(request))
                request = parse_json(request)
            raw = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            if len(raw) > limits.max_request_bytes:
                raise ResourceLimitExceeded("request bytes", limits.max_request_bytes, len(raw))
            document = parse_json(raw)
            if (type(document) is not dict or set(document) != {"kind", "schema_version", "reference", "candidate", "fresh_slot"}
                    or document["kind"] != _KIND or type(document["schema_version"]) is not int
                    or document["schema_version"] != 1):
                raise ValueError("closed version-1 reset-cache request required")
            if canonical_sha256(document) != expected_request_sha256:
                raise ReceiptMismatch("cache request differs from independent pin")
            reference, candidate = (fragment_from_dict(document[k]) for k in ("reference", "candidate"))
            n, m = reference.width, document["fresh_slot"]
            if n > limits.max_data_wires or len(reference.classical_inputs) > limits.max_classical_inputs:
                raise UnsupportedOperation("cache data/classical input width exceeds explicit caps")
            if candidate.width != n + 1 or candidate.classical_inputs != reference.classical_inputs:
                raise ValueError("candidate must add exactly one fresh wire and keep the classical input domain")
            if type(m) is not str or m in _names(reference):
                raise ValueError("new HMR slot must be absent from the reference interface")
            if _names(candidate) != _names(reference) | {m}:
                raise ValueError("candidate classical interface must add only the private HMR slot")
            if not candidate.ops or candidate.ops[0] != HOp("reset", (n,)):
                raise UnsupportedOperation("first operation must explicitly reset the new wire")
            if (any(op.kind not in _REVERSIBLE for op in reference.ops)
                    or any(op.kind not in _REVERSIBLE | {"hmr"} for op in candidate.ops[1:])):
                raise UnsupportedOperation("local reference must be signed monomial; only the fresh reset/HMR are admitted")
            events = [(i, op) for i, op in enumerate(candidate.ops) if op.kind == "hmr"]
            writes = [(i, op) for i, op in enumerate(candidate.ops) if op.slot == m]
            if (len(events) != 1 or events[0][1] != HOp("hmr", (n,), slot=m)
                    or writes != events):
                raise UnsupportedOperation("exactly one unconditional fresh HMR definition, without slot reuse, required")
            if len(reference.ops) > limits.max_ops or len(candidate.ops) > limits.max_ops:
                raise ResourceLimitExceeded("local operations", limits.max_ops, max(len(reference.ops), len(candidate.ops)))
            count = 1 << (n + len(reference.classical_inputs))
            steps = count * (len(reference.ops) + 2 * len(candidate.ops))
            if steps > limits.max_column_steps:
                raise ResourceLimitExceeded("Kraus column steps", limits.max_column_steps, steps)
            reference_names = sorted(_names(reference))
            checked = 0
            for classical in range(1 << len(reference.classical_inputs)):
                memory = {s: classical >> i & 1 for i, s in enumerate(reference.classical_inputs)}
                for state in range(1 << n):
                    guard.check_time()
                    a, p, expected_memory = _columns(reference.ops, state, memory, 0, guard)
                    for outcome in (0, 1):
                        b, sign, actual_memory = _columns(candidate.ops, state, memory, outcome, guard)
                        checked += 1
                        if (a != b or p != sign
                                or any(expected_memory[s] != actual_memory[s] for s in reference_names)):
                            result.update(outcome="inequivalent", witness={"scope": "local_column_only",
                                          "input_basis": state, "classical_input": memory,
                                          "hmr_outcome": outcome, "expected": [a, p], "actual": [b, sign]})
                            return result
            dependencies = _dependencies(guard)
            guard.check_time()
            result.update(outcome="equivalent", theorem="reference_tensor_fresh_reset_channel_with_new_measurement_forgotten",
                          initial_domain="arbitrary coherent data, arbitrary external frame and declared classical input values",
                          initial_domain_nonempty=True, fresh_wire=n, fresh_slot=m,
                          clean_entry="proved_by_explicit_reset", clean_return="proved_pure_zero_by_all_signed_columns",
                          measurement_definition_op=events[0][0], measurement_version=1,
                          checked_kraus_columns=checked, column_steps_bound=steps,
                          branch_identity="for each classical input, each quantum HMR Kraus operator equals the reference monomial operator / sqrt(2) after fresh reset",
                          classical_input_semantics="classical valuations may be correlated with quantum data/frame; coherent classical inputs are not modeled",
                          original_classical_outputs="all retained", fresh_classical_result="forgotten",
                          request=document, dependencies=dependencies, limits=asdict(limits))
            return result
    except (ResourceLimitExceeded, UnsupportedOperation) as error:
        return {"kind": _KIND, "schema_version": 1, "request_sha256": expected_request_sha256,
                "outcome": "unsupported" if isinstance(error, UnsupportedOperation) else "inconclusive",
                "reason": str(error), "global_substitution_authorized": False}


def replay_reset_cache(request, receipt, *, expected_request_sha256: str,
                       limits: CacheLimits = _LIMITS, budget: Budget | None = None) -> dict:
    from symq.labs.kmb_resource_frontier import _same

    try:
        with VerificationSession(call_budget(budget)) as guard:
            fresh = prove_reset_cache(request, expected_request_sha256=expected_request_sha256,
                                      limits=limits, budget=guard.remaining_budget())
            if fresh["outcome"] == "equivalent" and not _same(receipt, fresh, guard):
                raise ReceiptMismatch("cache receipt differs from full fresh proof")
            guard.check_time()
            return fresh
    except ResourceLimitExceeded as error:
        return {"kind": _KIND, "schema_version": 1, "outcome": "inconclusive", "reason": str(error),
                "global_substitution_authorized": False}
