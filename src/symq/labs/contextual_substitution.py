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

from dataclasses import dataclass, field
from typing import Any

from symq.circuit import Circuit
from symq.errors import SatUnavailable
from symq.experimental.domains import expression_to_dict
from symq.hashing import canonical_sha256
from symq.labs.classical_transcript import (
    Common,
    Program,
    Slot,
    UnprovedSubstitution,
    digest,
    verify_transcript,
)
from symq.labs.rewrite import (
    CostReport,
    VerdictFields,
    Weights,
    _proved,
    call_budget,
    check_receipt,
    check_span,
    cost_report,
    gate_key,
)
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession
from symq.sat import Contract, check_sat_equivalence
from symq.sat.assumptions import And, Const, Eq, Expr, Not, Var, Xor, validate
from symq.sat.composition import Guarantee, Interface, check_composition

__all__ = ["TOTAL_ENGINES", "ObligationReceipt", "SubstitutionContract", "SubstitutionResult",
           "check_substitution", "replay_substitution"]

TOTAL_ENGINES = frozenset({"linear", "packed", "sparse", "zdd", "zdd-native"})
"""Symbolic backends that prove the *total* theorem: the block and its replacement agree on
every input of every wire, so the rewrite is valid in any context. ``packed`` is exact and fast
for bilinear (degree-two) circuits such as GF(2^n) multipliers, and refuses higher degrees."""


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


@dataclass(frozen=True)
class SubstitutionContract:
    """An explicit, non-quantum input and cut-state contract.

    initial_constants and initial_assumption jointly constrain the original
    input domain (they are NOT a proof of prepared quantum ancillas).
    initial_assumption is a closed Boolean expression over x.<wire>; the
    conjunction with the constants must be satisfiable. clean_at_cut demands
    zero on these wires at the actual insertion point; the prefix must prove it.
    cut_assumption is a closed Boolean expression over u.<wire>, and MUST also
    be proved by the actual prefix; it cannot be an unverified caller assertion.

    restored_at_cut are arbitrary borrowed bits which BOTH local blocks must
    restore to their own cut input values. Clean wires must also be restored.
    All final global output bits are observed, without projection or garbage.
    """

    initial_constants: tuple[tuple[int, int], ...] = ()
    clean_at_cut: tuple[int, ...] = ()
    restored_at_cut: tuple[int, ...] = ()
    cut_assumption: Expr | None = None
    # Last, to retain the positional meaning of the original four fields.
    initial_assumption: Expr | None = None

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
        if self.initial_assumption is not None:
            validate(self.initial_assumption, frozenset(f"x.{w}" for w in range(width)))

    def document(self) -> dict[str, Any]:
        document = {
            "initial_constants": [list(pair) for pair in sorted(self.initial_constants)],
            "clean_at_cut": sorted(self.clean_at_cut),
            "restored_at_cut": sorted(self.restored_at_cut),
            "cut_assumption": (None if self.cut_assumption is None
                               else expression_to_dict(self.cut_assumption)),
            "theorem": "classical_contextual_full",
        }
        # Preserve the exact contract hash and version-2 replay form of old
        # requests. Older closed-schema parsers reject a nonempty new field;
        # they must never silently drop an original-input restriction.
        if self.initial_assumption is not None:
            document["initial_assumption"] = expression_to_dict(self.initial_assumption)
        return document


@dataclass(frozen=True)
class ObligationReceipt:
    name: str
    status: str
    witness_kind: str | None = None
    witness: tuple[int, ...] | None = None
    detail: str = ""


@dataclass(frozen=True)
class SubstitutionResult(VerdictFields):
    """Decisive iff ``outcome == "equivalent"``, for the two frozen source hashes.

    ``candidate`` is the frozen rewritten :class:`Program` when, and only when, this result
    was proved in the same call that built it; a receipt reconstructed from JSON or by hand
    cannot carry one, and only the checker can issue an ``equivalent`` outcome (see the trust
    boundary in :mod:`symq.labs.rewrite`).
    """

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
    candidate: Program | None = field(default=None, compare=False, repr=False)
    _token: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        self._check_fields()

    def _candidate_digest(self, candidate: Any) -> str:
        if type(candidate) is not Program:
            raise TypeError("the candidate must be a frozen Program")
        return digest(candidate)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 2, "kind": "symq_contextual_substitution",
                "outcome": self.outcome, "reason": self.reason, "theorem": self.theorem,
                "engine": self.engine, "reference_sha256": self.reference_sha256,
                "candidate_sha256": self.candidate_sha256,
                "contract_sha256": self.contract_sha256, "span": list(self.span),
                "cost": self.cost.to_dict(),
                "obligations": [{"name": o.name, "status": o.status,
                                 "witness_kind": o.witness_kind,
                                 "witness": None if o.witness is None else list(o.witness),
                                 "detail": o.detail} for o in self.obligations]}


