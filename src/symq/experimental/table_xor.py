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
from symq.experimental.domains import PredicateDomain, domain_from_dict
from symq.hashing import canonical_sha256
from symq.resources import Budget, Guard
from symq.sat import Contract, check_sat_equivalence
from symq.sat.assumptions import And, Const, Eq, Expr, ExprError, Not, Var, Xor, validate

__all__ = [
    "PredicateValues",
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
class PredicateValues:
    """Compact nonempty word domain, with a concretely checked witness.

    ``x.i`` refers to logical bit i of this address or target word, not to a
    physical circuit wire. The witness establishes nonemptiness only; it does
    not establish that a surrounding program prepares this support.
    """

    domain: PredicateDomain
    witness: int

    def __post_init__(self) -> None:
        if type(self.domain) is not PredicateDomain:
            raise TypeError("predicate values require a PredicateDomain")
        if type(self.domain.data) is not int or not 1 <= self.domain.data <= 16:
            raise ValueError("predicate word width must be in 1..16")
        domain = domain_from_dict(self.domain.to_dict())
        if type(self.witness) is not int or not domain.contains(self.witness):
            raise ValueError("predicate witness must be an admitted in-range word")
        object.__setattr__(self, "domain", domain)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "predicate", "domain": self.domain.to_dict(),
                "witness": self.witness}

    @classmethod
    def below(cls, width: int, upper: int) -> PredicateValues:
        """The nonempty unsigned interval ``0 <= word < upper``, without a list."""
        if type(width) is not int or not 1 <= width <= 16:
            raise ValueError("predicate word width must be in 1..16")
        if type(upper) is not int or not 1 <= upper <= 1 << width:
            raise ValueError("upper bound must be in 1..2**width")
        if upper == 1 << width:
            return cls(PredicateDomain(width, Const(True)), 0)
        clauses = []
        for bit in range(width):
            if upper >> bit & 1:
                terms = [Not(Var(f"x.{bit}"))]
                for high in range(bit + 1, width):
                    variable = Var(f"x.{high}")
                    terms.append(variable if upper >> high & 1 else Not(variable))
                clauses.append(Not(_balanced(terms, _and)))
        return cls(PredicateDomain(width, Not(_balanced(clauses, _and))), 0)

    @classmethod
    def from_dict(cls, value: Any) -> PredicateValues:
        if (type(value) is not dict or set(value) != {"kind", "domain", "witness"}
                or type(value["kind"]) is not str or value["kind"] != "predicate"):
            raise ValueError("predicate values have missing or unknown fields")
        return cls(domain_from_dict(value["domain"]), value["witness"])


def _validate_values(value: Any, bound: int, name: str) -> None:
    if type(value) is PredicateValues:
        fresh = PredicateValues.from_dict(value.to_dict())
        if (1 << fresh.domain.data) != bound:
            raise ValueError(f"{name} predicate width disagrees with wire layout")
    else:
        _ordered_values(value, bound, name)


def _values_document(value: tuple[int, ...] | PredicateValues | None) -> dict[str, Any]:
    if value is None:
        return {"kind": "full"}
    if type(value) is PredicateValues:
        return value.to_dict()
    return {"kind": "values", "values": list(value)}


def _parse_values(value: Any, *, allow_full: bool, allow_predicate: bool):
    if type(value) is not dict or type(value.get("kind")) is not str:
        raise ValueError("word domain must be a closed object")
    if allow_full and value == {"kind": "full"}:
        return None
    if (set(value) == {"kind", "values"} and value["kind"] == "values"
            and type(value["values"]) is list):
        return tuple(value["values"])
    if allow_predicate and value["kind"] == "predicate":
        return PredicateValues.from_dict(value)
    raise ValueError("invalid word domain")


