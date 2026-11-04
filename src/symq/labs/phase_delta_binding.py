"""Exact, opt-in global-phase binding of two dyadic programs on a proven prefix image.

For a frozen reversible prefix F with an explicit initial domain D and two
``DyadicPhaseProgram`` objects L and R on the same wires, a ``proved`` result
of ``check_program_phase_difference`` establishes

    L(F|x>) = exp(2*pi*i*c / 2**k) * R(F|x>)   for every x in D,

hence on the coherent span of D, with k = max(k_L, k_R). Variables of every
polynomial here are the *cut wires* w = F(x), which are also the program
inputs; this is the convention of ``phase_quotient`` certificates.

It combines three independent obligations: equal basis outputs on F(D) by
exact ANF composition; the exact canonical phase difference
delta = phi_L - phi_R (mod 2**k) extracted from both sources and compared term
by term with the certificate's delta; and ``check_prefix_phase`` on that
certificate. A nonzero constant can become a relative phase under quantum
control: no controlled substitution, measurement or rewrite is authorized.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal

from symq.anf import ANF
from symq.circuit import Circuit
from symq.errors import InternalInconsistency, ResourceLimitExceeded
from symq.hashing import canonical_json
from symq.resources import Budget, Guard, session_scoped

from .dyadic_phase import DyadicGate, DyadicPhaseProgram, SymbolicPhase, _add, symbolic
from .phase_quotient import (
    _MAX_K,
    PhaseQuotientCertificate,
    Terms,
    _certificate_dict,
    _constants,
    _digest,
    _freeze_certificate,
    _freeze_prefix,
    _guard,
    _prefix_state,
    _substitute,
    check_prefix_phase,
)

Outcome = Literal["proved", "not_proved", "inconclusive"]
_KIND = "symq_program_phase_difference_result"
_THEOREM = "dyadic_programs_global_phase_on_prefix_image"
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class PhaseDifference:
    """Canonical delta = phi_left - phi_right modulo ``2**k`` on the program inputs.

    ``delta`` is a sorted tuple of (mask, coefficient) pairs with distinct
    masks and coefficients in [1, 2**k). It says nothing about outputs.
    """

    width: int
    k: int
    delta: Terms


@dataclass(frozen=True)
class ProgramPhaseResult:
    """A source-bound statement about two programs; never a rewrite authorization.

    ``not_proved`` means an obligation was not established (including a
    certificate that does not match the programs); it is not a proof of
    inequivalence. ``inconclusive`` means a resource bound was reached.
    ``witness`` is always an original prefix input, replayed by scalar execution.
    """

    outcome: Outcome
    reason: str
    obligation: str | None
    width: int | None
    k: int | None
    constant: int | None
    expected_constant: int | None
    initial_constants: tuple[tuple[int, int], ...] | None
    prefix_sha256: str | None
    left_sha256: str | None
    right_sha256: str | None
    certificate_sha256: str | None
    delta_sha256: str | None
    output_scope: str | None
    output_index: int | None = None
    violating_invariant: int | None = None
    witness: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "kind": _KIND, "theorem": _THEOREM,
            "candidate_authorized": False, "controlled_use_authorized": False,
            "outcome": self.outcome, "reason": self.reason, "obligation": self.obligation,
            "width": self.width, "k": self.k, "constant": self.constant,
            "expected_constant": self.expected_constant,
            "initial_constants": (None if self.initial_constants is None
                                  else [list(pair) for pair in self.initial_constants]),
            "prefix_sha256": self.prefix_sha256, "left_sha256": self.left_sha256,
            "right_sha256": self.right_sha256, "certificate_sha256": self.certificate_sha256,
            "delta_sha256": self.delta_sha256, "output_scope": self.output_scope,
            "output_index": self.output_index,
            "violating_invariant": self.violating_invariant, "witness": self.witness,
        }


def _angle(value: object) -> Fraction | int | None:
    if value is None or type(value) is int:
        return value
    if type(value) is Fraction:
        numerator, denominator = value.numerator, value.denominator
        if type(numerator) is int and type(denominator) is int and denominator > 0:
            return Fraction(numerator, denominator)
    raise ValueError("phase angles must be exact int or Fraction turns")


def _freeze_program(value: object, width: int, guard: Guard, label: str) -> DyadicPhaseProgram:
    """Detached, revalidated copy built only from plain ints, strings and tuples."""
    if type(value) is not DyadicPhaseProgram:
        raise TypeError(f"{label} must be a DyadicPhaseProgram")
    if type(value.width) is not int or value.width != width:
        raise ValueError(f"{label} width must equal the prefix and certificate width")
    if type(value.k) is not int or not 1 <= value.k <= _MAX_K:
        raise ValueError(f"{label} k must be an integer in [1, {_MAX_K}]")
    if type(value.gates) is not list:
        raise ValueError(f"{label} gates must be a list")
    gates = []
    for gate in list(value.gates):
        guard.check_time()
        if type(gate) is not DyadicGate:
            raise ValueError(f"{label} accepts only DyadicGate operations")
        name, wires = gate.name, gate.wires
        if (type(name) is not str or type(wires) is not tuple
                or any(type(q) is not int for q in wires)):
            raise ValueError(f"{label} gate names and wires must be plain strings and int tuples")
        gates.append(DyadicGate(name, tuple(wires), _angle(gate.angle)))
    frozen = DyadicPhaseProgram(width, gates, value.k)
    guard.check_time()
    return frozen


def _program_dict(program: DyadicPhaseProgram) -> dict[str, Any]:
    def angle(value: Fraction | int | None) -> list[int] | None:
        if value is None:
            return None
        exact = Fraction(value)
        return [exact.numerator, exact.denominator]

    return {"kind": "symq_dyadic_phase_program", "width": program.width, "k": program.k,
            "gates": [[g.name, list(g.wires), angle(g.angle)] for g in program.gates]}


def _difference(left: SymbolicPhase, right: SymbolicPhase, guard: Guard) -> tuple[int, Terms]:
    """Scale both phases to k = max(k_l, k_r), subtract and canonicalize."""
    k = max(left.k, right.k)
    modulus = 1 << k
    scaled_left = {m: (c << (k - left.k)) % modulus for m, c in left.phase.items()}
    scaled_right = {m: (c << (k - right.k)) % modulus for m, c in right.phase.items()}
    guard.check_terms(len(scaled_left) + len(scaled_right))
    difference = _add(scaled_left, scaled_right, -1, k=k, guard=guard)
    guard.check_time()
    return k, tuple(sorted(difference.items()))


def _difference_dict(width: int, k: int, delta: Terms) -> dict[str, Any]:
    return {"kind": "symq_phase_difference", "width": width, "k": k,
            "delta": [list(term) for term in delta]}


@session_scoped
def extract_phase_difference(left: DyadicPhaseProgram, right: DyadicPhaseProgram, *,
                             budget: Budget | None = None) -> PhaseDifference:
    """Exact canonical phi_left - phi_right on the shared program inputs.

    Only the phase polynomials are compared; equal outputs are a separate
    obligation established by ``check_program_phase_difference``. Exhausting
    ``budget`` raises ``ResourceLimitExceeded``; no partial delta is returned.
    """
    guard = _guard(budget)
    if type(left) is not DyadicPhaseProgram or type(left.width) is not int:
        raise TypeError("left must be a DyadicPhaseProgram")
    a = _freeze_program(left, left.width, guard, "left")
    b = _freeze_program(right, a.width, guard, "right")
    k, delta = _difference(symbolic(a, _guard=guard), symbolic(b, _guard=guard), guard)
    return PhaseDifference(a.width, k, delta)


def _expected(value: object) -> int | None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("expected_constant must be None or a nonnegative integer")
    return value


def _check(prefix: Circuit, left: DyadicPhaseProgram, right: DyadicPhaseProgram,
           certificate: PhaseQuotientCertificate, initial_constants: object,
           expected_constant: object, guard: Guard, progress: dict[str, Any]) -> ProgramPhaseResult:
    progress["stage"] = "inputs"
    expected = _expected(expected_constant)
    cert = _freeze_certificate(certificate, guard)
    width = cert.width
    source = _freeze_prefix(prefix, width, guard)
    constants = _constants(initial_constants, width, guard)
    a = _freeze_program(left, width, guard, "left")
    b = _freeze_program(right, width, guard, "right")
    k = max(a.k, b.k)
    if expected is not None and expected >= 1 << k:
        raise ValueError("expected_constant must be canonical modulo 2**k")
    progress.update(width=width, k=k, expected_constant=expected, initial_constants=constants)
    progress["prefix_sha256"] = _digest(source.to_dict(), guard)
    progress["left_sha256"] = _digest(_program_dict(a), guard)
    progress["right_sha256"] = _digest(_program_dict(b), guard)
    progress["certificate_sha256"] = _digest(_certificate_dict(cert), guard)

    def result(outcome: Literal["proved", "not_proved"], reason: str, obligation: str | None,
               constant: int | None = None, **extra: int | None) -> ProgramPhaseResult:
        guard.check_time()
        return ProgramPhaseResult(
            outcome, reason, obligation, width, k, constant, expected, constants,
            progress["prefix_sha256"], progress["left_sha256"], progress["right_sha256"],
            progress["certificate_sha256"], progress.get("delta_sha256"),
            progress.get("output_scope"), **extra)

    # Obligation 1: equal basis outputs on F(D), by exact ANF composition.
    progress["stage"] = "outputs"
    sa, sb = symbolic(a, _guard=guard), symbolic(b, _guard=guard)
    fixed_ones = sum(1 << wire for wire, bit in constants if bit)
    state: tuple[ANF, ...] | None = None
    scope = "all_cut_inputs"
    for index, (p, q) in enumerate(zip(sa.outputs, sb.outputs)):
        guard.check_time()
        difference = p ^ q
        if not difference.terms:
            continue
        if state is None:
            state = _prefix_state(source, constants, guard)
        scope = "prefix_image"
        composed = _substitute(difference, state, guard)
        if composed.terms:
            witness = min(composed.terms, key=lambda m: (m.bit_count(), m)) | fixed_ones
            guard.check_time()
            cut = source.run(witness)
            guard.check_time()
            if (a.run(cut)[0] == b.run(cut)[0]
                    or any((witness >> wire & 1) != bit for wire, bit in constants)):
                raise InternalInconsistency("output witness failed scalar replay")
            return result("not_proved", "outputs differ on the prefix image", "outputs",
                          output_index=index, witness=witness)
    progress["output_scope"] = scope

    # Obligation 2: the certificate's delta is exactly the programs' phase difference.
    progress["stage"] = "phase_difference"
    extracted_k, delta = _difference(sa, sb, guard)
    if extracted_k != k:
        raise InternalInconsistency("extracted modulus differs from max(k_left, k_right)")
    progress["delta_sha256"] = _digest(_difference_dict(width, k, delta), guard)
    if cert.k != k:
        return result("not_proved", f"certificate modulus 2**{cert.k} differs from the "
                      f"extracted modulus 2**{k}", "phase_difference")
    if cert.delta != delta:
        return result("not_proved", "certificate delta differs from the extracted program "
                      "phase difference", "phase_difference")

    # Obligation 3: delta is the constant c on F(D) (phase_quotient, unchanged).
    progress["stage"] = "prefix_phase"
    inner = check_prefix_phase(source, cert, guard.inherited_budget(),
                               initial_constants=constants)
    if (inner.prefix_sha256 != progress["prefix_sha256"]
            or inner.certificate_sha256 != progress["certificate_sha256"]
            or inner.initial_constants != constants):
        raise InternalInconsistency("prefix phase check bound different sources")
    if inner.outcome != "proved":
        return result("not_proved", inner.reason, "prefix_phase",
                      violating_invariant=inner.violating_invariant, witness=inner.witness)
    if inner.constant != cert.constant:
        raise InternalInconsistency("prefix phase check reported a different constant")
    if expected is not None and cert.constant != expected:
        return result("not_proved", "proved constant differs from expected_constant",
                      "expected_constant")
    return result("proved", "equal outputs on the prefix image and constant extracted "
                  "phase difference", None, cert.constant)


@session_scoped
def _checked(prefix: Circuit, left: DyadicPhaseProgram, right: DyadicPhaseProgram,
             certificate: PhaseQuotientCertificate, initial_constants: object,
             expected_constant: object, progress: dict[str, Any],
             budget: Budget | None = None) -> ProgramPhaseResult:
    return _check(prefix, left, right, certificate, initial_constants, expected_constant,
                  _guard(budget), progress)


def check_program_phase_difference(
        prefix: Circuit, left: DyadicPhaseProgram, right: DyadicPhaseProgram,
        certificate: PhaseQuotientCertificate, *,
        initial_constants: tuple[tuple[int, int], ...] = (),
        expected_constant: int | None = None,
        budget: Budget | None = None) -> ProgramPhaseResult:
    """Prove left and right differ only by a global phase on the prefix image.

    All inputs are snapshotted and revalidated first. Invalid input raises
    ``TypeError``/``ValueError``; exhausting ``budget`` returns ``inconclusive``
    (it binds only the identities computed before the limit and has no
    replayable claim). ``expected_constant``, if given, must equal the proved
    constant. The theorem is stated in the module docstring.
    """
    progress: dict[str, Any] = {}
    try:
        return _checked(prefix, left, right, certificate, initial_constants,
                        expected_constant, progress, budget=budget)
    except ResourceLimitExceeded as error:
        get = progress.get
        return ProgramPhaseResult(
            "inconclusive", f"resource limit exceeded during {get('stage', 'inputs')}: {error}",
            "resources", get("width"), get("k"), None, get("expected_constant"),
            get("initial_constants"), get("prefix_sha256"), get("left_sha256"),
            get("right_sha256"), get("certificate_sha256"), get("delta_sha256"),
            get("output_scope"))


_NULLABLE_INT = ("constant", "expected_constant", "output_index", "violating_invariant",
                 "witness")
_DIGESTS = ("prefix_sha256", "left_sha256", "right_sha256", "certificate_sha256",
            "delta_sha256")
_RECEIPT_KEYS = frozenset(ProgramPhaseResult("not_proved", "", None, 1, 1, None, None, (),
                                             None, None, None, None, None, None).to_dict())


def _validate_receipt(value: object, guard: Guard) -> None:
    """Closed schema with exact JSON types; validation is not a proof."""
    if type(value) is not dict or set(value) != _RECEIPT_KEYS:
        raise ValueError("a serialized program phase receipt with the exact fields is required")
    if value["outcome"] == "inconclusive":
        raise ValueError("an inconclusive result carries no replayable claim")
    exact = {"schema_version": int, "kind": str, "theorem": str, "outcome": str, "reason": str,
             "candidate_authorized": bool, "controlled_use_authorized": bool,
             "width": int, "k": int}
    if any(type(value[key]) is not kind for key, kind in exact.items()):
        raise ValueError("malformed program phase receipt field types")
    if value["outcome"] not in ("proved", "not_proved"):
        raise ValueError("unknown program phase receipt outcome")
    for key in _NULLABLE_INT:
        if value[key] is not None and type(value[key]) is not int:
            raise ValueError(f"receipt field {key} must be an integer or null")
    for key in ("obligation", "output_scope"):
        if value[key] is not None and type(value[key]) is not str:
            raise ValueError(f"receipt field {key} must be a string or null")
    for key in _DIGESTS:
        digest = value[key]
        if digest is not None and (type(digest) is not str or not _SHA256.fullmatch(digest)):
            raise ValueError(f"receipt field {key} must be a SHA-256 hex digest or null")
    pairs = value["initial_constants"]
    if type(pairs) is not list:
        raise ValueError("receipt initial_constants must be an array")
    for pair in pairs:
        guard.check_time()
        if type(pair) is not list or len(pair) != 2 or any(type(v) is not int for v in pair):
            raise ValueError("receipt initial constants must be [wire, bit] integer pairs")


@session_scoped
def replay_program_phase_difference(
        prefix: Circuit, left: DyadicPhaseProgram, right: DyadicPhaseProgram,
        certificate: PhaseQuotientCertificate, receipt: object, *,
        initial_constants: tuple[tuple[int, int], ...] = (),
        expected_constant: int | None = None,
        budget: Budget | None = None) -> ProgramPhaseResult:
    """Recompute every obligation and compare the complete, untrusted receipt.

    The consumer pins ``expected_constant``; a receipt made without that pin,
    or with another one, does not match. Exhausting the budget raises
    ``ResourceLimitExceeded`` (no answer), never a mismatch or a verdict.
    """
    guard = _guard(budget)
    _validate_receipt(receipt, guard)
    fresh = _check(prefix, left, right, certificate, initial_constants, expected_constant,
                   guard, {})
    guard.check_time()
    if canonical_json(fresh.to_dict()) != canonical_json(receipt):
        raise ValueError("program phase receipt mismatch")
    return fresh