def _priced(program: Program) -> list[str]:
    return [gate_key(gate.name, len(gate.qubits)) for gate in program.gates]


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
    weights: Weights | None = None,
    budget: Budget | None = None,
    engine: str = "sat",
) -> SubstitutionResult:
    """Prove a replacement at an exact gate interval, without modifying source.

    ``engine="sat"`` proves the contextual theorem under ``contract`` (module docstring). A
    symbolic engine from :data:`TOTAL_ENGINES` proves the total theorem instead: the contract
    must be empty, and every input of the block is free.

    The replacement has source.width wires in the same global numbering, even
    if it acts on only two of them. This conservative MVP has NO output
    projection, wire mapping, phase or HMR support. Only the classical basis
    input domain specified by contract is proved.

    Rejected local lemmas are not global counterexamples. A time/resource
    failure returns inconclusive, and a missing SAT engine returns unsupported.
    The cooperative deadline starts on entry, including freezing and hashing.
    Malformed inputs and internal verifier inconsistencies raise exceptions.
    """
    # The whole-call deadline starts here, before freezing, hashing and building predicates.
    budget = call_budget(budget)
    if type(source) is not Circuit or type(replacement) is not Circuit:
        raise TypeError("source and replacement must be reversible Circuits")
    original = Program.freeze(source)
    inserted = Program.freeze(replacement)
    if original.width != inserted.width:
        raise ValueError("replacement must use the original global wire width")
    check_span(span, len(original.gates))
    if type(contract) is not SubstitutionContract:
        raise TypeError("an explicit SubstitutionContract is required")
    contract.validate(original.width)
    weights = Weights() if weights is None else weights
    if type(weights) is not Weights:
        raise TypeError("weights must be symq.labs.rewrite.Weights")
    if engine != "sat" and engine not in TOTAL_ENGINES:
        raise ValueError(f"engine must be 'sat' or one of {sorted(TOTAL_ENGINES)}")
    if engine != "sat" and contract != SubstitutionContract():
        raise ValueError("a symbolic engine proves the total theorem: the contract must be empty")
    if engine == "sat" and (budget.max_terms is not None or budget.max_nodes is not None
                            or budget.max_bytes is not None):
        raise ValueError("SAT cannot enforce term/node/byte limits; use max_seconds")

    start, stop = span
    prefix = Circuit(original.width, list(original.gates[:start]))
    local_reference = Circuit(original.width, list(original.gates[start:stop]))
    local_candidate = inserted.circuit()
    candidate = Program(
        original.width, original.gates[:start] + inserted.gates + original.gates[stop:]
    )
    cost = cost_report(_priced(original), _priced(candidate), weights)
    theorem = "classical_contextual_full" if engine == "sat" else "classical_total"
    hash_contract = canonical_sha256({
        "schema_version": 1, "kind": "classical_contextual_substitution",
        "contract": contract.document(), "span": list(span), "engine": engine,
        "theorem": theorem,
    })
    ref_hash, candidate_hash = digest(original), digest(candidate)
    receipts: list[ObligationReceipt] = []

    def result(outcome: str, reason: str) -> SubstitutionResult:
        return SubstitutionResult(
            outcome, reason, ref_hash, candidate_hash, hash_contract,
            span, cost, tuple(receipts), theorem, engine,
        )

    def proved(reason: str) -> SubstitutionResult:
        return _proved(SubstitutionResult, candidate, reason=reason,
                       reference_sha256=ref_hash, candidate_sha256=candidate_hash,
                       contract_sha256=hash_contract, span=span, cost=cost,
                       obligations=tuple(receipts), theorem=theorem, engine=engine)

    if engine != "sat":
        from symq.backends import BACKENDS

        if engine not in BACKENDS:
            return result("unsupported", f"the {engine!r} engine is not available here")
        steps = (Common(original.gates[:start]),
                 Slot(Program(original.width, original.gates[start:stop]), inserted,
                      tuple(range(original.width))),
                 Common(original.gates[stop:]))
        try:
            with VerificationSession(budget) as session:
                verify_transcript(original.circuit(), candidate.circuit(), steps,
                                  reference_sha256=ref_hash, candidate_sha256=candidate_hash,
                                  backend=engine, budget=session.remaining_budget(),
                                  max_expanded_gates=max(200_000, 2 * len(original.gates),
                                                         2 * len(candidate.gates)))
                receipts.append(ObligationReceipt("block_equality", "passed"))
                session.check_time()
                return proved("the block and its replacement agree on every input")
        except UnprovedSubstitution as exc:
            receipts.append(ObligationReceipt(
                "block_equality", "failed", None if exc.witness is None else "local_input",
                None if exc.witness is None else (exc.witness,), str(exc)))
            return result("not_proved", str(exc))
        except ResourceLimitExceeded as exc:
            if exc.resource == "degree":
                return result("unsupported", f"{engine} cannot represent this block: {exc}")
            return result("inconclusive", str(exc))

    # The predicate at the actual cut must be *proved*, not assumed.
    domain = _conjoin([
        *[_value("x", wire, bit) for wire, bit in contract.initial_constants],
        *([contract.initial_assumption] if contract.initial_assumption is not None else []),
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
            return proved("all contextual classical and restoration obligations proved")
    except SatUnavailable as exc:
        return result("unsupported", str(exc))
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))


def replay_substitution(
    receipt: SubstitutionResult,
    source: Circuit,
    span: tuple[int, int],
    replacement: Circuit,
    *,
    contract: SubstitutionContract,
    budget: Budget | None = None,
) -> SubstitutionResult:
    """Recompute a pinned contextual proof; a stored verdict is never authority.

    This reruns the checker from the supplied source, replacement and contract with the
    receipt's weights, and raises :class:`symq.labs.rewrite.ReceiptMismatch` if the frozen
    source, candidate, contract, span or cost differ from the receipt, or if a decisive fresh
    result differs from the receipt on any field. Only the fresh result can be acted on: an
    ``inconclusive`` or ``unsupported`` replay reverifies nothing, and only a fresh proof
    carries the applicable candidate.
    """
    if type(receipt) is not SubstitutionResult:
        raise TypeError("a typed SubstitutionResult receipt is required")
    if receipt.engine != "sat" and receipt.engine not in TOTAL_ENGINES:
        raise ValueError("the receipt requests an unsupported proof engine")
    fresh = check_substitution(source, span, replacement, contract=contract,
                               weights=receipt.cost.weights, budget=budget,
                               engine=receipt.engine)
    check_receipt(receipt, fresh, ("reference_sha256", "candidate_sha256", "contract_sha256",
                                   "span", "cost"))
    return fresh