@dataclass(frozen=True)
class TableXorContract:
    """Physical wire partition and exact external table specification.

    Address and target bit i is stored at the i-th listed wire, least-significant
    bit first. target_values=None is explicitly the FULL target cube. A tuple
    or PredicateValues restricts targets to the declared word domain.
    All other wires must be declared zero-prepared scratch or arbitrary borrowed
    dirty workspace; all outputs are retained and compared.
    """

    width: int
    address_wires: tuple[int, ...]
    target_wires: tuple[int, ...]
    clean_wires: tuple[int, ...]
    borrowed_wires: tuple[int, ...]
    table: tuple[int, ...]
    legal_addresses: tuple[int, ...] | PredicateValues
    target_values: tuple[int, ...] | PredicateValues | None
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
        _validate_values(self.legal_addresses, len(self.table), "legal_addresses")
        if self.target_values is not None:
            _validate_values(self.target_values, 1 << len(self.target_wires), "target_values")
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
        compact = (type(self.legal_addresses) is PredicateValues
                   or type(self.target_values) is PredicateValues)
        document = {
            "kind": "symq_table_xor_contract", "schema_version": 1,
            "width": self.width, "address_wires": list(self.address_wires),
            "target_wires": list(self.target_wires), "clean_wires": list(self.clean_wires),
            "borrowed_wires": list(self.borrowed_wires), "table": list(self.table),
            "target_domain": _values_document(self.target_values),
            "table_id": self.table_id, "slot_id": self.slot_id,
            "theorem": self.theorem, "bit_order": self.bit_order,
        }
        if compact:
            document["schema_version"] = 2
            document["address_domain"] = _values_document(self.legal_addresses)
        else:
            document["legal_addresses"] = list(self.legal_addresses)
        return document

    @classmethod
    def from_dict(cls, value: Any) -> TableXorContract:
        keys = {"kind", "schema_version", "width", "address_wires", "target_wires",
                "clean_wires", "borrowed_wires", "table",
                "target_domain", "table_id", "slot_id", "theorem", "bit_order"}
        if (type(value) is not dict or type(value.get("schema_version")) is not int
                or value["schema_version"] not in (1, 2)):
            raise ValueError("unsupported table contract version")
        version = value["schema_version"]
        keys.add("legal_addresses" if version == 1 else "address_domain")
        if type(value) is not dict or set(value) != keys:
            raise ValueError("table contract has missing or unknown fields")
        if value["kind"] != "symq_table_xor_contract" or type(value["kind"]) is not str:
            raise ValueError("wrong table contract kind")
        target_values = _parse_values(value["target_domain"], allow_full=True,
                                      allow_predicate=version == 2)
        arrays = ("address_wires", "target_wires", "clean_wires", "borrowed_wires",
                  "table")
        if version == 1:
            arrays += ("legal_addresses",)
        if any(type(value[key]) is not list for key in arrays):
            raise ValueError("wire and table fields must be JSON arrays")
        addresses = (tuple(value["legal_addresses"]) if version == 1 else
                     _parse_values(value["address_domain"], allow_full=False,
                                   allow_predicate=True))
        if (version == 2 and type(addresses) is not PredicateValues
                and type(target_values) is not PredicateValues):
            raise ValueError("version 2 requires at least one predicate domain")
        return cls(
            width=value["width"], address_wires=tuple(value["address_wires"]),
            target_wires=tuple(value["target_wires"]),
            clean_wires=tuple(value["clean_wires"]),
            borrowed_wires=tuple(value["borrowed_wires"]),
            table=tuple(value["table"]), legal_addresses=addresses,
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


def _bind_predicate(expression: Expr, wires: tuple[int, ...]) -> Expr:
    """Logical word bits to physical inputs; the domain is validated first."""
    if type(expression) is Const:
        return expression
    if type(expression) is Var:
        return Var(f"x.{wires[int(expression.name[2:])]}")
    if type(expression) is Not:
        return Not(_bind_predicate(expression.operand, wires))
    if type(expression) not in (And, Xor, Eq):
        raise ExprError("unknown predicate node")
    return type(expression)(_bind_predicate(expression.left, wires),
                            _bind_predicate(expression.right, wires))


def _allow_values(wires: tuple[int, ...], values: tuple[int, ...] | PredicateValues) -> Expr:
    if type(values) is PredicateValues:
        return _bind_predicate(values.domain.predicate, wires)
    clauses = []
    for value in values:
        tests = [Var(f"x.{wire}") if value >> bit & 1 else Not(Var(f"x.{wire}"))
                 for bit, wire in enumerate(wires)]
        clauses.append(_balanced(tests, _and))
    # One De Morgan layer over a balanced AND, instead of three extra levels
    # per binary OR. This keeps even a 16-bit listed domain inside MAX_DEPTH.
    return Not(_balanced([Not(clause) for clause in clauses], _and))


def _full_values(value: tuple[int, ...] | PredicateValues, width: int) -> bool:
    return type(value) is tuple and len(value) == 1 << width


def _assumption(spec: TableXorContract) -> Expr | None:
    parts = []
    if not _full_values(spec.legal_addresses, len(spec.address_wires)):
        parts.append(_allow_values(spec.address_wires, spec.legal_addresses))
    if (spec.target_values is not None and
            not _full_values(spec.target_values, len(spec.target_wires))):
        parts.append(_allow_values(spec.target_wires, spec.target_values))
    if not parts:
        return None
    result = _balanced(parts, _and)
    validate(result, frozenset(f"x.{q}" for q in range(spec.width)))
    return result


def _contains(values: tuple[int, ...] | PredicateValues | None, word: int) -> bool:
    if values is None:
        return True
    if type(values) is PredicateValues:
        return values.domain.contains(word)
    return word in values


def _enumerated_values(values: tuple[int, ...] | PredicateValues | None,
                       width: int, guard: Guard):
    if values is None:
        return range(1 << width)
    if type(values) is tuple:
        return values
    admitted = []
    for word in range(1 << width):
        guard.check_time()
        if values.domain.contains(word):
            admitted.append(word)
    return tuple(admitted)


def _in_domain(spec: TableXorContract, state: int) -> bool:
    if any(state >> q & 1 for q in spec.clean_wires):
        return False
    address = _unpack(spec.address_wires, state)
    target = _unpack(spec.target_wires, state)
    return (_contains(spec.legal_addresses, address)
            and _contains(spec.target_values, target))


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
    guard = Guard(budget)
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
    # Checked on the merged budget, so an enclosing VerificationSession cannot slip them in.
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError("native max_nodes/max_bytes are not supported in this adapter")
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
            addresses = _enumerated_values(spec.legal_addresses, len(spec.address_wires), guard)
            targets = _enumerated_values(spec.target_values, len(spec.target_wires), guard)
            total = len(addresses) * len(targets) * (1 << len(spec.borrowed_wires))
            if total > max_states:
                raise ResourceLimitExceeded("basis states", max_states, total)
            guard.check_terms(total)
            count = 0
            for address, target, dirty in product(
                    addresses, targets, range(1 << len(spec.borrowed_wires))):
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
    max_reference_gates: int = 100_000,
    max_source_gates: int = 200_000,
    max_states: int = 65_536,
) -> TableXorResult:
    """Fresh verification, requiring the consumer's own source and spec pins.

    Neither the record nor a digest is proof authority. Only a fresh exact check
    can return equivalent; stale or forged records, and a fresh check that
    refutes the record, raise ReceiptMismatch. A fresh check that cannot
    conclude (a cap, the deadline, SAT unavailable) is returned as-is
    (``inconclusive``/``unsupported``): it says nothing about the receipt.
    Pass the same caps that the original check needed.
    """
    guard = Guard(budget)
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
            or receipt["theorem"] != fresh_spec.theorem
            or receipt["backend"] != backend):
        raise ReceiptMismatch("source, specification, slot, or theorem changed")
    try:
        guard.check_time()
    except ResourceLimitExceeded as exc:
        return TableXorResult("inconclusive", str(exc), fresh_spec.theorem, backend, src, con)
    fresh = check_table_xor(original, fresh_spec, backend=backend,
                            budget=guard.inherited_budget(),
                            max_reference_gates=max_reference_gates,
                            max_source_gates=max_source_gates, max_states=max_states)
    if fresh.status in ("inconclusive", "unsupported"):
        return fresh
    if not fresh.equivalent:
        raise ReceiptMismatch(f"fresh proof did not succeed: {fresh.status}: {fresh.reason}")
    if receipt != fresh.to_dict():
        raise ReceiptMismatch("saved success fields disagree with fresh verification")
    return fresh
