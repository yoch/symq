"""Research-only deterministic source-bound CNF snapshot for a classical SAT miter.

This is a *formula construction*, not a proof. The existing
build_miter() encoding used by check_sat_equivalence() is frozen and its final
"some required output differs" clause is asserted. The exported DIMACS is
suitable for the bounded positive-hint LRAT checker when a separate untrusted
solver provides a compatible refutation. Source-to-CNF semantics remain
trusted Python and require independent checks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from symq.circuit import Circuit, Gate
from symq.resources import Budget, Guard, ResourceLimitExceeded
from symq.sat.encoding import Contract, Encoder
from symq.sat.miter import build_miter


def _canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


class _BoundedEncoder(Encoder):
    """Opt-in Tseitin encoder whose limits are enforced *during* construction.

    Default SAT/Encoder paths are untouched. This bounds variables, raw clauses,
    and the exact DIMACS bytes of normalized (non-tautological) clauses, not
    Python heap/RSS. Every allocation checks the caller's deadline. Long
    cancellation-only streams are polled separately by encode_circuit.
    """

    def __init__(self, guard: Guard, *, max_variables: int, max_clauses: int,
                 cnf_bytes: int, reported_offset: int = 0) -> None:
        super().__init__()
        self._guard = guard
        self._max_variables = max_variables
        self._max_clauses = max_clauses
        self._cnf_limit = cnf_bytes
        self._normalized_clauses = 0
        self._normalized_bytes = 0
        self._offset = reported_offset
        self._check_bytes(variables=0, clauses=0, body_bytes=0)

    def _check_bytes(self, *, variables: int, clauses: int, body_bytes: int) -> None:
        # The header's length is determined by normalized clause count,
        # not by the raw clause count (which can include tautologies).
        size = body_bytes + len(f"p cnf {variables} {clauses}\n")
        if size > self._cnf_limit:
            # Report the caller's total (source + CNF) cap, as the final check does.
            raise ResourceLimitExceeded("bytes", self._cnf_limit + self._offset,
                                        size + self._offset)

    def new(self) -> int:
        self._guard.check_time()
        if self.next_variable > self._max_variables:
            raise ResourceLimitExceeded(
                "variables", self._max_variables, self.next_variable,
            )
        self._check_bytes(
            variables=self.next_variable, clauses=self._normalized_clauses,
            body_bytes=self._normalized_bytes,
        )
        return super().new()

    def add(self, *literals: int) -> None:
        self._guard.check_time()
        count = len(self.clauses) + 1
        if count > self._max_clauses:
            raise ResourceLimitExceeded("clauses", self._max_clauses, count)

        seen: set[int] = set()
        unique: list[int] = []
        tautology = False
        for lit in literals:
            if type(lit) is not int or lit == 0 or abs(lit) >= self.next_variable:
                raise ValueError("encoder emitted a literal outside its allocated variables")
            if -lit in seen:
                tautology = True
                break
            if lit not in seen:
                seen.add(lit)
                unique.append(lit)

        extra = 0 if tautology else len(" ".join(str(v) for v in unique) + " 0\n")
        next_clauses = self._normalized_clauses + (not tautology)
        next_bytes = self._normalized_bytes + extra
        self._check_bytes(
            variables=self.next_variable - 1,
            clauses=next_clauses, body_bytes=next_bytes,
        )
        super().add(*literals)
        self._normalized_clauses = next_clauses
        self._normalized_bytes = next_bytes


@dataclass(frozen=True)
class MiterCNF:
    dimacs: str
    cnf_sha256: str
    source_sha256: str
    variables: int
    clauses: int
    input_literals: tuple[int, ...]
    theorem: str = "classical_sat_miter_nonidentity_v1"

    def to_manifest(self) -> dict:
        """Metadata is a pin, NOT a proof or independent signature."""
        return {
            "schema_version": 1, "theorem": self.theorem,
            "cnf_sha256": self.cnf_sha256,
            "source_sha256": self.source_sha256,
            "variables": self.variables, "clauses": self.clauses,
            "input_literals": list(self.input_literals),
            "proved": False, "portable_certificate": False,
        }


def export_classical_miter_cnf(
    left: Circuit,
    right: Circuit,
    contract: Contract | None = None,
    *,
    budget: Budget | None = None,
    max_variables: int = 200_000,
    max_clauses: int = 200_000,
    max_bytes: int = 8_000_000,
    max_source_gates: int = 100_000,
) -> MiterCNF:
    """Export the precise closed SAT formula used for an equivalence query.

    The normalized formula is SAT exactly when the *declared classical miter* has a
    counterexample. Allocation and encoding limits are enforced incrementally
    for this opt-in labs path; they are not OS hard time/memory limits. The source-binding SHA is computed from frozen validated
    source and a strict subset of Contract. Arbitrary assumption ASTs are
    deliberately not yet exported, to avoid inventing a second encoding.
    No solver is invoked and no equivalence verdict is returned.
    """
    if type(left) is not Circuit or type(right) is not Circuit:
        raise TypeError("exact reversible Circuits required")
    if contract is not None and type(contract) is not Contract:
        raise TypeError("exact SAT Contract required")
    for name, cap in (("max_variables", max_variables),
                      ("max_clauses", max_clauses),
                      ("max_bytes", max_bytes),
                      ("max_source_gates", max_source_gates)):
        if type(cap) is not int or cap < 1:
            raise ValueError(f"{name} must be a positive integer")
    if budget is not None and (
        type(budget) is not Budget or budget.max_nodes is not None
        or budget.max_terms is not None
    ):
        raise ValueError("CNF exporter does not support ANF term/node budgets")
    guard = Guard(budget)
    if guard.budget.max_nodes is not None or guard.budget.max_terms is not None:
        raise ValueError("CNF exporter cannot enforce node/term budgets")
    guard.check_time()
    if type(left.gates) is not list or type(right.gates) is not list:
        raise ValueError("source gates must be exact lists")
    source_gates = len(left.gates) + len(right.gates)
    if source_gates > max_source_gates:
        raise ResourceLimitExceeded("operations", max_source_gates, source_gates)
    # Gate count alone does not bound the source: one shared wide MCX can be
    # referenced many times. Refuse from O(gates) arithmetic before any
    # validation/to_dict/JSON. Every input wire is a variable, and every qubit
    # serializes as at least two canonical JSON bytes.
    effective_bytes = min(max_bytes, guard.budget.max_bytes) if (
        guard.budget.max_bytes is not None
    ) else max_bytes
    for side in (left, right):
        if type(side.width) is int and side.width > max_variables:
            raise ResourceLimitExceeded("variables", max_variables, side.width)
    qubits = 0
    for index, gate in enumerate(left.gates + right.gates):
        if index % 4096 == 0:
            guard.check_time()
        if type(gate) is Gate and type(gate.qubits) is tuple:
            qubits += len(gate.qubits)
    if 2 * qubits > effective_bytes:
        raise ResourceLimitExceeded("bytes", effective_bytes, 2 * qubits)

    # Pin the exact semantics-facing input snapshot once. Large-source
    # snapshot validation is still cooperative, not OS-preemptible.
    lhs = Circuit(left.width, list(left.gates))
    guard.check_time()
    rhs = Circuit(right.width, list(right.gates))
    guard.check_time()
    value = Contract() if contract is None else Contract(
        input_constants=dict(contract.input_constants),
        observed_outputs=None if contract.observed_outputs is None
        else tuple(contract.observed_outputs),
        restored_wires=tuple(contract.restored_wires),
        output_map=dict(contract.output_map),
        assumption=contract.assumption,
    )
    if lhs.width != rhs.width:
        raise ValueError("miter widths differ")
    value.validate(lhs.width)
    if value.assumption is not None:
        raise ValueError("assumption AST export is not qualified for this pilot")
    source = {
        "theorem": "classical_sat_miter_nonidentity_v1",
        "left": lhs.to_dict(), "right": rhs.to_dict(),
        "contract": {
            "input_constants": [[wire, bit] for wire, bit in sorted(value.input_constants.items())],
            "observed_outputs": (None if value.observed_outputs is None
                                 else list(value.observed_outputs)),
            "restored_wires": list(value.restored_wires),
            "output_map": [[a, b] for a, b in sorted(value.output_map.items())],
            "assumption": None,
        },
    }
    source_bytes = _canonical(source)
    guard.check_time()
    if len(source_bytes) > effective_bytes:
        raise ResourceLimitExceeded("bytes", effective_bytes, len(source_bytes))
    guard.check_time()

    bounded = _BoundedEncoder(
        guard, max_variables=max_variables, max_clauses=max_clauses,
        cnf_bytes=effective_bytes - len(source_bytes),
        reported_offset=len(source_bytes),
    )
    # The shared default SAT encoder remains unchanged. For this opt-in
    # proof exporter, the bounded subclass checks caps as gates emit clauses,
    # while gate checkpoints poll even when algebraic simplification allocates
    # nothing (e.g. repeated X gates).
    miter = build_miter(lhs, rhs, value, encoder=bounded,
                        checkpoint=guard.check_time)
    encoder = miter.encoder
    encoder.add(*miter.difference)
    variables = encoder.next_variable - 1
    raw_clauses = len(encoder.clauses)
    if variables > max_variables:
        raise ResourceLimitExceeded("variables", max_variables, variables)
    if raw_clauses > max_clauses:
        raise ResourceLimitExceeded("clauses", max_clauses, raw_clauses)

    # The production SAT solver accepts duplicated literals and tautological
    # clauses. The portable LRAT parser deliberately refuses both. Normalize
    # without changing satisfiability: remove duplicate occurrences of a
    # literal, and omit any clause containing x and NOT x. This is *not* a
    # byte-identical dump of the solver's internal clause list; a proof must
    # be generated specifically against the resulting pinned formula.
    normalized: list[tuple[int, ...]] = []
    for line in encoder.clauses:
        guard.check_time()
        seen: set[int] = set()
        clause: list[int] = []
        tautology = False
        for literal in line:
            if type(literal) is not int or literal == 0 or abs(literal) > variables:
                raise ValueError("miter emitted a literal outside the variable range")
            if -literal in seen:
                tautology = True
                break
            if literal not in seen:
                seen.add(literal)
                clause.append(literal)
        if not tautology:
            normalized.append(tuple(clause))
    clauses = len(normalized)
    output = [f"p cnf {variables} {clauses}\n"]
    for clause in normalized:
        output.append(" ".join(str(lit) for lit in clause) + " 0\n")
    dimacs = "".join(output)
    size = len(source_bytes) + len(dimacs.encode("ascii"))
    if size > effective_bytes:
        raise ResourceLimitExceeded("bytes", effective_bytes, size)
    guard.check_time()
    return MiterCNF(
        dimacs=dimacs,
        cnf_sha256=hashlib.sha256(dimacs.encode("ascii")).hexdigest(),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        variables=variables, clauses=clauses,
        input_literals=tuple(miter.inputs),
    )
