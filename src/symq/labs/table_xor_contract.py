"""Source-bound finite XOR-table contracts for phase-free reversible loaders.

Experimental adapter for issue #144. The supported grammar is exactly Circuit's
X/CX/CCX/MCX permutation grammar; it contains no measurement, global phases,
implicit target padding, borrowed-wire disposal or coherent-control authority.

A total check on every legal BASIS input additionally proves the same unitary
isometry on their coherent span: each accepted gate is a basis permutation with
unit amplitude, so every |x><y| and every external reference is preserved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise, product
from typing import Any

from symq.circuit import Circuit, Gate
from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
from symq.hashing import canonical_sha256
from symq.resources import Budget, Guard
from symq.sat import Contract, check_sat_equivalence
from symq.sat.assumptions import And, Expr, ExprError, Not, Var, validate

__all__ = [
    "ReceiptMismatch",
    "TableXorContract",
    "TableXorResult",
    "check_table_xor",
    "replay_table_xor",
]

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_THEOREMS = {"classical", "coherent"}
_BACKENDS = {"sat", "exhaustive"}
_MAX_ADDRESS_BITS = 16
_MAX_TARGET_BITS = 16
_MAX_WIDTH = 128


class ReceiptMismatch(ValueError):
    """A prior receipt cannot be replayed under the supplied source/contract."""


def _wires(value: Any, name: str) -> None:
    if type(value) is not tuple or any(type(v) is not int or v < 0 for v in value):
        raise ValueError(f"{name} must be a tuple of nonnegative plain integers")


def _ordered_values(value: Any, bound: int, name: str) -> None:
    _wires(value, name)
    if not value or any(v >= bound for v in value):
        raise ValueError(f"{name} must be nonempty and in range")
    if any(a >= b for a, b in pairwise(value)):
        raise ValueError(f"{name} must be strictly increasing and distinct")


@dataclass(frozen=True)
class TableXorContract:
    """Physical wire partition and exact external table specification.

    Address and target bit i is stored at the i-th listed wire, least-significant
    bit first. target_values=None is explicitly the FULL target cube. A tuple
    restricts targets to the listed integer encodings (not a full dirty target).
    All other wires must be declared zero-prepared scratch or arbitrary borrowed
    dirty workspace; all outputs are retained and compared.
    """

    width: int
    address_wires: tuple[int, ...]
    target_wires: tuple[int, ...]
    clean_wires: tuple[int, ...]
    borrowed_wires: tuple[int, ...]
    table: tuple[int, ...]
    legal_addresses: tuple[int, ...]
    target_values: tuple[int, ...] | None
    table_id: str
    slot_id: str
    theorem: str
    bit_order: str = "lsb_first"

    def __post_init__(self) -> None:
        if type(self.width) is not int or not 1 <= self.width <= _MAX_WIDTH:
            raise ValueError("width must be a plain integer in 1..128")
        for name in ("address_wires", "target_wires", "clean_wires", "borrowed_wires"):
            _wires(getattr(self, name), name)
        if not self.address_wires or len(self.address_wires) > _MAX_ADDRESS_BITS:
            raise ValueError("address width must be in 1..16")
        if not self.target_wires or len(self.target_wires) > _MAX_TARGET_BITS:
            raise ValueError("target width must be in 1..16")
        all_wires = (self.address_wires + self.target_wires
                     + self.clean_wires + self.borrowed_wires)
        if len(all_wires) != self.width or set(all_wires) != set(range(self.width)):
            raise ValueError("wire partition must cover each physical wire exactly once")
        if type(self.table) is not tuple or len(self.table) != 1 << len(self.address_wires):
            raise ValueError("table must supply exactly one row per address, including illegal rows")
        if any(type(v) is not int or not 0 <= v < 1 << len(self.target_wires)
               for v in self.table):
            raise ValueError("table rows must be exact, in-range integer XOR words")
        _ordered_values(self.legal_addresses, len(self.table), "legal_addresses")
        if self.target_values is not None:
            _ordered_values(self.target_values, 1 << len(self.target_wires), "target_values")
        if self.bit_order != "lsb_first" or type(self.bit_order) is not str:
            raise ValueError("only explicit lsb_first wire ordering is accepted")
        if type(self.theorem) is not str or self.theorem not in _THEOREMS:
            raise ValueError("theorem must be classical or coherent")
        for key in ("table_id", "slot_id"):
            value = getattr(self, key)
            if type(value) is not str or not value or len(value) > 128 or not value.isprintable():
                raise ValueError(f"{key} must be a nonempty printable identity (max 128)")
        if self.table_id == self.slot_id:
            # Different namespaces prevent accidentally treating a table as its emission slot.
            raise ValueError("table_id and slot_id must be distinct identities")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "symq_table_xor_contract", "schema_version": 1,
            "width": self.width, "address_wires": list(self.address_wires),
            "target_wires": list(self.target_wires), "clean_wires": list(self.clean_wires),
            "borrowed_wires": list(self.borrowed_wires), "table": list(self.table),
            "legal_addresses": list(self.legal_addresses),
            "target_domain": ({"kind": "full"} if self.target_values is None else
                              {"kind": "values", "values": list(self.target_values)}),
            "table_id": self.table_id, "slot_id": self.slot_id,
            "theorem": self.theorem, "bit_order": self.bit_order,
        }

    @classmethod
    def from_dict(cls, value: Any) -> TableXorContract:
        keys = {"kind", "schema_version", "width", "address_wires", "target_wires",
                "clean_wires", "borrowed_wires", "table", "legal_addresses",
                "target_domain", "table_id", "slot_id", "theorem", "bit_order"}
        if type(value) is not dict or set(value) != keys:
            raise ValueError("table contract has missing or unknown fields")
        if value["kind"] != "symq_table_xor_contract" or type(value["kind"]) is not str:
            raise ValueError("wrong table contract kind")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("unsupported table contract version")
        domain = value["target_domain"]
        if type(domain) is not dict:
            raise ValueError("target_domain must be a closed object")
        if domain == {"kind": "full"} and type(domain["kind"]) is str:
            target_values = None
        elif set(domain) == {"kind", "values"} and type(domain["kind"]) is str \
                and domain["kind"] == "values" and type(domain["values"]) is list:
            target_values = tuple(domain["values"])
        else:
            raise ValueError("invalid target_domain; use full or explicit values")
        arrays = ("address_wires", "target_wires", "clean_wires", "borrowed_wires",
                  "table", "legal_addresses")
        if any(type(value[key]) is not list for key in arrays):
            raise ValueError("wire and table fields must be JSON arrays")
        return cls(
            width=value["width"], address_wires=tuple(value["address_wires"]),
            target_wires=tuple(value["target_wires"]),
            clean_wires=tuple(value["clean_wires"]),
            borrowed_wires=tuple(value["borrowed_wires"]),
            table=tuple(value["table"]), legal_addresses=tuple(value["legal_addresses"]),
            target_values=target_values, table_id=value["table_id"],
            slot_id=value["slot_id"], theorem=value["theorem"],
            bit_order=value["bit_order"],
        )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True)
class TableXorResult:
    status: str
    reason: str
    theorem: str
    backend: str
    source_sha256: str
    contract_sha256: str
    witness: int | None = None
    checked_states: int = 0
    sat_clauses: int = 0

    @property
    def equivalent(self) -> bool:
        return self.status == "equivalent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "symq_table_xor_result", "schema_version": 1,
            "status": self.status, "reason": self.reason, "theorem": self.theorem,
            "backend": self.backend, "source_sha256": self.source_sha256,
            "contract_sha256": self.contract_sha256, "witness": self.witness,
            "checked_states": self.checked_states, "sat_clauses": self.sat_clauses,
        }


def _freeze(source: Circuit) -> Circuit:
    if type(source) is not Circuit:
        raise TypeError("only actual classical Circuit sources are supported")
    source.validate()
    gates = []
    for gate in source.gates:
        if (type(gate) is not Gate or type(gate.name) is not str
                or type(gate.qubits) is not tuple
                or any(type(q) is not int for q in gate.qubits)):
            raise TypeError("noncanonical or forged Gate in emitted source")
        gates.append(Gate(gate.name, gate.qubits))
    return Circuit(source.width, gates)


def _bitpack(wires: tuple[int, ...], value: int) -> int:
    return sum(((value >> i) & 1) << q for i, q in enumerate(wires))


def _unpack(wires: tuple[int, ...], state: int) -> int:
    return sum(((state >> q) & 1) << i for i, q in enumerate(wires))


def _expected(spec: TableXorContract, initial: int) -> int:
    address = _unpack(spec.address_wires, initial)
    return initial ^ _bitpack(spec.target_wires, spec.table[address])


def _state(spec: TableXorContract, address: int, target: int, dirty: int) -> int:
    return (_bitpack(spec.address_wires, address)
            | _bitpack(spec.target_wires, target)
            | _bitpack(spec.borrowed_wires, dirty))


def _reference(spec: TableXorContract, guard: Guard, max_gates: int) -> Circuit:
    """Construction by row equality; independent of the emitted source."""
    program = Circuit(spec.width)
    for address, word in enumerate(spec.table):
        guard.check_time()
        if not word:
            continue
        inverted = tuple(w for bit, w in enumerate(spec.address_wires)
                         if not (address >> bit) & 1)
        addition = 2 * len(inverted) + word.bit_count()
        if len(program.gates) + addition > max_gates:
            raise ResourceLimitExceeded("reference gates", max_gates,
                                        len(program.gates) + addition)
        guard.check_terms(len(program.gates) + addition)
        for q in inverted:
            program.x(q)
        for bit, q in enumerate(spec.target_wires):
            if word >> bit & 1:
                program.mcx(*spec.address_wires, q)
        for q in reversed(inverted):
            program.x(q)
    guard.check_time()
    return program


def _balanced(items: list[Expr], operation) -> Expr:
    if not items:
        raise ValueError("an empty Boolean clause is not permitted")
    while len(items) > 1:
        items = [operation(items[i], items[i + 1]) if i + 1 < len(items)
                 else items[i] for i in range(0, len(items), 2)]
    return items[0]


def _and(a: Expr, b: Expr) -> Expr:
    return And(a, b)


def _or(a: Expr, b: Expr) -> Expr:
    return Not(And(Not(a), Not(b)))


def _allow_values(wires: tuple[int, ...], values: tuple[int, ...]) -> Expr:
    clauses = []
    for value in values:
        tests = [Var(f"x.{wire}") if value >> bit & 1 else Not(Var(f"x.{wire}"))
                 for bit, wire in enumerate(wires)]
        clauses.append(_balanced(tests, _and))
    return _balanced(clauses, _or)


def _assumption(spec: TableXorContract) -> Expr | None:
    parts = []
    if len(spec.legal_addresses) != len(spec.table):
        parts.append(_allow_values(spec.address_wires, spec.legal_addresses))
    if (spec.target_values is not None and
            len(spec.target_values) != 1 << len(spec.target_wires)):
        parts.append(_allow_values(spec.target_wires, spec.target_values))
    if not parts:
        return None
    result = _balanced(parts, _and)
    validate(result, frozenset(f"x.{q}" for q in range(spec.width)))
    return result


def _in_domain(spec: TableXorContract, state: int) -> bool:
    if any(state >> q & 1 for q in spec.clean_wires):
        return False
    address = _unpack(spec.address_wires, state)
    target = _unpack(spec.target_wires, state)
    return (address in spec.legal_addresses and
            (spec.target_values is None or target in spec.target_values))


def check_table_xor(
    source: Circuit,
    contract: TableXorContract,
    *,
    backend: str = "sat",
    budget: Budget | None = None,
    max_reference_gates: int = 100_000,
    max_source_gates: int = 200_000,
    max_states: int = 65_536,
) -> TableXorResult:
    """Certify the emitted program against the exact *external* table contract.

    SAT compares all states symbolically; exhaustive enumerates the legal input
    basis under an explicit cap. A purely reversible X-family theorem extends
    by linearity to the coherent span, but only if explicitly requested.
    """
    if type(contract) is not TableXorContract:
        raise TypeError("TableXorContract required")
    # Reconstruct even an object forged without running its dataclass initializer.
    spec = TableXorContract.from_dict(contract.to_dict())
    if type(backend) is not str or backend not in _BACKENDS:
        raise ValueError("backend must be sat or exhaustive")
    for name, cap in (("max_reference_gates", max_reference_gates),
                      ("max_source_gates", max_source_gates), ("max_states", max_states)):
        if type(cap) is not int or cap < 1:
            raise ValueError(f"{name} must be a positive plain integer")
    if budget is not None and (budget.max_nodes is not None or budget.max_bytes is not None):
        raise ValueError("native max_nodes/max_bytes are not supported in this adapter")
    guard = Guard(budget)
    program = _freeze(source)
    if program.width != spec.width:
        raise ValueError("emitted program and contract widths disagree")
    source_sha256 = canonical_sha256(program.to_dict())
    contract_sha256 = spec.sha256

    def outcome(status: str, reason: str, *, witness: int | None = None,
                count: int = 0, clauses: int = 0) -> TableXorResult:
        return TableXorResult(status, reason, spec.theorem, backend, source_sha256,
                              contract_sha256, witness, count, clauses)

    try:
        guard.check_time()
        if len(program.gates) > max_source_gates:
            raise ResourceLimitExceeded("source gates", max_source_gates, len(program.gates))
        if backend == "exhaustive":
            targets = (range(1 << len(spec.target_wires)) if spec.target_values is None
                       else spec.target_values)
            total = len(spec.legal_addresses) * len(targets) * (1 << len(spec.borrowed_wires))
            if total > max_states:
                raise ResourceLimitExceeded("basis states", max_states, total)
            guard.check_terms(total)
            count = 0
            for address, target, dirty in product(
                    spec.legal_addresses, targets, range(1 << len(spec.borrowed_wires))):
                guard.check_time()
                initial = _state(spec, address, target, dirty)
                count += 1
                if program.run(initial) != _expected(spec, initial):
                    guard.check_time()
                    return outcome("different", "emitted output differs from exact table",
                                   witness=initial, count=count)
            guard.check_time()
            return outcome("equivalent", "all declared basis states checked", count=count)

        reference = _reference(spec, guard, max_reference_gates)
        try:
            assumption = _assumption(spec)
        except ExprError:
            guard.check_time()
            return outcome("unsupported", "legal-domain predicate exceeds the SAT grammar")
        sat_contract = Contract(
            input_constants={q: 0 for q in spec.clean_wires},
            assumption=assumption,
        )
        verdict = check_sat_equivalence(program, reference, sat_contract,
                                        budget=guard.inherited_budget())
        guard.check_time()
        if verdict.outcome == "different":
            witness = verdict.witness
            if (type(witness) is not int or not _in_domain(spec, witness)
                    or program.run(witness) == _expected(spec, witness)):
                raise InternalInconsistency("SAT witness does not refute the actual table contract")
            guard.check_time()
            return outcome("different", "replayed witness against exact table",
                           witness=witness, clauses=verdict.clauses)
        if verdict.outcome == "equivalent":
            return outcome("equivalent", "SAT UNSAT on all declared inputs",
                           clauses=verdict.clauses)
        return outcome("inconclusive", verdict.detail or "SAT undecided", clauses=verdict.clauses)
    except ResourceLimitExceeded as exc:
        return outcome("inconclusive", str(exc))
    except SatUnavailable as exc:
        return outcome("unsupported", str(exc))


def replay_table_xor(
    source: Circuit,
    contract: TableXorContract,
    receipt: dict[str, Any],
    *,
    expected_source_sha256: str,
    expected_contract_sha256: str,
    backend: str = "sat",
    budget: Budget | None = None,
) -> TableXorResult:
    """Fresh verification, requiring the consumer's own source and spec pins.

    Neither the record nor a digest is proof authority. Only a fresh exact check
    can return equivalent; stale or forged records raise ReceiptMismatch.
    """
    if type(receipt) is not dict or set(receipt) != {
            "kind", "schema_version", "status", "reason", "theorem", "backend",
            "source_sha256", "contract_sha256", "witness", "checked_states", "sat_clauses"}:
        raise ReceiptMismatch("invalid or incomplete table result document")
    if (receipt["kind"] != "symq_table_xor_result"
            or type(receipt["kind"]) is not str
            or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or type(receipt["status"]) is not str or receipt["status"] != "equivalent"
            or type(receipt["theorem"]) is not str or receipt["theorem"] not in _THEOREMS
            or type(receipt["backend"]) is not str or receipt["backend"] not in _BACKENDS
            or type(receipt["reason"]) is not str
            or receipt["witness"] is not None
            or type(receipt["checked_states"]) is not int or receipt["checked_states"] < 0
            or type(receipt["sat_clauses"]) is not int or receipt["sat_clauses"] < 0):
        raise ReceiptMismatch("the recorded success has invalid fields")
    for name, value in (("source", expected_source_sha256),
                        ("contract", expected_contract_sha256)):
        if type(value) is not str or _SHA.fullmatch(value) is None:
            raise ValueError(f"external expected_{name}_sha256 pin is required")
    original = _freeze(source)
    fresh_spec = TableXorContract.from_dict(contract.to_dict())
    src = canonical_sha256(original.to_dict())
    con = fresh_spec.sha256
    if (receipt["source_sha256"] != src or receipt["contract_sha256"] != con
            or src != expected_source_sha256 or con != expected_contract_sha256
            or receipt["theorem"] != fresh_spec.theorem):
        raise ReceiptMismatch("source, specification, slot, or theorem changed")
    fresh = check_table_xor(original, fresh_spec, backend=backend, budget=budget)
    if not fresh.equivalent:
        raise ReceiptMismatch(f"fresh proof did not succeed: {fresh.status}: {fresh.reason}")
    return fresh
