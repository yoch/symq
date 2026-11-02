"""Bounded exact check of a finite-table XOR oracle built with HMR uncomputation.

Research prototype for issue #144 (``symq.labs``, no API promise). The source is a
``symq.experimental.hybrid.HybridProgram``: reversible gates, sign phases, X-basis
measure-and-reset (HMR), Z measurement, reset and classically controlled gates. The
contract is the finite-table XOR isometry

    W |a, z, 0_s, d> = |a, z XOR T[a], 0_s, d>      (all quantum outputs retained)

on the span P of the legal basis inputs, with every classical record forgotten.

Criterion (``docs/guide/hmr-table-contract.md``): for every Kraus branch m of the
program (the outcomes of all measurement events in program order, plus the hidden
pre-reset bit of each ``reset``), ``K_m V`` restricted to P equals ``c_m W`` with
one scalar ``c_m`` for all of P. It is sufficient, and for this exact contract (all
quantum outputs retained, every record forgotten) it is also necessary, so a refusal
carries a coherence pair ``(x, y)`` of legal basis inputs on which the channels
provably differ. Every branch amplitude in this grammar is ``±2**(-H/2)`` or 0, with
``H`` the number of HMR events, so the check is exact integer sign arithmetic.

The check enumerates legal basis inputs and branches: it is exponential and capped.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Any

from symq.errors import InternalInconsistency, ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridProgram, freeze_hybrid
from symq.experimental.serialization import program_to_dict
from symq.hashing import canonical_sha256
from symq.resources import Budget, Guard

__all__ = [
    "HmrTableContract",
    "HmrTableResult",
    "and_uncompute_example",
    "check_hmr_table_xor",
]

_MAX_WIDTH = 64
_MAX_ADDRESS_BITS = 12
_MAX_TARGET_BITS = 12
_PERMUTATIONS = {"x", "cx", "ccx", "mcx", "swap", "cswap"}
_SIGNS = {"z", "cz", "ccz", "neg"}
_CLASSICAL = {"store", "invert", "oxor"}
_EVENTS = {"hmr", "measure_z", "reset"}


def _wires(value: Any, name: str) -> None:
    if type(value) is not tuple or any(type(v) is not int or v < 0 for v in value):
        raise ValueError(f"{name} must be a tuple of nonnegative plain integers")


def _ordered(value: Any, bound: int, name: str) -> None:
    _wires(value, name)
    if not value or any(v >= bound for v in value):
        raise ValueError(f"{name} must be nonempty and in range")
    if any(a >= b for a, b in pairwise(value)):
        raise ValueError(f"{name} must be strictly increasing")


def _pack(wires: tuple[int, ...], value: int) -> int:
    return sum(((value >> i) & 1) << q for i, q in enumerate(wires))


def _unpack(wires: tuple[int, ...], state: int) -> int:
    return sum(((state >> q) & 1) << i for i, q in enumerate(wires))


@dataclass(frozen=True)
class HmrTableContract:
    """Wire partition and exact table, LSB first (format follows the #153 adapter).

    ``table`` has one row per address word. A row may be ``None`` (do not care) only
    for an illegal address: illegal rows are not part of the theorem. ``target_values``
    ``None`` is the full target cube. Clean wires are zero on input and must be zero on
    output; borrowed wires are arbitrary on input and must be restored, including their
    entanglement with any external reference. The program's own ancilla wires must be
    declared clean.
    """

    width: int
    address_wires: tuple[int, ...]
    target_wires: tuple[int, ...]
    clean_wires: tuple[int, ...]
    borrowed_wires: tuple[int, ...]
    table: tuple[int | None, ...]
    legal_addresses: tuple[int, ...]
    target_values: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.width) is not int or not 1 <= self.width <= _MAX_WIDTH:
            raise ValueError(f"width must be a plain integer in 1..{_MAX_WIDTH}")
        for name in ("address_wires", "target_wires", "clean_wires", "borrowed_wires"):
            _wires(getattr(self, name), name)
        if not 1 <= len(self.address_wires) <= _MAX_ADDRESS_BITS:
            raise ValueError(f"address width must be in 1..{_MAX_ADDRESS_BITS}")
        if not 1 <= len(self.target_wires) <= _MAX_TARGET_BITS:
            raise ValueError(f"target width must be in 1..{_MAX_TARGET_BITS}")
        every = self.address_wires + self.target_wires + self.clean_wires + self.borrowed_wires
        if len(every) != self.width or set(every) != set(range(self.width)):
            raise ValueError("wire roles must partition the physical width exactly")
        if type(self.table) is not tuple or len(self.table) != 1 << len(self.address_wires):
            raise ValueError("table must have exactly one row per address word")
        _ordered(self.legal_addresses, len(self.table), "legal_addresses")
        legal = set(self.legal_addresses)
        for address, row in enumerate(self.table):
            if row is None:
                if address in legal:
                    raise ValueError(f"legal address {address} needs an integer table row")
            elif type(row) is not int or not 0 <= row < 1 << len(self.target_wires):
                raise ValueError("table rows must be in-range integer XOR words or None")
        if self.target_values is not None:
            _ordered(self.target_values, 1 << len(self.target_wires), "target_values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "symq_hmr_table_contract", "schema_version": 1,
            "width": self.width, "address_wires": list(self.address_wires),
            "target_wires": list(self.target_wires), "clean_wires": list(self.clean_wires),
            "borrowed_wires": list(self.borrowed_wires), "table": list(self.table),
            "legal_addresses": list(self.legal_addresses),
            "target_values": None if self.target_values is None else list(self.target_values),
            "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained",
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def input_count(self) -> int:
        targets = (1 << len(self.target_wires) if self.target_values is None
                   else len(self.target_values))
        return len(self.legal_addresses) * targets << len(self.borrowed_wires)

    def legal_inputs(self) -> list[int]:
        """Every legal basis input as a physical basis index (clean wires zero)."""
        targets = (range(1 << len(self.target_wires)) if self.target_values is None
                   else self.target_values)
        return [_pack(self.address_wires, a) | _pack(self.target_wires, z)
                | _pack(self.borrowed_wires, d)
                for a in self.legal_addresses for z in targets
                for d in range(1 << len(self.borrowed_wires))]

    def ideal(self, state: int) -> int:
        """``W`` on one legal basis input."""
        row = self.table[_unpack(self.address_wires, state)]
        if row is None:
            raise ValueError("ideal() is defined on legal inputs only")
        return state ^ _pack(self.target_wires, row)

    def coordinates(self, state: int) -> dict[str, int]:
        return {"address": _unpack(self.address_wires, state),
                "target": _unpack(self.target_wires, state),
                "borrowed": _unpack(self.borrowed_wires, state),
                "clean": _unpack(self.clean_wires, state)}


@dataclass(frozen=True)
class HmrTableResult:
    """``equivalent`` is a proof; ``not_proved`` carries a failed obligation and witness.

    ``not_proved`` is returned only for the channel obligations ``permutation``,
    ``branch_support`` and ``branch_phase``. Because the criterion is also necessary
    for this contract, its witness names a legal coherence ``|x><y|`` (``x == y`` for a
    basis error) on which the program's channel differs from the ideal one;
    ``coefficient`` is then the exact coefficient of ``W|x><y|W†`` in the program's
    output (the ideal value is 1). ``unsupported`` means the request is outside this
    contract (a visible record asks for an instrument contract, obligation
    ``visible_record``; a forged or out-of-grammar source; a width/ancilla mismatch) and
    says nothing about the channel. ``inconclusive`` is a cap or the budget.
    """

    status: str
    reason: str
    obligation: str | None
    witness: dict[str, Any] | None
    checked_inputs: int
    branches: int
    hmr_events: int
    events: int
    source_sha256: str
    contract_sha256: str

    @property
    def equivalent(self) -> bool:
        return self.status == "equivalent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "symq_hmr_table_result", "schema_version": 1,
            "status": self.status, "reason": self.reason, "obligation": self.obligation,
            "witness": self.witness, "checked_inputs": self.checked_inputs,
            "branches": self.branches, "hmr_events": self.hmr_events, "events": self.events,
            "source_sha256": self.source_sha256, "contract_sha256": self.contract_sha256,
        }


def _condition(name: str | None, memory: dict[str, int]) -> bool:
    if name is None:
        return True
    if name.startswith("!"):
        return not memory[name[1:]]
    return bool(memory[name])


def _permute(state: int, op: HOp) -> int:
    wires = op.wires
    if op.kind in {"x", "cx", "ccx", "mcx"}:
        *controls, target = wires
        if all(state >> c & 1 for c in controls):
            return state ^ (1 << target)
        return state
    if op.kind == "swap":
        enabled, (a, b) = True, wires
    else:
        control, a, b = wires
        enabled = bool(state >> control & 1)
    if enabled and (state >> a & 1) != (state >> b & 1):
        return state ^ (1 << a) ^ (1 << b)
    return state


Path = tuple[int, int, dict[str, int], tuple[int, ...]]
"""``(basis state, sign, classical memory, branch key)`` of one Kraus trajectory."""


def _snapshot_contract(contract: HmrTableContract) -> HmrTableContract:
    """Detached, revalidated contract: a frozen object mutated after construction (for
    example an emptied legal set) is rebuilt through ``__post_init__`` and refused."""
    if type(contract) is not HmrTableContract:
        raise TypeError("an HmrTableContract is required")
    return HmrTableContract(
        contract.width, contract.address_wires, contract.target_wires,
        contract.clean_wires, contract.borrowed_wires, contract.table,
        contract.legal_addresses, contract.target_values)


def _snapshot_program(program: HybridProgram) -> HybridProgram:
    """Detached program rebuilt from exact primitives only.

    ``HybridProgram.validate`` tests operation names by set membership, which a ``str``
    subclass can spoof through ``__hash__``/``__eq__``. Every field is required to have
    an exact primitive type before a fresh ``HOp`` is built, and the same snapshot is
    then interpreted and hashed.
    """
    if type(program) is not HybridProgram:
        raise TypeError("a HybridProgram is required")
    data, ancillas, source_ops = program.data, program.ancillas, program.ops
    if type(data) is not int or type(ancillas) is not int:
        raise UnsupportedOperation("program dimensions must be exact integers")
    if type(source_ops) is not list:
        raise UnsupportedOperation("ops must be a list")
    ops = []
    for index, op in enumerate(list(source_ops)):
        if type(op) is not HOp:
            raise UnsupportedOperation(f"op {index}: HOp required")
        kind, wires, value = op.kind, op.wires, op.value
        if type(kind) is not str:
            raise UnsupportedOperation(f"op {index}: operation name must be an exact str")
        if type(wires) is not tuple or any(type(q) is not int for q in wires):
            raise UnsupportedOperation(f"op {index}: wires must be a tuple of exact ints")
        names = (op.slot, op.condition, op.source)
        if any(name is not None and type(name) is not str for name in names):
            raise UnsupportedOperation(f"op {index}: slot names must be exact str")
        if value is not None and type(value) is not int:
            raise UnsupportedOperation(f"op {index}: value must be an exact int")
        ops.append(HOp(kind, wires, *names, value))
    return HybridProgram(data, ancillas, ops)


def _branches(ops: tuple[HOp, ...], start: int, *, guard: Guard, max_branches: int,
              steps: list[int], max_steps: int) -> dict[tuple[int, ...], tuple[int, int]]:
    """``branch key -> (sign, output basis)`` for every nonzero branch on one basis ket.

    HMR on a basis ket gives both outcomes, each with amplitude ``±1/sqrt 2``; Z
    measurement and reset select the single nonzero Kraus outcome (the wire's value).
    """
    paths: list[Path] = [(start, 1, {}, ())]
    for op in ops:
        guard.check_time()
        steps[0] += len(paths)
        if steps[0] > max_steps:
            raise ResourceLimitExceeded("steps", max_steps, steps[0])
        kind = op.kind
        if kind == "hmr":
            bit = 1 << op.wires[0]
            slot = op.slot
            assert slot is not None
            doubled: list[Path] = []
            for state, sign, memory, key in paths:
                for outcome in (0, 1):
                    table = dict(memory)
                    table[slot] = outcome
                    flip = outcome and state & bit
                    doubled.append((state & ~bit, -sign if flip else sign, table,
                                    key + (outcome,)))
            if len(doubled) > max_branches:
                raise ResourceLimitExceeded("branches", max_branches, len(doubled))
            guard.check_terms(len(doubled))
            paths = doubled
        elif kind in {"measure_z", "reset"}:
            q = op.wires[0]
            updated: list[Path] = []
            for state, sign, memory, key in paths:
                outcome = state >> q & 1
                if kind == "measure_z":
                    assert op.slot is not None
                    memory[op.slot] = outcome
                else:
                    state &= ~(1 << q)
                updated.append((state, sign, memory, key + (outcome,)))
            paths = updated
        elif kind in _CLASSICAL:
            assert op.slot is not None
            for _state, _sign, memory, _key in paths:
                if kind == "store":
                    assert op.value is not None
                    memory[op.slot] = op.value
                elif kind == "invert":
                    memory[op.slot] ^= int(_condition(op.condition, memory))
                else:
                    assert op.source is not None
                    memory[op.slot] ^= memory[op.source]
        elif kind in _PERMUTATIONS:
            paths = [(_permute(s, op) if _condition(op.condition, m) else s, sign, m, k)
                     for s, sign, m, k in paths]
        elif kind in _SIGNS:
            mask = sum(1 << q for q in op.wires)
            paths = [(s, -sign if _condition(op.condition, m) and s & mask == mask else sign,
                      m, k) for s, sign, m, k in paths]
        else:
            raise UnsupportedOperation(f"operation {kind!r} is outside the checked grammar")
    result = {key: (sign, state) for state, sign, _memory, key in paths}
    if len(result) != len(paths):
        raise InternalInconsistency("two trajectories share one branch key")
    return result


def _coefficient(left: dict[tuple[int, ...], tuple[int, int]],
                 right: dict[tuple[int, ...], tuple[int, int]], hmr: int) -> Fraction:
    """Coefficient of ``W|x><y|W†`` in ``E(|x><y|)`` when every branch output is correct."""
    total = sum(sign * right[key][0] for key, (sign, _) in left.items() if key in right)
    return Fraction(total, 1 << hmr)


def check_hmr_table_xor(
    program: HybridProgram,
    contract: HmrTableContract,
    *,
    observed_slots: tuple[str, ...] = (),
    budget: Budget | None = None,
    max_inputs: int = 4096,
    max_branches: int = 4096,
    max_steps: int = 2_000_000,
) -> HmrTableResult:
    """Decide the branchwise criterion on every legal basis input, within explicit caps.

    ``observed_slots`` names classical slots the caller keeps visible. The XOR contract has
    no classical output, so any visible record is ``unsupported`` (obligation
    ``visible_record``) instead of being silently forgotten. Caps and the budget, own or
    inherited from a ``VerificationSession``, give ``inconclusive``; ``max_nodes`` and
    ``max_bytes`` are refused. Contract and program are detached snapshots rebuilt from
    exact primitives before anything is checked or hashed.
    """
    for name, value in (("max_inputs", max_inputs), ("max_branches", max_branches),
                        ("max_steps", max_steps)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if type(observed_slots) is not tuple or any(type(s) is not str for s in observed_slots):
        raise ValueError("observed_slots must be a tuple of slot names")
    guard = Guard(budget)
    # The merged budget, so a limit inherited from a VerificationSession is refused too.
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError("max_nodes/max_bytes do not apply to this enumeration")
    # One detached snapshot of each input is checked, interpreted, hashed and witnessed.
    contract = _snapshot_contract(contract)
    if type(program) is not HybridProgram:
        raise TypeError("a HybridProgram is required")
    contract_sha = contract.sha256
    try:
        guard.check_time()
        program = _snapshot_program(program)
        ops = tuple(step.operation for step in
                    freeze_hybrid(program, budget=guard.inherited_budget()).operations)
        source_sha = canonical_sha256(program_to_dict(program))
        guard.check_time()
    except UnsupportedOperation as error:
        return HmrTableResult("unsupported", str(error), None, None, 0, 0, 0, 0, "",
                              contract_sha)
    except ResourceLimitExceeded as error:  # the deadline, own or inherited
        return HmrTableResult("inconclusive", str(error), None, None, 0, 0, 0, 0, "",
                              contract_sha)
    hmr = sum(op.kind == "hmr" for op in ops)
    events = sum(op.kind in _EVENTS for op in ops)

    def result(status: str, reason: str, obligation: str | None = None,
               witness: dict[str, Any] | None = None, checked: int = 0) -> HmrTableResult:
        if status in ("equivalent", "not_proved"):
            guard.check_time()  # no decisive verdict after the deadline
        return HmrTableResult(status, reason, obligation, witness, checked,
                              1 << hmr if hmr < 64 else 0, hmr, events, source_sha,
                              contract_sha)

    if program.width != contract.width:
        return result("unsupported", "program and contract widths differ")
    ancillas = set(range(program.data, program.width))
    if not ancillas <= set(contract.clean_wires):
        return result("unsupported", "program ancilla wires must be declared clean")
    if observed_slots:
        return result("unsupported", "the XOR contract has no classical output; a visible "
                      "record asks for an instrument contract, which is not checked here",
                      "visible_record", {"slots": list(observed_slots)})
    if contract.input_count() < 1:
        raise InternalInconsistency("a validated contract has an empty legal domain")
    if contract.input_count() > max_inputs:
        return result("inconclusive", f"{contract.input_count()} legal inputs exceed "
                      f"max_inputs={max_inputs}")
    if hmr >= 63 or 1 << hmr > max_branches:
        return result("inconclusive", f"2**{hmr} branches exceed max_branches={max_branches}")

    def describe(state: int) -> dict[str, int]:
        return {"basis": state, **contract.coordinates(state)}

    steps = [0]
    reference: dict[tuple[int, ...], tuple[int, int]] | None = None
    first = 0
    checked = 0
    try:
        for state in contract.legal_inputs():
            guard.check_time()
            branches = _branches(ops, state, guard=guard, max_branches=max_branches,
                                 steps=steps, max_steps=max_steps)
            if len(branches) != 1 << hmr:
                raise InternalInconsistency("a basis input lost normalization")
            expected = contract.ideal(state)
            for key, (_sign, output) in branches.items():
                if output != expected:
                    witness = {"pair": [state, state], "input": describe(state),
                               "branch": list(key), "output": describe(output),
                               "expected": describe(expected)}
                    return result("not_proved", "a branch maps a legal input to the wrong "
                                  "basis state (table, borrowed or clean wire)",
                                  "permutation", witness, checked + 1)
            checked += 1
            if reference is None:
                reference, first = branches, state
                continue
            missing = sorted(set(reference) ^ set(branches))
            mismatch = [key for key in sorted(reference)
                        if key in branches and branches[key][0] != reference[key][0]]
            if missing or mismatch:
                coefficient = _coefficient(reference, branches, hmr)
                if coefficient == 1:
                    raise InternalInconsistency("a refused pair kept its full coherence")
                key = missing[0] if missing else mismatch[0]
                witness = {"pair": [first, state], "inputs": [describe(first),
                                                              describe(state)],
                           "branch": list(key), "coefficient": str(coefficient)}
                if missing:
                    witness["present_for"] = first if key in reference else state
                    return result("not_proved", "a Kraus branch is nonzero on one legal input "
                                  "and zero on another (input-dependent outcome)",
                                  "branch_support", witness, checked)
                witness["signs"] = [reference[key][0], branches[key][0]]
                return result("not_proved", "a Kraus branch carries an input-dependent "
                              "phase on the legal support", "branch_phase", witness, checked)
        if checked != contract.input_count() or checked < 1:
            raise InternalInconsistency("a positive verdict must cover every legal input")
        return result("equivalent", "every Kraus branch equals c_m W on the legal support",
                      checked=checked)
    except ResourceLimitExceeded as error:
        return HmrTableResult("inconclusive", str(error), None, None, checked,
                              1 << hmr if hmr < 64 else 0, hmr, events, source_sha,
                              contract_sha)


def and_uncompute_example() -> tuple[HybridProgram, HmrTableContract]:
    """Public synthetic loader: T = [0b00, 0b01, 0b11, *] on legal addresses {0, 1, 2}.

    Wires: address 0, 1; target 2, 3; borrowed 4; clean ancilla 5. Target bit 0 gets
    ``NOT [a == 0]`` through an ancilla AND of the negated address bits; target bit 1
    gets address bit 1 through the borrowed wire (toggle trick). The AND is
    uncomputed by HMR followed by a CZ phase correction conditioned on the outcome.
    """
    p = HybridProgram(5, 1)
    p.x(0).x(1).ccx(0, 1, 5).x(0).x(1)           # ancilla = [a == 0]
    p.cx(5, 2).x(2)                               # t0 ^= NOT [a == 0]
    p.cx(4, 3).cx(1, 4).cx(4, 3).cx(1, 4)        # t1 ^= a1 using borrowed wire 4
    p.hmr(5, "b0")                                # phase (-1)^(b0 [a == 0]), ancilla 0
    p.x(0).x(1).cz(0, 1, condition="b0").x(0).x(1)  # correction (-1)^(b0 [a == 0])
    contract = HmrTableContract(
        width=6, address_wires=(0, 1), target_wires=(2, 3), clean_wires=(5,),
        borrowed_wires=(4,), table=(0b00, 0b01, 0b11, None), legal_addresses=(0, 1, 2))
    return p, contract
