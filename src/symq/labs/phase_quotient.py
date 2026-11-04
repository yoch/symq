"""Exact, opt-in phase identities modulo proven Boolean prefix relations.

The algebraic certificate is conditional: delta-c = sum(q_j * lift(b_j)).
``check_prefix_phase`` additionally proves b_j(prefix(x)) = 0 for every legal
input. Its theorem concerns the supplied phase polynomial, not equivalence
of unspecified circuits, output restoration, or a controlled replacement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeGuard

from symq.anf import ANF
from symq.circuit import Circuit
from symq.errors import InternalInconsistency
from symq.hashing import canonical_sha256
from symq.resources import Budget, Guard, session_scoped

from .dyadic_phase import Poly, _add, _boolean_product, _multiply, lift_anf

Terms = tuple[tuple[int, int], ...]
_KIND = "symq_phase_quotient_certificate"
_THEOREM = "dyadic_phase_constant_on_prefix_image"
_MAX_WIDTH = 256
_MAX_K = 64
# Like the sibling labs modules, an omitted budget is bounded, not unlimited.
_DEFAULT_BUDGET = Budget(max_terms=100_000, max_seconds=10.0)
_MISMATCH = "prefix phase receipt mismatch"


def _exact_keys(value: object, keys: frozenset[str]) -> TypeGuard[dict[str, Any]]:
    """Exact top-level key set of an untrusted dict, in O(len(keys)).

    Length first, then only the expected keys: never copy or hash an arbitrarily
    large untrusted key set before refusing it.
    """
    return (type(value) is dict and len(value) == len(keys)
            and all(key in value for key in keys))


@dataclass(frozen=True)
class PhaseQuotientCertificate:
    """Untrusted data; only a fresh check establishes an identity.

    ``delta`` and each multiplier are sorted (mask, coefficient) tuples,
    with distinct masks and nonzero coefficients in [1, 2**k). Invariants
    are Boolean ANFs whose required value is zero, on the *cut wires*.
    """

    width: int
    k: int
    delta: Terms
    invariants: tuple[ANF, ...]
    multipliers: tuple[Terms, ...]
    constant: int = 0


@dataclass(frozen=True)
class PrefixPhaseResult:
    """A source-bound phase statement; never a rewrite authorization."""

    outcome: Literal["proved", "not_proved"]
    reason: str
    width: int
    k: int
    constant: int | None
    prefix_sha256: str
    certificate_sha256: str
    initial_constants: tuple[tuple[int, int], ...]
    violating_invariant: int | None = None
    witness: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "kind": "symq_prefix_phase_result",
            "theorem": _THEOREM, "candidate_authorized": False,
            "outcome": self.outcome, "reason": self.reason,
            "width": self.width, "k": self.k, "constant": self.constant,
            "prefix_sha256": self.prefix_sha256,
            "certificate_sha256": self.certificate_sha256,
            "initial_constants": [list(pair) for pair in self.initial_constants],
            "violating_invariant": self.violating_invariant,
            "witness": self.witness,
        }


# Derived from the result itself, so a new or renamed field cannot drift from replay.
_RECEIPT_KEYS = frozenset(PrefixPhaseResult("not_proved", "", 1, 1, None, "", "", ()).to_dict())


def _guard(budget: Budget | None) -> Guard:
    guard = Guard(_DEFAULT_BUDGET if budget is None else budget)
    guard.check_time()
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError("phase quotient supports max_terms and time, not max_nodes/max_bytes")
    return guard


def _terms(value: object, width: int, modulus: int, guard: Guard) -> Terms:
    if type(value) is not tuple:
        raise ValueError("polynomial terms must be an immutable sorted tuple")
    guard.check_terms(len(value))
    previous = -1
    out: list[tuple[int, int]] = []
    for item in value:
        guard.check_time()
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("each polynomial term must be a (mask, coefficient) tuple")
        mask, coefficient = item
        if (type(mask) is not int or mask < 0 or mask.bit_length() > width
                or mask <= previous):
            raise ValueError("monomial masks must be distinct, increasing and fit width")
        if type(coefficient) is not int or not 0 < coefficient < modulus:
            raise ValueError("coefficients must be nonzero canonical integers modulo 2**k")
        previous = mask
        out.append((mask, coefficient))
    return tuple(out)


def _freeze_certificate(value: PhaseQuotientCertificate, guard: Guard) -> PhaseQuotientCertificate:
    if type(value) is not PhaseQuotientCertificate:
        raise TypeError("PhaseQuotientCertificate required")
    if type(value.width) is not int or not 1 <= value.width <= _MAX_WIDTH:
        raise ValueError(f"width must be an integer in [1, {_MAX_WIDTH}]")
    if type(value.k) is not int or not 1 <= value.k <= _MAX_K:
        raise ValueError(f"k must be an integer in [1, {_MAX_K}]")
    modulus = 1 << value.k
    if type(value.constant) is not int or not 0 <= value.constant < modulus:
        raise ValueError("constant must be a canonical integer modulo 2**k")
    if (type(value.invariants) is not tuple or type(value.multipliers) is not tuple
            or len(value.invariants) != len(value.multipliers)):
        raise ValueError("one immutable multiplier tuple is required per invariant")
    # Charge even empty relations; a tuple of many zeros is not a free input.
    count = len(value.invariants)
    guard.check_terms(count)
    delta = _terms(value.delta, value.width, modulus, guard)
    count += len(delta)
    guard.check_terms(count)
    invariants: list[ANF] = []
    multipliers: list[Terms] = []
    for invariant, multiplier in zip(value.invariants, value.multipliers):
        guard.check_time()
        if type(invariant) is not ANF or type(invariant.terms) is not frozenset:
            raise ValueError("invariants must be immutable Boolean ANFs")
        count += len(invariant.terms)
        guard.check_terms(count)
        masks = []
        for mask in invariant.terms:
            guard.check_time()
            if type(mask) is not int or mask < 0 or mask.bit_length() > value.width:
                raise ValueError("invariant monomials must fit width")
            masks.append(mask)
        invariants.append(ANF(frozenset(masks)))
        terms = _terms(multiplier, value.width, modulus, guard)
        count += len(terms)
        guard.check_terms(count)
        multipliers.append(terms)
    guard.check_time()
    return PhaseQuotientCertificate(value.width, value.k, delta, tuple(invariants),
                                    tuple(multipliers), value.constant)


def _certificate_dict(value: PhaseQuotientCertificate) -> dict[str, Any]:
    return {
        "schema_version": 1, "kind": _KIND, "width": value.width, "k": value.k,
        "constant": value.constant, "delta": [list(term) for term in value.delta],
        "invariants": [sorted(p.terms) for p in value.invariants],
        "multipliers": [[list(term) for term in p] for p in value.multipliers],
    }


@session_scoped
def certificate_to_dict(value: PhaseQuotientCertificate,
                        budget: Budget | None = None) -> dict[str, Any]:
    """Encode validated data, without asserting that its identity holds."""
    guard = _guard(budget)
    result = _certificate_dict(_freeze_certificate(value, guard))
    guard.check_time()
    return result


@session_scoped
def certificate_from_dict(value: object, budget: Budget | None = None) -> PhaseQuotientCertificate:
    """Strict versioned JSON object parser; a parsed certificate remains unproved."""
    guard = _guard(budget)
    keys = frozenset({"schema_version", "kind", "width", "k", "constant", "delta",
                      "invariants", "multipliers"})
    if not _exact_keys(value, keys):
        raise ValueError("invalid phase quotient certificate fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported phase quotient certificate version")
    if value["kind"] != _KIND:
        raise ValueError("not a phase quotient certificate")

    def polynomial(raw: object) -> Terms:
        if type(raw) is not list:
            raise ValueError("JSON polynomials must be arrays")
        guard.check_terms(len(raw))
        out = []
        for item in raw:
            guard.check_time()
            if type(item) is not list or len(item) != 2:
                raise ValueError("JSON polynomial terms must be two-element arrays")
            out.append((item[0], item[1]))
        return tuple(out)

    raw_invariants, raw_multipliers = value["invariants"], value["multipliers"]
    if type(raw_invariants) is not list or type(raw_multipliers) is not list:
        raise ValueError("JSON invariants and multipliers must be arrays")
    if len(raw_invariants) != len(raw_multipliers):
        raise ValueError("one multiplier is required per invariant")
    count = len(raw_invariants)
    guard.check_terms(count)
    invariants = []
    multipliers = []
    delta = polynomial(value["delta"])
    count += len(delta)
    guard.check_terms(count)
    for raw, multiplier in zip(raw_invariants, raw_multipliers):
        guard.check_time()
        if type(raw) is not list:
            raise ValueError("JSON invariant terms must be arrays")
        count += len(raw)
        guard.check_terms(count)
        previous = -1
        for mask in raw:
            guard.check_time()
            if type(mask) is not int or mask < 0 or mask <= previous:
                raise ValueError("JSON invariant masks must be increasing nonnegative integers")
            previous = mask
        invariants.append(ANF(frozenset(raw)))
        terms = polynomial(multiplier)
        count += len(terms)
        guard.check_terms(count)
        multipliers.append(terms)
    cert = PhaseQuotientCertificate(value["width"], value["k"], delta, tuple(invariants),
                                    tuple(multipliers), value["constant"])
    return _freeze_certificate(cert, guard)


def _identity(cert: PhaseQuotientCertificate, guard: Guard) -> bool:
    left = _add(dict(cert.delta), {0: cert.constant}, -1, k=cert.k, guard=guard)
    right: Poly = {}
    for relation, multiplier in zip(cert.invariants, cert.multipliers):
        guard.check_time()
        lifted = lift_anf(relation, guard, k=cert.k)
        product = _multiply(lifted, dict(multiplier), guard, k=cert.k)
        right = _add(right, product, k=cert.k, guard=guard)
    guard.check_time()
    return left == right


@session_scoped
def verify_phase_identity(certificate: PhaseQuotientCertificate,
                          budget: Budget | None = None) -> bool:
    """Check only delta-c = sum(q_j*lift(b_j)); assumptions are NOT established.

    False means this certificate failed, not that the intended phases differ.
    ResourceLimitExceeded means no answer, including during intermediate lifts.
    """
    guard = _guard(budget)
    return _identity(_freeze_certificate(certificate, guard), guard)


def _freeze_prefix(prefix: Circuit, width: int, guard: Guard) -> Circuit:
    if type(prefix) is not Circuit or type(prefix.width) is not int or prefix.width != width:
        raise ValueError("a reversible Circuit matching the certificate width is required")
    if type(prefix.gates) is not list:
        raise ValueError("prefix gate stream must be a list")
    try:
        # Reconstruct even frozen objects: validation must not trust an old IR check.
        frozen = prefix.snapshot(check=guard.check_time)
    except TypeError as error:
        raise ValueError(
            f"prefix gate names and wires must be plain strings and tuples: {error}") from error
    guard.check_time()
    return frozen


def _constants(value: object, width: int, guard: Guard) -> tuple[tuple[int, int], ...]:
    if type(value) is not tuple:
        raise ValueError("initial_constants must be an immutable tuple")
    out: dict[int, int] = {}
    for pair in value:
        guard.check_time()
        if type(pair) is not tuple or len(pair) != 2:
            raise ValueError("initial constants must be (wire, bit) pairs")
        wire, bit = pair
        if (type(wire) is not int or not 0 <= wire < width or wire in out
                or type(bit) is not int or bit not in (0, 1)):
            raise ValueError("initial constants need distinct wires and exact bits")
        out[wire] = bit
    return tuple(sorted(out.items()))


def _prefix_state(prefix: Circuit, constants: tuple[tuple[int, int], ...],
                  guard: Guard) -> tuple[ANF, ...]:
    fixed = dict(constants)
    guard.check_terms(prefix.width)
    state = [ANF.constant(fixed[q]) if q in fixed else ANF.variable(q)
             for q in range(prefix.width)]
    total = sum(len(p.terms) for p in state)
    for gate in prefix.gates:
        guard.check_time()
        product = ANF.constant(1)
        for q in gate.controls:
            product = _boolean_product(product, state[q], guard)
        before = state[gate.target]
        state[gate.target] = before ^ product
        # Running total: one O(1) update per gate instead of rescanning the state.
        total += len(state[gate.target].terms) - len(before.terms)
        guard.check_terms(total)
    guard.check_time()
    return tuple(state)


def _substitute(relation: ANF, state: tuple[ANF, ...], guard: Guard) -> ANF:
    result = ANF()
    for mask in sorted(relation.terms):
        guard.check_time()
        product = ANF.constant(1)
        while mask:
            bit = mask & -mask
            product = _boolean_product(product, state[bit.bit_length() - 1], guard)
            mask ^= bit
        result = result ^ product
        guard.check_terms(len(result.terms))
    guard.check_time()
    return result


def _digest(value: object, guard: Guard) -> str:
    guard.check_time()
    result = canonical_sha256(value)
    guard.check_time()
    return result


def _validate_receipt(receipt: object, guard: Guard) -> dict[str, Any]:
    """Bounded, type-exact shape check of an untrusted receipt, before any proof work."""
    if not _exact_keys(receipt, _RECEIPT_KEYS):
        raise ValueError("a serialized prefix phase receipt is required")
    guard.check_time()
    for key, bits in (("schema_version", 8), ("width", 16), ("k", 8)):
        value = receipt[key]
        if type(value) is not int or value < 0 or value.bit_length() > bits:
            raise ValueError(f"{_MISMATCH}: field {key} must be a small nonnegative integer")
    for key in ("kind", "theorem", "outcome", "reason", "prefix_sha256", "certificate_sha256"):
        if type(receipt[key]) is not str or len(receipt[key]) > 4096:
            raise ValueError(f"{_MISMATCH}: field {key} must be a bounded string")
    if type(receipt["candidate_authorized"]) is not bool:
        raise ValueError(f"{_MISMATCH}: field candidate_authorized must be a boolean")
    # Bounds: a constant is below 2**k <= 2**_MAX_K, a witness below 2**width <= 2**_MAX_WIDTH,
    # and an invariant index fits a machine word; larger values cannot match a fresh result.
    for key, bits in (("constant", _MAX_K), ("violating_invariant", 63), ("witness", _MAX_WIDTH)):
        value = receipt[key]
        if value is not None and (type(value) is not int or value < 0
                                  or value.bit_length() > bits):
            raise ValueError(f"{_MISMATCH}: field {key} must be a bounded integer or null")
    pairs = receipt["initial_constants"]
    if type(pairs) is not list or len(pairs) > _MAX_WIDTH:
        raise ValueError(f"{_MISMATCH}: initial_constants must be a bounded array")
    for pair in pairs:
        guard.check_time()
        if (type(pair) is not list or len(pair) != 2
                or any(type(item) is not int for item in pair)
                or not 0 <= pair[0] < _MAX_WIDTH or pair[1] not in (0, 1)):
            raise ValueError(f"{_MISMATCH}: initial constants must be bounded [wire, bit] pairs")
    guard.check_time()
    return receipt


@session_scoped
def check_prefix_phase(prefix: Circuit, certificate: PhaseQuotientCertificate,
                       budget: Budget | None = None, *,
                       initial_constants: tuple[tuple[int, int], ...] = ()) -> PrefixPhaseResult:
    """Prove the supplied phase equals c on the image of a reversible prefix.

    Unspecified input wires remain arbitrary, including borrowed ancillas.
    Distinct fixed input bits define a nonempty basis support. Exact ANF
    substitution establishes each relation on that support, hence also on
    its coherent span. The result does not compare output permutations.
    """
    guard = _guard(budget)
    cert = _freeze_certificate(certificate, guard)
    source = _freeze_prefix(prefix, cert.width, guard)
    constants = _constants(initial_constants, cert.width, guard)
    prefix_hash = _digest(source.to_dict(), guard)
    certificate_hash = _digest(_certificate_dict(cert), guard)

    def result(outcome: Literal["proved", "not_proved"], reason: str,
               index: int | None = None, witness: int | None = None) -> PrefixPhaseResult:
        guard.check_time()
        return PrefixPhaseResult(outcome, reason, cert.width, cert.k,
                                 cert.constant if outcome == "proved" else None,
                                 prefix_hash, certificate_hash, constants, index, witness)

    if not _identity(cert, guard):
        return result("not_proved", "polynomial identity mismatch")
    state = _prefix_state(source, constants, guard)
    fixed_ones = sum(1 << wire for wire, bit in constants if bit)
    for index, invariant in enumerate(cert.invariants):
        difference = _substitute(invariant, state, guard)
        if difference.terms:
            witness = min(difference.terms, key=lambda mask: (mask.bit_count(), mask)) | fixed_ones
            # Per-gate checks keep the scalar witness replay cooperative on long prefixes.
            cut = source.run(witness, check=guard.check_time)
            guard.check_time()
            observed = 0
            for mask in invariant.terms:
                guard.check_time()
                observed ^= int(cut & mask == mask)
            if (not observed or any((witness >> q & 1) != v for q, v in constants)):
                raise InternalInconsistency("prefix invariant witness failed scalar replay")
            return result("not_proved", "invariant not established on prefix image", index, witness)
    return result("proved", "exact identity and all prefix invariants established")


@session_scoped
def replay_prefix_phase(prefix: Circuit, certificate: PhaseQuotientCertificate,
                        receipt: object, budget: Budget | None = None, *,
                        initial_constants: tuple[tuple[int, int], ...] = ()) -> PrefixPhaseResult:
    """Recompute every obligation and compare the complete, untrusted receipt.

    Even a semantically equivalent changed prefix has a different identity.
    No signature or producer seal is trusted as a proof.
    """
    guard = _guard(budget)
    expected = _validate_receipt(receipt, guard)
    fresh = check_prefix_phase(prefix, certificate, guard.inherited_budget(),
                               initial_constants=initial_constants)
    guard.check_time()
    # The shape check above makes plain equality exact: no bool/int or tuple/list aliasing.
    if fresh.to_dict() != expected:
        raise ValueError(_MISMATCH)
    guard.check_time()
    return fresh
