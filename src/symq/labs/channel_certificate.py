"""One-copy functional certificates for full sign/HMR channels (research).

All inputs are free data bits with zero-initialized ancillas, all quantum
outputs are retained and all measurement outcomes are forgotten. A certificate
proves output equality, mutual functional dependence of the dephasing signatures
and a phase difference constant on their fibres. Failed discovery or certificate
rejection is NOT a proof that the channels differ.

The checker interprets the actual frozen programs with sparse Boolean
polynomials. It neither constructs a two-copy kernel nor trusts supplied
semantic records. This is a sufficient certificate format, not a complete
decision procedure or a general hybrid-circuit theorem.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Any, Literal

from symq.circuit import UnsupportedOperation
from symq.hashing import canonical_json, canonical_sha256
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, Guard, ResourceLimitExceeded

Poly = frozenset[int]
_ZERO: Poly = frozenset()
_ONE: Poly = frozenset((0,))
THEOREM = "full_sign_hmr_channel_forgotten_outcomes"
_FIELDS = frozenset({
    "schema_version", "theorem", "left_sha256", "right_sha256",
    "left_selectors", "left_reconstruction", "right_reconstruction",
    "signature_from_right", "phase_function",
})


@dataclass(frozen=True)
class CertificateLimits:
    """Structural caps, separate from per-polynomial terms and elapsed time.

    The byte cap applies to canonical certificate JSON, not Python RSS. Program
    validation, arithmetic, candidate construction and checking share one clock.
    """

    max_width: int = 256
    max_operations: int = 20_000
    max_events: int = 256
    max_dictionary_terms: int = 1024
    max_certificate_terms: int = 20_000
    max_certificate_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


_DEFAULT_LIMITS = CertificateLimits()


@dataclass(frozen=True)
class ChannelCertificate:
    """Immutable reconstruction polynomials, encoded by monomial bitmasks.

    A monomial mask refers to selected left signature coordinates, except in
    ``signature_from_right``, whose variables are all right coordinates.
    ``0`` is the constant monomial; an empty tuple is the zero polynomial.
    Constructing or loading this object does not establish a proof.
    """

    left_sha256: str
    right_sha256: str
    left_selectors: tuple[int, ...]
    left_reconstruction: tuple[tuple[int, ...], ...]
    right_reconstruction: tuple[tuple[int, ...], ...]
    signature_from_right: tuple[tuple[int, ...], ...]
    phase_function: tuple[int, ...]
    schema_version: int = 1
    theorem: str = THEOREM

    def to_dict(self) -> dict[str, Any]:
        """Serialize data only; callers must still use ``verify_certificate``."""
        return {
            "schema_version": self.schema_version,
            "theorem": self.theorem,
            "left_sha256": self.left_sha256,
            "right_sha256": self.right_sha256,
            "left_selectors": list(self.left_selectors),
            "left_reconstruction": [list(p) for p in self.left_reconstruction],
            "right_reconstruction": [list(p) for p in self.right_reconstruction],
            "signature_from_right": [list(p) for p in self.signature_from_right],
            "phase_function": list(self.phase_function),
        }


@dataclass(frozen=True)
class CertificateResult:
    """``not_proved`` means only that this certificate/search did not prove it.

    This receipt is not a rewrite authorization. Verification must be rerun for
    the supplied programs after any source or certificate change.
    """

    outcome: Literal["equivalent", "not_proved", "inconclusive"]
    reason: str
    certificate: ChannelCertificate | None = None

    @property
    def equivalent(self) -> bool:
        return self.outcome == "equivalent"


@dataclass(frozen=True)
class _Program:
    data: int
    ancillas: int
    ops: tuple[Op, ...]
    sha256: str


@dataclass(frozen=True)
class _Semantics:
    outputs: tuple[Poly, ...]
    phase: Poly
    signature: tuple[Poly, ...]


def _cap(resource: str, count: int, maximum: int) -> None:
    if count > maximum:
        raise ResourceLimitExceeded(resource, maximum, count)


def _guard(budget: Budget | None, limits: CertificateLimits) -> Guard:
    if type(limits) is not CertificateLimits:
        raise TypeError("limits must be CertificateLimits")
    # Recheck even deliberately mutated frozen dataclasses at the trust boundary.
    limits.__post_init__()
    if budget is None:
        budget = Budget(max_terms=20_000, max_seconds=5)
    if type(budget) is not Budget:
        raise TypeError("budget must be Budget or None")
    guard = Guard(budget)
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError("sparse certificate checking supports terms/time, not node/RSS budgets")
    guard.check_time()
    return guard


def _snapshot(program: PhaseProgram, guard: Guard, limits: CertificateLimits) -> _Program:
    if type(program) is not PhaseProgram:
        raise TypeError("two exact PhaseProgram instances are required")
    data, ancillas = program.data, program.ancillas
    if type(data) is not int or data < 1 or type(ancillas) is not int or ancillas < 0:
        raise ValueError("invalid program dimensions")
    _cap("width", data + ancillas, limits.max_width)
    if type(program.ops) is not list:
        raise ValueError("program.ops must be a list")
    _cap("operations", len(program.ops), limits.max_operations)
    for op in program.ops:
        guard.check_time()
        if type(op) is Op and type(op.qubits) is tuple:
            _cap("instruction arity", len(op.qubits), limits.max_width)
    # The original public list and even deliberately mutated frozen Ops must not
    # remain the semantic source: the core snapshot rebuilds and revalidates them.
    copy = program.snapshot(check=guard.check_time)
    _cap("operations", len(copy.ops), limits.max_operations)
    ops = copy.ops
    _cap("measurement events", copy.measurements, limits.max_events)
    digest = canonical_sha256({
        "grammar": "sign-hmr/affine-outcomes/full-channel/v1",
        "data": data, "ancillas": ancillas,
        "ops": [[op.kind, list(op.qubits), op.outcome] for op in ops],
    })
    guard.check_time()
    return _Program(data, ancillas, tuple(ops), digest)


def _xor(left: Poly, right: Poly, guard: Guard) -> Poly:
    guard.check_time()
    result = set(left)
    guard.check_terms(len(result))
    for term in right:
        guard.check_time()
        if term in result:
            result.remove(term)
        else:
            result.add(term)
        guard.check_terms(len(result))
    return frozenset(result)


def _multiply(left: Poly, right: Poly, guard: Guard) -> Poly:
    result: set[int] = set()
    for a in left:
        for b in right:
            guard.check_time()
            term = a | b
            if term in result:
                result.remove(term)
            else:
                result.add(term)
            guard.check_terms(len(result))
    guard.check_time()
    return frozenset(result)


def _product(values: tuple[Poly, ...], guard: Guard) -> Poly:
    result = _ONE
    for value in values:
        result = _multiply(result, value, guard)
    guard.check_time()
    return result


def _interpret(program: _Program, guard: Guard) -> _Semantics:
    values = [frozenset((1 << i,)) for i in range(program.data)]
    values.extend([_ZERO] * program.ancillas)
    phase = _ZERO
    signature: list[Poly] = []
    for op in program.ops:
        guard.check_time()
        if op.kind == "mcx":
            target = op.qubits[-1]
            product = _product(tuple(values[q] for q in op.qubits[:-1]), guard)
            values[target] = _xor(values[target], product, guard)
        elif op.kind == "mcz":
            product = _product(tuple(values[q] for q in op.qubits), guard)
            phase = _xor(phase, product, guard)
        elif op.kind == "hmr":
            signature.append(values[op.qubits[0]])
            values[op.qubits[0]] = _ZERO
        elif op.kind == "mcz_if":
            if op.outcome is None:  # validate() has already refused this.
                raise UnsupportedOperation("feedback needs an initialized outcome")
            product = _product(tuple(values[q] for q in op.qubits), guard)
            signature[op.outcome] = _xor(signature[op.outcome], product, guard)
        else:
            raise UnsupportedOperation(f"outside sign/HMR grammar: {op.kind!r}")
    guard.check_time()
    return _Semantics(tuple(values), phase, tuple(signature))


def _compose(terms: tuple[int, ...], inputs: tuple[Poly, ...], guard: Guard) -> Poly:
    result = _ZERO
    for term in terms:
        guard.check_time()
        if term >> len(inputs):
            raise ValueError("certificate variable outside its signature frame")
        product = _product(tuple(value for i, value in enumerate(inputs)
                                 if term >> i & 1), guard)
        result = _xor(result, product, guard)
    return result


def _decode(value: object, guard: Guard, limits: CertificateLimits) -> ChannelCertificate:
    if type(value) is ChannelCertificate:
        source = {name: getattr(value, name) for name in _FIELDS}
        sequence_type = tuple
    elif type(value) is dict:
        source = value
        sequence_type = list
    else:
        raise ValueError("certificate must be a ChannelCertificate or JSON object")
    if source.keys() != _FIELDS:
        raise ValueError("unknown or missing certificate fields")
    if type(source["schema_version"]) is not int or source["schema_version"] != 1:
        raise ValueError("unsupported certificate schema_version")
    if type(source["theorem"]) is not str or source["theorem"] != THEOREM:
        raise ValueError("unsupported certificate theorem")
    for key in ("left_sha256", "right_sha256"):
        digest = source[key]
        if (type(digest) is not str or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("invalid source digest")
    total = 0

    def sequence(obj: Any, maximum: int, name: str) -> Any:
        if type(obj) is not sequence_type:
            raise ValueError(f"{name} must be a {sequence_type.__name__}")
        _cap(name, len(obj), maximum)
        return obj

    selectors = sequence(source["left_selectors"], limits.max_events, "selectors")
    if (any(type(i) is not int or not 0 <= i < limits.max_events for i in selectors)
            or len(set(selectors)) != len(selectors)):
        raise ValueError("selectors must be distinct nonnegative event indices")

    def polynomial(obj: Any) -> tuple[int, ...]:
        nonlocal total
        seq = sequence(obj, limits.max_certificate_terms, "certificate terms")
        total += len(seq)
        _cap("total certificate terms", total, limits.max_certificate_terms)
        previous = -1
        for term in seq:
            guard.check_time()
            if type(term) is not int or term < 0 or term.bit_length() > limits.max_events:
                raise ValueError("invalid certificate monomial")
            if term <= previous:
                raise ValueError("certificate monomials must be sorted and unique")
            previous = term
        return tuple(seq)

    def frame(name: str) -> tuple[tuple[int, ...], ...]:
        seq = sequence(source[name], limits.max_events, name)
        return tuple(polynomial(p) for p in seq)

    certificate = ChannelCertificate(
        source["left_sha256"], source["right_sha256"], tuple(selectors),
        frame("left_reconstruction"), frame("right_reconstruction"),
        frame("signature_from_right"), polynomial(source["phase_function"]),
    )
    _cap("certificate bytes", len(canonical_json(certificate.to_dict())),
         limits.max_certificate_bytes)
    guard.check_time()
    return certificate


def _check(left: _Program, right: _Program, cert: ChannelCertificate,
           guard: Guard) -> CertificateResult:
    if (left.sha256, right.sha256) != (cert.left_sha256, cert.right_sha256):
        return CertificateResult("not_proved", "certificate source digest mismatch")
    if (left.data, left.ancillas) != (right.data, right.ancillas):
        return CertificateResult("not_proved", "input/output frames differ")
    ls, rs = _interpret(left, guard), _interpret(right, guard)
    if ls.outputs != rs.outputs:
        return CertificateResult("not_proved", "full output functions do not match")
    if any(i >= len(ls.signature) for i in cert.left_selectors):
        return CertificateResult("not_proved", "selected left event does not exist")
    features = tuple(ls.signature[i] for i in cert.left_selectors)
    obligations = (
        ("left reconstruction", cert.left_reconstruction, features, ls.signature),
        ("right reconstruction", cert.right_reconstruction, features, rs.signature),
        ("reverse reconstruction", cert.signature_from_right, rs.signature, features),
        ("phase on fibres", (cert.phase_function,), features,
         (_xor(ls.phase, rs.phase, guard),)),
    )
    for name, expressions, inputs, targets in obligations:
        if len(expressions) != len(targets):
            return CertificateResult("not_proved", f"{name}: wrong coordinate count")
        for expression, target in zip(expressions, targets):
            if _compose(expression, inputs, guard) != target:
                return CertificateResult("not_proved", f"{name}: polynomial identity failed")
    guard.check_time()
    return CertificateResult("equivalent", "all one-copy full-channel identities checked", cert)


def _verify_work(left: PhaseProgram, right: PhaseProgram, certificate: object,
                 guard: Guard, limits: CertificateLimits) -> CertificateResult:
    """Own semantic scratch in a scope that ends before the public final check."""
    frozen_left = _snapshot(left, guard, limits)
    frozen_right = _snapshot(right, guard, limits)
    try:
        cert = _decode(certificate, guard, limits)
        return _check(frozen_left, frozen_right, cert, guard)
    except ValueError as exc:
        return CertificateResult("not_proved", str(exc))


def verify_certificate(
    left: PhaseProgram, right: PhaseProgram, certificate: object, *,
    budget: Budget | None = None, limits: CertificateLimits = _DEFAULT_LIMITS,
) -> CertificateResult:
    """Recompute and check a certificate against the exact supplied programs.

    Malformed certificates return ``not_proved``; unsupported/malformed programs
    raise ValueError/TypeError/UnsupportedOperation. Resource exhaustion returns
    ``inconclusive`` without a certificate. No negative channel verdict is issued.
    Semantic scratch cleanup completes before the final deadline check.
    """
    try:
        guard = _guard(budget, limits)
        result = _verify_work(left, right, certificate, guard, limits)
        guard.check_time()
        return result
    except ResourceLimitExceeded as exc:
        return CertificateResult("inconclusive", str(exc))


class _Span:
    def __init__(self, guard: Guard) -> None:
        self.guard = guard
        self.rows: dict[int, tuple[Poly, Poly]] = {}

    def add(self, value: Poly, expression: Poly) -> None:
        while value:
            self.guard.check_time()
            pivot = max(value)
            if pivot not in self.rows:
                self.rows[pivot] = value, expression
                return
            row, representation = self.rows[pivot]
            value = _xor(value, row, self.guard)
            expression = _xor(expression, representation, self.guard)

    def solve(self, value: Poly) -> Poly | None:
        result = _ZERO
        while value:
            self.guard.check_time()
            pivot = max(value)
            if pivot not in self.rows:
                return None
            row, expression = self.rows[pivot]
            value = _xor(value, row, self.guard)
            result = _xor(result, expression, self.guard)
        return result


def _dictionary(inputs: tuple[Poly, ...], degree: int, guard: Guard,
                limits: CertificateLimits) -> _Span:
    count = sum(comb(len(inputs), d) for d in range(min(degree, len(inputs)) + 1))
    _cap("dictionary terms", count, limits.max_dictionary_terms)
    span = _Span(guard)
    for d in range(min(degree, len(inputs)) + 1):
        for selected in combinations(range(len(inputs)), d):
            guard.check_time()
            mask = sum(1 << i for i in selected)
            span.add(_product(tuple(inputs[i] for i in selected), guard),
                     frozenset((mask,)))
    return span


class _GrowingDictionary:
    """The degree-bounded dictionary over features chosen so far, grown in place.

    Adding feature n inserts only the products that involve it, so the span is
    never rebuilt. The basis spans the same space as a full rebuild, whatever
    the insertion order.
    """

    def __init__(self, degree: int, guard: Guard, limits: CertificateLimits) -> None:
        self.degree, self.guard, self.limits = degree, guard, limits
        self.features: list[Poly] = []
        self.span = _dictionary((), degree, guard, limits)

    def add(self, feature: Poly) -> None:
        n = len(self.features)
        count = sum(comb(n + 1, d) for d in range(min(self.degree, n + 1) + 1))
        _cap("dictionary terms", count, self.limits.max_dictionary_terms)
        self.features.append(feature)
        for d in range(min(self.degree - 1, n) + 1):
            for selected in combinations(range(n), d):
                self.guard.check_time()
                mask = sum(1 << i for i in selected) | (1 << n)
                factors = tuple(self.features[i] for i in selected) + (feature,)
                self.span.add(_product(factors, self.guard), frozenset((mask,)))


def _discover_work(left: PhaseProgram, right: PhaseProgram, degree: int,
                   guard: Guard, limits: CertificateLimits) -> CertificateResult:
    frozen_left = _snapshot(left, guard, limits)
    frozen_right = _snapshot(right, guard, limits)
    if (frozen_left.data, frozen_left.ancillas) != (
            frozen_right.data, frozen_right.ancillas):
        return CertificateResult("not_proved", "input/output frames differ")
    ls, rs = _interpret(frozen_left, guard), _interpret(frozen_right, guard)
    if ls.outputs != rs.outputs:
        return CertificateResult("not_proved", "full output functions do not match")
    selectors: list[int] = []
    dictionary = _GrowingDictionary(degree, guard, limits)
    span = dictionary.span
    for i, value in enumerate(ls.signature):
        if span.solve(value) is None:
            selectors.append(i)
            dictionary.add(value)
    features = dictionary.features
    left_rebuild = [span.solve(value) for value in ls.signature]
    right_rebuild = [span.solve(value) for value in rs.signature]
    phase = span.solve(_xor(ls.phase, rs.phase, guard))
    inverse: list[Poly | None] = []
    reverse_span: _Span | None = None
    for feature in features:
        guard.check_time()
        if feature in rs.signature:
            inverse.append(frozenset((1 << rs.signature.index(feature),)))
        else:
            if reverse_span is None:
                reverse_span = _dictionary(rs.signature, degree, guard, limits)
            inverse.append(reverse_span.solve(feature))
    if phase is None or any(p is None for p in left_rebuild + right_rebuild + inverse):
        return CertificateResult("not_proved", "no certificate in the chosen dictionary")

    def packed(items: list[Poly | None]) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(sorted(p)) for p in items if p is not None)

    cert = ChannelCertificate(
        frozen_left.sha256, frozen_right.sha256, tuple(selectors),
        packed(left_rebuild), packed(right_rebuild), packed(inverse),
        tuple(sorted(phase)),
    )
    cert = _decode(cert, guard, limits)
    # Reinterpret the frozen actual programs; never trust the guesser's
    # semantic values or its elimination result as the final proof.
    return _check(frozen_left, frozen_right, cert, guard)


def discover_certificate(
    left: PhaseProgram, right: PhaseProgram, *, degree: int = 2,
    budget: Budget | None = None, limits: CertificateLimits = _DEFAULT_LIMITS,
) -> CertificateResult:
    """Try a bounded polynomial dictionary, then run the exact certificate checker.

    Greedily selects left event functions and seeks reconstructions of both
    signatures, an inverse reconstruction, and the relative sign. Discovery,
    fresh checking and semantic scratch cleanup share one budget. Missing a
    relation is ``not_proved``.
    """
    # Degree 0 holds only the constant, so no selected feature could ever
    # reconstruct itself: every non-constant signature would be "not proved".
    if type(degree) is not int or degree < 1:
        raise ValueError("degree must be a positive integer")
    try:
        guard = _guard(budget, limits)
        result = _discover_work(left, right, degree, guard, limits)
        guard.check_time()
        return result
    except ResourceLimitExceeded as exc:
        return CertificateResult("inconclusive", str(exc))
