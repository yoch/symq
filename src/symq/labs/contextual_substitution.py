"""Bounded, contextual reversible-Boolean substitutions (research API).

A proof concerns the frozen source stream and its explicitly restricted *basis*
input domain. It does NOT establish a quantum coherent-channel theorem.

The existing assume/guarantee engine establishes:
  (0) The declared original-input domain is nonempty.
  (1) The actual prefix establishes the entire cut predicate.
  (2) The cut relation entails the local suffix precondition.
  (3) The original and replacement blocks agree on every cut state satisfying
      that predicate, on ALL wires.

The unchanged common suffix then preserves equality by ordinary composition.
Optional clean/borrowed restoration is proved separately on both blocks.
A failed local lemma does not necessarily witness a difference at a reachable
global input, so we deliberately return "not_proved", never "different".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from symq.circuit import Circuit
from symq.errors import SatUnavailable
from symq.hashing import canonical_sha256
from symq.labs.classical_transcript import Program, digest
from symq.resources import Budget, Guard, ResourceLimitExceeded, VerificationSession
from symq.sat import Contract, check_sat_equivalence
from symq.sat.assumptions import And, Const, Eq, Expr, Not, Var, Xor, validate
from symq.sat.composition import Guarantee, Interface, check_composition


def _conjoin(expressions: list[Expr]) -> Expr:
    """Balanced conjunction: SAT assumptions have a strict maximum tree depth."""
    if not expressions:
        return Const(True)
    level = expressions
    while len(level) > 1:
        level = [
            And(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
            for i in range(0, len(level), 2)
        ]
    return level[0]


def _equals(left: str, right: str, width: int) -> Expr:
    return _conjoin([
        Eq(Var(f"{left}.{wire}"), Var(f"{right}.{wire}"))
        for wire in range(width)
    ])


def _value(prefix: str, wire: int, bit: int) -> Expr:
    term = Var(f"{prefix}.{wire}")
    return term if bit else Not(term)


def _rename(expression: Expr, from_prefix: str, to_prefix: str) -> Expr:
    if isinstance(expression, Const):
        return expression
    if isinstance(expression, Var):
        if not expression.name.startswith(from_prefix):
            raise ValueError("cut expression has an undeclared variable")
        return Var(to_prefix + expression.name[len(from_prefix):])
    if isinstance(expression, Not):
        return Not(_rename(expression.operand, from_prefix, to_prefix))
    if isinstance(expression, (And, Xor, Eq)):
        return type(expression)(
            _rename(expression.left, from_prefix, to_prefix),
            _rename(expression.right, from_prefix, to_prefix),
        )
    raise TypeError("unsupported Boolean expression")


def _expression_data(expression: Expr | None) -> Any:
    if expression is None:
        return None
    if isinstance(expression, Const):
        return ["const", expression.value]
    if isinstance(expression, Var):
        return ["var", expression.name]
    if isinstance(expression, Not):
        return ["not", _expression_data(expression.operand)]
    if isinstance(expression, (And, Xor, Eq)):
        return [
            type(expression).__name__.lower(),
            _expression_data(expression.left),
            _expression_data(expression.right),
        ]
    raise TypeError("unsupported Boolean expression")


@dataclass(frozen=True)
class SubstitutionContract:
    """An explicit, non-quantum input and cut-state contract.

    initial_constants constrain the original input domain (they are NOT a proof
    of prepared quantum ancillas). clean_at_cut demands zero on these wires at
    the actual insertion point; the prefix must prove it. cut_assumption is a
    closed Boolean expression over u.<wire>, and MUST also be proved by the
    actual prefix; it cannot be an unverified caller assertion.

    restored_at_cut are arbitrary borrowed bits which BOTH local blocks must
    restore to their own cut input values. Clean wires must also be restored.
    All final global output bits are observed, without projection or garbage.
    """

    initial_constants: tuple[tuple[int, int], ...] = ()
    clean_at_cut: tuple[int, ...] = ()
    restored_at_cut: tuple[int, ...] = ()
    cut_assumption: Expr | None = None

    def validate(self, width: int) -> None:
        if type(self.initial_constants) is not tuple:
            raise TypeError("initial_constants must be an immutable tuple of pairs")
        seen: set[int] = set()
        for pair in self.initial_constants:
            if (type(pair) is not tuple or len(pair) != 2
                    or type(pair[0]) is not int or not 0 <= pair[0] < width
                    or type(pair[1]) is not int or pair[1] not in (0, 1)):
                raise ValueError("initial constants need unique in-range (wire, 0/1) pairs")
            if pair[0] in seen:
                raise ValueError("duplicate initial constant wire")
            seen.add(pair[0])
        for name, wires in (
            ("clean_at_cut", self.clean_at_cut),
            ("restored_at_cut", self.restored_at_cut),
        ):
            if (type(wires) is not tuple or len(set(wires)) != len(wires)
                    or any(type(w) is not int or not 0 <= w < width for w in wires)):
                raise ValueError(f"{name} must have distinct in-range integer wires")
        if set(self.clean_at_cut) & set(self.restored_at_cut):
            raise ValueError("a cut wire cannot be both clean and borrowed")
        if self.cut_assumption is not None:
            validate(self.cut_assumption, frozenset(f"u.{w}" for w in range(width)))

    def document(self) -> dict[str, Any]:
        return {
            "initial_constants": [list(pair) for pair in sorted(self.initial_constants)],
            "clean_at_cut": sorted(self.clean_at_cut),
            "restored_at_cut": sorted(self.restored_at_cut),
            "cut_assumption": _expression_data(self.cut_assumption),
            "theorem": "classical_contextual_full",
        }


@dataclass(frozen=True)
class GateWeights:
    """Declared integer per-gate proxy, NOT T-count, depth or hardware cost."""

    x: int = 1
    cx: int = 1
    ccx: int = 1
    mcx: int = 1

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in (self.x, self.cx, self.ccx, self.mcx)):
            raise ValueError("every gate weight must be a nonnegative integer")

    def weight(self, name: str) -> int:
        return int(getattr(self, name))


@dataclass(frozen=True)
class CostReport:
    original_gates: int
    candidate_gates: int
    original_counts: tuple[tuple[str, int], ...]
    candidate_counts: tuple[tuple[str, int], ...]
    original_weighted: int
    candidate_weighted: int
    weighted_delta: int
    weights: GateWeights


@dataclass(frozen=True)
class ObligationReceipt:
    name: str
    status: str
    witness_kind: str | None = None
    witness: tuple[int, ...] | None = None
    detail: str = ""


@dataclass(frozen=True)
class SubstitutionResult:
    """Decisive iff outcome == equivalent, for the two frozen source hashes."""

    outcome: str
    reason: str
    reference_sha256: str
    candidate_sha256: str
    contract_sha256: str
    span: tuple[int, int]
    cost: CostReport
    obligations: tuple[ObligationReceipt, ...]
    theorem: str = "classical_contextual_full"
    engine: str = "sat"

    @property
    def equivalent(self) -> bool:
        return self.outcome == "equivalent"

    @property
    def certified(self) -> bool:
        return self.equivalent

    @property
    def different(self) -> bool:
        # A local cut-state witness need not be reachable at the global input.
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, **asdict(self)}


def _cost(original: Program, candidate: Program, weights: GateWeights) -> CostReport:
    def counts(p: Program) -> tuple[tuple[str, int], ...]:
        names = {g.name for g in p.gates}
        return tuple((name, sum(g.name == name for g in p.gates)) for name in sorted(names))

    before = sum(weights.weight(g.name) for g in original.gates)
    after = sum(weights.weight(g.name) for g in candidate.gates)
    return CostReport(
        len(original.gates), len(candidate.gates),
        counts(original), counts(candidate), before, after, after - before, weights,
    )


def _bits(witness: dict[str, int], prefix: str, width: int) -> int:
    return sum((1 << wire) for wire in range(width) if witness.get(f"{prefix}{wire}"))


def _obligation_record(obligation: Any, width: int) -> ObligationReceipt:
    answer = obligation.satisfiable
    status = ("unknown" if answer is None else
              "passed" if (answer is True) == (obligation.wanted == "sat") else "failed")
    kind = None
    values = None
    if obligation.witness:
        if obligation.name in {"domain", "prefix"}:
            kind = "input"
            values = (_bits(obligation.witness, "x.", width),)
        elif obligation.name in {"interface", "suffix"}:
            kind = "cut"
            values = (
                _bits(obligation.witness, "u.", width),
                _bits(obligation.witness, "v.", width),
            )
    return ObligationReceipt(obligation.name, status, kind, values, obligation.detail)


def check_substitution(
    source: Circuit,
    span: tuple[int, int],
    replacement: Circuit,
    *,
    contract: SubstitutionContract,
    weights: GateWeights | None = None,
    budget: Budget | None = None,
) -> SubstitutionResult:
    """Prove a replacement at an exact gate interval, without modifying source.

    The replacement has source.width wires in the same global numbering, even
    if it acts on only two of them. This conservative MVP has NO output
    projection, wire mapping, phase or HMR support. Only the classical basis
    input domain specified by contract is proved.

    Rejected local lemmas are not global counterexamples. A time/resource
    failure returns inconclusive, and a missing SAT engine returns unsupported.
    The cooperative deadline starts on entry, including freezing and hashing.
    Malformed inputs and internal verifier inconsistencies raise exceptions.
    """
    # Start the actual call deadline BEFORE freezing, hashing, cost accounting,
    # contract validation or constructing symbolic predicates. The absolute
    # deadline is deliberately not restarted when the SAT engine is entered.
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be Budget or None")
    requested = budget if budget is not None else Budget(max_seconds=30)
    budget = Budget(requested.max_terms, requested.max_nodes,
                    absolute_deadline=Guard(requested).deadline,
                    max_bytes=requested.max_bytes)
    if type(source) is not Circuit or type(replacement) is not Circuit:
        raise TypeError("source and replacement must be reversible Circuits")
    original = Program.freeze(source)
    inserted = Program.freeze(replacement)
    if original.width != inserted.width:
        raise ValueError("replacement must use the original global wire width")
    if (type(span) is not tuple or len(span) != 2
            or any(type(v) is not int for v in span)
            or not 0 <= span[0] <= span[1] <= len(original.gates)):
        raise ValueError("span must be a valid [start, stop) gate interval")
    if type(contract) is not SubstitutionContract:
        raise TypeError("an explicit SubstitutionContract is required")
    contract.validate(original.width)
    if weights is None:
        weights = GateWeights()
    if type(weights) is not GateWeights:
        raise TypeError("weights must be GateWeights")
    if budget.max_terms is not None or budget.max_nodes is not None or budget.max_bytes is not None:
        raise ValueError("SAT cannot enforce term/node/byte limits; use max_seconds")

    start, stop = span
    prefix = Circuit(original.width, list(original.gates[:start]))
    local_reference = Circuit(original.width, list(original.gates[start:stop]))
    local_candidate = inserted.circuit()
    candidate = Program(
        original.width, original.gates[:start] + inserted.gates + original.gates[stop:]
    )
    cost = _cost(original, candidate, weights)
    hash_contract = canonical_sha256({
        "schema_version": 1, "kind": "classical_contextual_substitution",
        "contract": contract.document(), "span": list(span),
    })
    ref_hash, candidate_hash = digest(original), digest(candidate)
    receipts: list[ObligationReceipt] = []

    def result(outcome: str, reason: str) -> SubstitutionResult:
        return SubstitutionResult(
            outcome, reason, ref_hash, candidate_hash, hash_contract,
            span, cost, tuple(receipts),
        )

    # The predicate at the actual cut must be *proved*, not assumed.
    domain = _conjoin([
        _value("x", wire, bit) for wire, bit in contract.initial_constants
    ])
    cut = _conjoin([
        *[_value("u", wire, 0) for wire in contract.clean_at_cut],
        *([contract.cut_assumption] if contract.cut_assumption is not None else []),
    ])
    relation = _conjoin([_equals("u", "v", original.width), cut])
    interface = Interface(original.width, domain, relation)
    guarantee = Guarantee(original.width, cut, _equals("s", "t", original.width))

    try:
        with VerificationSession(budget) as session:
            proof = check_composition(
                prefix_left=prefix, prefix_right=prefix,
                suffix_left=local_reference, suffix_right=local_candidate,
                interface=interface, guarantee=guarantee,
                budget=session.remaining_budget(),
            )
            receipts.extend(_obligation_record(o, original.width) for o in proof.obligations)
            if not proof.accepted:
                if any(o.status == "unknown" for o in receipts):
                    return result("inconclusive", "a mandatory SAT obligation was undecided")
                if any(o.status == "failed" and o.name in {"domain", "prefix", "interface"}
                       for o in receipts):
                    return result("precondition_failed",
                                  "the legal input or cut predicate was not established")
                return result("not_proved",
                              "the local all-output lemma does not hold under the cut predicate")

            # Local restoration is not implied by equivalence of two dirty outputs.
            restored = contract.clean_at_cut + contract.restored_at_cut
            if restored:
                local_assumption = _rename(cut, "u.", "x.")
                restoration = Contract(
                    assumption=local_assumption,
                    observed_outputs=(),
                    restored_wires=restored,
                )
                for name, block in (
                    ("restore_original", local_reference),
                    ("restore_candidate", local_candidate),
                ):
                    decision = check_sat_equivalence(
                        block, block, restoration, budget=session.remaining_budget()
                    )
                    status = {
                        "equivalent": "passed",
                        "different": "failed",
                        "inconclusive": "unknown",
                    }[decision.outcome]
                    receipts.append(ObligationReceipt(
                        name, status, "cut" if decision.witness is not None else None,
                        (decision.witness,) if decision.witness is not None else None,
                        decision.detail,
                    ))
                    if status == "unknown":
                        return result("inconclusive", f"{name} did not finish")
                    if status == "failed":
                        return result("not_proved",
                                      f"{name}: the block did not restore all declared wires")
            session.check_time()
            return result("equivalent",
                          "all contextual classical and restoration obligations proved")
    except SatUnavailable as exc:
        return result("unsupported", str(exc))
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))
