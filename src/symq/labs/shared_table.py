"""Shared wide tables and predicate domains, routed to the existing affine proof.

The maintained table-XOR limits remain unchanged. This closed research v3
transport compiles to the existing affine v2 theorem, retaining the original
contract identity. Preparation of that support is a separate pinned proof.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from symq import Circuit
from symq.experimental.table_xor import PredicateValues
from symq.labs.affine_table import _space, verify_affine_table
from symq.labs.classical_transcript import Program, digest
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.resource_report import resource_report
from symq.labs.rewrite import call_budget
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor

__all__ = ["SharedTable", "prove_shared_table_preparation", "verify_shared_table"]

_FIELDS = {"kind", "schema_version", "width", "address_wires", "target_wires", "clean_wires", "borrowed_wires", "table", "address_domain", "target_space", "bit_order", "records", "outputs"}
_MAX_JSON_BYTES = 2_000_000


def _integer(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in {lower}..{upper}")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class SharedTable:
    """A closed column-major truth table with deduplicated equal bit columns."""

    address_bits: int
    target_bits: int
    columns: tuple[int, ...]
    target_columns: tuple[int, ...]

    def __post_init__(self):
        _integer(self.address_bits, 1, 16, "address width")
        _integer(self.target_bits, 1, 256, "target width")
        if (type(self.columns) is not tuple or not 1 <= len(self.columns) <= self.target_bits
                or any(type(c) is not int or c < 0 or c.bit_length() > 1 << self.address_bits
                       for c in self.columns) or len(set(self.columns)) != len(self.columns)):
            raise ValueError("unique bounded integer bit columns required")
        if (type(self.target_columns) is not tuple or len(self.target_columns) != self.target_bits
                or any(type(i) is not int or not 0 <= i < len(self.columns) for i in self.target_columns)
                or set(self.target_columns) != set(range(len(self.columns)))):
            raise ValueError("complete target-to-shared-column map required")

    @classmethod
    def from_rows(cls, rows, *, address_bits, target_bits):
        _integer(address_bits, 1, 16, "address width")
        _integer(target_bits, 1, 256, "target width")
        if type(rows) not in (list, tuple) or len(rows) != 1 << address_bits:
            raise ValueError("a complete truth table is required")
        if any(type(v) is not int or not 0 <= v < 1 << target_bits for v in rows):
            raise ValueError("table words outside target width")
        columns, indices = [], []
        for bit in range(target_bits):
            value = sum(((word >> bit) & 1) << address for address, word in enumerate(rows))
            if value not in columns:
                columns.append(value)
            indices.append(columns.index(value))
        return cls(address_bits, target_bits, tuple(columns), tuple(indices))

    def to_dict(self):
        self.__post_init__()
        digits = ((1 << self.address_bits) + 3) // 4
        return {"kind": "shared_bit_columns", "address_bits": self.address_bits,
                "target_bits": self.target_bits,
                "columns_hex": [f"{c:0{digits}x}" for c in self.columns],
                "target_columns": list(self.target_columns)}

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {
            "kind", "address_bits", "target_bits", "columns_hex", "target_columns",
        } or value["kind"] != "shared_bit_columns":
            raise ValueError("closed shared-bit-columns document required")
        bits = value["address_bits"]
        _integer(bits, 1, 16, "address width")
        _integer(value["target_bits"], 1, 256, "target width")
        columns = value["columns_hex"]
        digits = ((1 << bits) + 3) // 4
        if (type(columns) is not list or not 1 <= len(columns) <= value["target_bits"]
                or any(type(c) is not str or len(c) != digits
                       or any(x not in "0123456789abcdef" for x in c) for c in columns)
                or type(value["target_columns"]) is not list):
            raise ValueError("canonical fixed-width lowercase hex columns required")
        return cls(bits, value["target_bits"], tuple(int(c, 16) for c in columns),
                   tuple(value["target_columns"]))

    def rows(self, guard):
        rows = []
        for address in range(1 << self.address_bits):
            guard.check_time()
            rows.append(sum(((self.columns[c] >> address) & 1) << bit
                            for bit, c in enumerate(self.target_columns)))
        return rows


def _admitted(domain, guard):
    """The admitted words of a predicate domain, in increasing order.

    The predicate is evaluated on all ``2**n`` words at once: each subexpression becomes the
    set of words where it holds, as the bits of one integer (bit ``a`` for word ``a``). A
    variable ``x.i`` holds on the words whose bit ``i`` is set; ``Not``, ``And``, ``Xor``
    and ``Eq`` are bit operations on those sets. ``PredicateDomain.contains`` evaluates the
    same predicate one word at a time; a test compares the two.
    """
    width = domain.data
    every = (1 << (1 << width)) - 1
    variables = []
    for bit in range(width):
        block = ((1 << (1 << bit)) - 1) << (1 << bit)  # 2**bit ones above 2**bit zeros
        period = 1 << (bit + 1)
        pattern = 0
        for start in range(0, 1 << width, period):
            pattern |= block << start
        variables.append(pattern)
    memo = {}

    def holds(expression):
        guard.check_time()
        known = memo.get(id(expression))
        if known is not None:
            return known[1]
        kind = type(expression)
        if kind is Const:
            value = every if expression.value else 0
        elif kind is Var:
            value = variables[int(expression.name.split(".")[1])]
        elif kind is Not:
            value = every ^ holds(expression.operand)
        elif kind is And:
            value = holds(expression.left) & holds(expression.right)
        elif kind is Xor:
            value = holds(expression.left) ^ holds(expression.right)
        elif kind is Eq:
            value = every ^ holds(expression.left) ^ holds(expression.right)
        else:  # pragma: no cover - PredicateDomain admits only these nodes
            raise ValueError("unknown predicate node")
        memo[id(expression)] = (expression, value)
        return value

    admitted = holds(domain.predicate)
    words = []
    for word in range(1 << width):
        if word & 0xFFF == 0:
            guard.check_time()
        if admitted >> word & 1:
            words.append(word)
    return words


def _normalize(contract, guard):
    raw = _canonical(contract)
    if len(raw) > _MAX_JSON_BYTES:
        raise ResourceLimitExceeded("shared table JSON bytes", _MAX_JSON_BYTES, len(raw))
    contract = json.loads(raw)
    if (type(contract) is not dict or set(contract) != _FIELDS
            or contract["kind"] != "symq_shared_affine_table_contract"
            or type(contract["schema_version"]) is not int or contract["schema_version"] != 3):
        raise ValueError("closed version-3 shared affine table contract required")
    _integer(contract["width"], 2, 256, "physical width")
    if (contract["bit_order"] != "lsb_first" or contract["records"] != "forgotten"
            or contract["outputs"] != "all_retained"):
        raise ValueError("only lsb_first, forgotten records and all-retained outputs are supported")
    roles = []
    for name in ("address_wires", "target_wires", "clean_wires", "borrowed_wires"):
        wires = contract[name]
        if (type(wires) is not list or any(type(q) is not int or not 0 <= q < contract["width"]
                                          for q in wires)):
            raise ValueError("in-range integer role mappings required")
        roles.extend(wires)
    if len(set(roles)) != len(roles) or set(roles) != set(range(contract["width"])):
        raise ValueError("complete disjoint contract role mapping required")
    table = SharedTable.from_dict(contract["table"])
    domain = PredicateValues.from_dict(contract["address_domain"])
    if domain.domain.data != table.address_bits:
        raise ValueError("predicate and table address widths differ")
    if (type(contract["address_wires"]) is not list
            or len(contract["address_wires"]) != table.address_bits
            or type(contract["target_wires"]) is not list
            or len(contract["target_wires"]) != table.target_bits):
        raise ValueError("table and physical mapping widths differ")
    legal = _admitted(domain.domain, guard)
    if not legal:
        raise ValueError("empty address domain")
    normalized = {k: v for k, v in contract.items() if k != "address_domain"}
    normalized.update(kind="symq_affine_hmr_table_contract", schema_version=2,
                      table=table.rows(guard), legal_addresses=legal)
    guard.check_time()
    return contract, normalized, table, domain, hashlib.sha256(raw).hexdigest()


def verify_shared_table(source, contract, *, budget: Budget | None = None,
                        backend="anf", **bounds):
    """Recheck a wide loader under a nonempty predicate and affine target image.

    A shared table describes, and this function verifies, up to 16 address bits
    (``affine_table.MAX_ADDRESS_BITS``). The predicate is evaluated on every address
    word, while target parameters stay symbolic (up to 256 bits). No target enumeration
    occurs.
    """
    requested = Budget(max_seconds=30.0) if budget is None else budget  # call_budget's default
    budget = call_budget(budget)
    try:
        with VerificationSession(budget) as session:
            _document, normalized, table, _domain, pin = _normalize(contract, session)
            result = verify_affine_table(source, normalized, backend=backend,
                                         budget=session.remaining_budget(), **bounds)
            result.update(shared_contract_sha256=pin, address_domain_nonempty=True,
                          address_domain_size=len(normalized["legal_addresses"]),
                          shared_columns=len(table.columns), target_bits=table.target_bits,
                          normalized_contract_sha256=hashlib.sha256(_canonical(normalized)).hexdigest(),
                          actual_context_preparation_proved=False,
                          source_preparation_scope="declared_support_only")
            session.check_time()
            return result
    except ResourceLimitExceeded as error:
        return {"status": "inconclusive", "obligation": "resources", "witness": None,
                "reason": str(error), "actual_context_preparation_proved": False,
                **resource_report(error, {"max_terms": requested.max_terms,
                                          "max_seconds": requested.max_seconds,
                                          "absolute_deadline": requested.absolute_deadline,
                                          **bounds})}


def _and(expressions):
    if not expressions:
        return Const(True)
    while len(expressions) > 1:
        expressions = [And(expressions[i], expressions[i + 1])
                       if i + 1 < len(expressions) else expressions[i]
                       for i in range(0, len(expressions), 2)]
    return expressions[0]


def _address_expression(expr, wires):
    if isinstance(expr, Const):
        return expr
    if isinstance(expr, Var):
        return Var(f"u.{wires[int(expr.name[2:])]}")
    if isinstance(expr, Not):
        return Not(_address_expression(expr.operand, wires))
    return type(expr)(_address_expression(expr.left, wires), _address_expression(expr.right, wires))


def prove_shared_table_preparation(prefix: Circuit, contract, *, expected_source_sha256: str,
                                   initial_constants=(), initial_assumption=None,
                                   budget: Budget | None = None):
    """Prove actual cut membership at the end of a pinned classical prefix.

    This is a separate all-input Boolean support theorem under the prefix's
    explicit initial domain. It cannot consume a saved success as authority.
    No relationship to an unprovided complete source is inferred.
    """
    budget = call_budget(budget)
    try:
        with VerificationSession(budget) as session:
            document, spec, _table, domain, pin = _normalize(contract, session)
            if type(prefix) is not Circuit or len(prefix.gates) > 200_000 or prefix.width > 256:
                raise ValueError("preparation requires a Circuit with <=200000 gates and <=256 wires")
            source = Program.freeze(prefix)
            if digest(source) != expected_source_sha256:
                raise ValueError("preparation prefix differs from independently pinned source")
            if source.width != spec["width"]:
                raise ValueError("preparation prefix must use the contract's global width")
            roles = [*spec["address_wires"], *spec["target_wires"],
                     *spec["clean_wires"], *spec["borrowed_wires"]]
            if (any(type(q) is not int or not 0 <= q < source.width for q in roles)
                    or len(set(roles)) != len(roles) or set(roles) != set(range(source.width))):
                raise ValueError("complete disjoint contract role mapping required")
            # The same affine-image parser/rank checks as the loader proof.
            space = _space(document["target_space"], spec["target_wires"], session)
            residual = [1 << i for i in range(len(spec["target_wires"]))]
            for pivot, vector in space.pivots:
                coefficient = residual[pivot]
                residual = [value ^ coefficient if vector >> i & 1 else value
                            for i, value in enumerate(residual)]
            equations = []
            for mask in residual:
                if not mask:
                    continue
                terms = [Var(f"u.{q}") for i, q in enumerate(spec["target_wires"]) if mask >> i & 1]
                while len(terms) > 1:
                    terms = [Xor(terms[i], terms[i + 1]) if i + 1 < len(terms) else terms[i]
                             for i in range(0, len(terms), 2)]
                equations.append(Eq(terms[0], Const(bool((mask & space.offset).bit_count() & 1))))
            predicate = _and([_address_expression(domain.domain.predicate, spec["address_wires"]),
                              *equations,
                              *[Not(Var(f"u.{q}")) for q in spec["clean_wires"]]])
            proof = check_substitution(source.circuit(), (len(source.gates), len(source.gates)),
                                       Circuit(source.width),
                                       contract=SubstitutionContract(
                                           initial_constants=initial_constants,
                                           initial_assumption=initial_assumption,
                                           cut_assumption=predicate), budget=session.remaining_budget())
            session.check_time()
            return {"status": proof.outcome, "source_sha256": digest(source),
                    "shared_contract_sha256": pin, "proof": proof.to_dict(),
                    "theorem": "cut_support_from_exact_classical_prefix_under_declared_initial_domain",
                    "external_initial_preparation_proved": False,
                    "complete_source_connection": "not_inferred_from_a_prefix_only"}
    except ResourceLimitExceeded as error:
        return {"status": "inconclusive", "reason": str(error)}
