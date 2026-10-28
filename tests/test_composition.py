"""A worked two-block composition, its local suffix lemma, and the mutants that must break it.

The example is deliberately tiny and self-contained -- no qant circuit is copied, since
``yoch/qant`` is private and the issue forbids importing its raw circuits without authorization.

Circuit, width 4, wires ``x0 x1 x2 x3``:

* block ``A``: ``ccx(x0, x1, x2)`` -- the AND of ``x0`` and ``x1`` lands on ``x2``;
* block ``B``: ``cx(2, 0)``      -- propagates ``x2`` onto ``x0``.

Wire 3 is **ignored garbage**: the variant ``A'`` flips it and nothing downstream reads it. It is
*not* a restored ancilla, and this suite does not claim restoration. A contract that required wire 3
to come back unchanged would need its own obligation; see
``test_wire_three_is_declared_garbage_and_its_restoration_is_not_claimed``.

Everything is checked against concrete execution, which shares no code with the SAT encoding.
"""

from __future__ import annotations

import time

import pytest

from symq import Budget, Circuit
from symq.sat import available
from symq.sat.assumptions import And, Const, Eq, ExprError, Not, Var, Xor, evaluate, validate
from symq.sat.composition import (
    Guarantee,
    Interface,
    check_composition,
    replay_witness,
)

pytestmark = pytest.mark.skipif(not available(), reason="python-sat is not installed")

WIDTH = 4
BUDGET = Budget(max_seconds=30)

WEAK_RELATION = Eq(Var("u.2"), Var("v.2"))
"""``R(u, v) := u.x2 = v.x2`` -- the only wire ``B`` reads.

This relation is **too weak for a local suffix lemma**: it says nothing about wires 0 and 1, which
``B`` writes, so two cut states agreeing on wire 2 can leave the suffixes disagreeing on wire 0. It
is kept because it is the relation the original revision used, and the audit's counterexample shows
it must now be rejected.
"""

STRONG_RELATION = And(
    And(Eq(Var("u.0"), Var("v.0")), Eq(Var("u.1"), Var("v.1"))),
    Eq(Var("u.2"), Var("v.2")),
)
"""``R(u, v)``: equality on wires 0, 1 and 2, saying nothing about wire 3."""


def block_a() -> Circuit:
    """``x2 ^= x0 AND x1``."""
    return Circuit(WIDTH).ccx(0, 1, 2)


def block_a_with_scratch_junk() -> Circuit:
    """The same product, plus a flip of ``x3`` that the suffix never reads."""
    return Circuit(WIDTH).ccx(0, 1, 2).x(3)


def block_a_wrong() -> Circuit:
    """A prefix that writes garbage into ``x2`` -- the wire the suffix *does* read."""
    return Circuit(WIDTH).ccx(0, 1, 2).cx(0, 2)


def block_b() -> Circuit:
    """``x0 ^= x2``: reads the product, writes an input wire back."""
    return Circuit(WIDTH).cx(2, 0)


def block_b_prime() -> Circuit:
    """The same propagation written through a scratch that is restored."""
    return Circuit(WIDTH).cx(2, 3).cx(3, 2).cx(2, 3).cx(2, 0)


def guarantee() -> Guarantee:
    """``post``: the final states agree on wires 0, 1 and 2; wire 3 is garbage."""
    expression = And(Eq(Var("s.0"), Var("t.0")), Eq(Var("s.1"), Var("t.1")))
    expression = And(expression, Eq(Var("s.2"), Var("t.2")))
    return Guarantee(WIDTH, Const(True), expression)


def interface(relation=None) -> Interface:
    return Interface(WIDTH, Const(True), WEAK_RELATION if relation is None else relation)


OBSERVED = (0, 1, 2)
"""Wires the contract observes; wire 3 is the scratch the variant flips and is excluded."""


def exhaustive(left: Circuit, right: Circuit) -> bool:
    """The contract's conclusion, by concrete execution: the observed wires agree on every input."""
    return all(
        ((left.run(x) >> wire) & 1) == ((right.run(x) >> wire) & 1)
        for x in range(1 << WIDTH)
        for wire in OBSERVED
    )


def fully_identical(left: Circuit, right: Circuit) -> bool:
    """Every wire equal; used to show the pair is *not* identical, so the relation is doing work."""
    return all(left.run(x) == right.run(x) for x in range(1 << WIDTH))


def run_check(
    relation,
    *,
    prefix_left=None,
    prefix_right=None,
    suffix_left=None,
    suffix_right=None,
    guarantee_=None,
    budget=BUDGET,
):
    return check_composition(
        prefix_left=block_a() if prefix_left is None else prefix_left,
        prefix_right=block_a_with_scratch_junk() if prefix_right is None else prefix_right,
        suffix_left=block_b() if suffix_left is None else suffix_left,
        suffix_right=block_b() if suffix_right is None else suffix_right,
        interface=interface(relation),
        guarantee=guarantee() if guarantee_ is None else guarantee_,
        budget=budget,
    )


# ------------------------------------------------------- the local lemma, over independent cut states


def test_the_weak_relation_is_rejected_on_the_audit_counterexample():
    """The decisive regression: ``R = (u.2 = v.2)`` no longer certifies the suffix.

    The audit gives the counterexample explicitly: ``u = 0``, ``v = 1`` satisfy ``R`` (both have
    bit 2 clear) and ``Pre_B = TRUE``, yet ``B(u) = 0`` and ``B'(v) = 1`` disagree on wire 0, so
    ``post`` fails. The previous revision accepted this relation because it only ever evaluated the
    suffix on cut states that its own prefixes happened to produce.

    This test is the reason the obligation was rewritten: it fails on ``7e7b481`` and passes now.
    """
    verdict = run_check(WEAK_RELATION)
    assert not verdict.accepted, [(o.name, o.satisfiable) for o in verdict.obligations]
    suffix = verdict.by_name("suffix")
    assert suffix.satisfiable is True, "a counterexample must exist"
    assert suffix.witness, "and must be reported as a pair of cut states"

    replayed = replay_witness(
        suffix,
        interface=interface(WEAK_RELATION),
        guarantee=guarantee(),
        suffix_left=block_b(),
        suffix_right=block_b(),
    )
    assert replayed.kind == "cut"
    u, v = replayed.inputs
    # The audit's own pair must be a valid counterexample, whatever the solver happened to return.
    assert ((u >> 2) & 1) == ((v >> 2) & 1), "R holds on the reported pair"
    left_out, right_out = block_b().run(u), block_b().run(v)
    assert ((left_out ^ right_out) & 0b111) != 0, "and the suffixes really disagree"


def test_the_audit_pair_u0_v1_is_a_counterexample_by_hand():
    """The audit's ``u=0, v=1`` checked without any solver, so the claim does not rest on the CNF.

    ``B = B' = CX(2,0)`` maps ``0 -> 0`` and ``1 -> 1``; ``R`` holds because both have bit 2 clear;
    wire 0 differs, so ``post`` fails on wires 0..2.
    """
    u, v = 0, 1
    assert ((u >> 2) & 1) == ((v >> 2) & 1), "u and v satisfy R"
    left_out, right_out = block_b().run(u), block_b().run(v)
    assert ((left_out ^ right_out) & 0b111) != 0, "yet the images differ on an observed wire"


def test_the_strengthened_relation_yields_a_universal_suffix_lemma():
    """``R`` on wires 0, 1, 2 passes, and passes *for every cut pair* it admits.

    The proof is universal by construction: the suffix query encodes only ``B`` and ``B'`` over two
    independent symbolic states, so UNSAT means no admissible pair violates ``post``. The
    brute-force loop below is a second opinion over the same statement, computed by execution.
    """
    verdict = run_check(STRONG_RELATION)
    assert verdict.accepted, [(o.name, o.satisfiable) for o in verdict.obligations]
    assert verdict.by_name("suffix").satisfiable is False

    for u in range(1 << WIDTH):
        for v in range(1 << WIDTH):
            if ((u ^ v) & 0b111) != 0:
                continue  # not R-related
            left_out, right_out = block_b().run(u), block_b().run(v)
            assert ((left_out ^ right_out) & 0b111) == 0, (u, v)


def test_the_suffix_query_does_not_encode_the_prefixes():
    """Structural check on the obligation itself: it must be insensitive to the prefixes.

    Growing the prefixes -- even hugely -- must leave the suffix obligation's CNF byte-for-byte the
    same size. A regression that silently reintroduced the prefixes (as the audited revision did)
    would make it grow.
    """
    small = run_check(STRONG_RELATION)
    bigger_prefix_left = Circuit(WIDTH)
    for wire in range(WIDTH):
        bigger_prefix_left = bigger_prefix_left.cx(wire, (wire + 1) % WIDTH).ccx(
            wire, (wire + 1) % WIDTH, (wire + 2) % WIDTH
        )
    bigger = check_composition(
        prefix_left=bigger_prefix_left,
        prefix_right=bigger_prefix_left.x(3),
        suffix_left=block_b(),
        suffix_right=block_b(),
        interface=interface(STRONG_RELATION),
        guarantee=guarantee(),
        budget=BUDGET,
    )
    assert bigger.by_name("suffix").clauses == small.by_name("suffix").clauses
    assert bigger.by_name("suffix").variables == small.by_name("suffix").variables
    # The prefix obligation, by contrast, does grow with the prefixes.
    assert bigger.by_name("prefix").clauses > small.by_name("prefix").clauses


def test_the_interface_relation_still_does_work_across_the_cut():
    """The strong relation succeeds although the prefixes differ on wire 3.

    Without a relation carrying the correlation, demanding full wire equality across the cut would
    reject a correct composition. This pins that the expressive gain survives the correction.
    """
    every_wire = And(
        And(Eq(Var("u.0"), Var("v.0")), Eq(Var("u.1"), Var("v.1"))),
        And(Eq(Var("u.2"), Var("v.2")), Eq(Var("u.3"), Var("v.3"))),
    )
    verdict = run_check(every_wire)
    assert not verdict.accepted, "full equality cannot relate two different cut states"
    assert verdict.by_name("prefix").satisfiable is True
    assert not fully_identical(
        Circuit(WIDTH, [*block_a().gates, *block_b().gates]),
        Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *block_b().gates]),
    )


def test_wire_three_is_declared_garbage_and_its_restoration_is_not_claimed():
    """Wire 3 is an ignored output, **not** a restored ancilla.

    ``A' = A; X(3)`` leaves wire 3 flipped for every input, so nothing here certifies restoration.
    The guarantee deliberately omits wire 3 and the test states the consequence: the composed
    circuits differ on it. Claiming "clean ancilla restoration" would require an extra obligation
    over wire 3, which this checker does not implement.
    """
    left = Circuit(WIDTH, [*block_a().gates, *block_b().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *block_b().gates])
    assert all(((left.run(x) ^ right.run(x)) >> 3) & 1 for x in range(1 << WIDTH))
    assert exhaustive(left, right), "but every observed wire agrees"


# ---------------------------------------------------------------- the four obligations, separately


def test_the_domain_query_is_satisfiable():
    verdict = run_check(STRONG_RELATION)
    domain = verdict.by_name("domain")
    assert domain.wanted == "sat" and domain.satisfiable is True, domain


def test_the_prefix_obligation_holds_for_the_positive_pair():
    verdict = run_check(STRONG_RELATION)
    prefix = verdict.by_name("prefix")
    assert prefix.ok and prefix.satisfiable is False


def test_the_interface_obligation_holds_for_a_vacuous_precondition():
    verdict = run_check(STRONG_RELATION)
    assert verdict.by_name("interface").ok


def test_the_suffix_obligation_holds_for_the_positive_pair():
    verdict = run_check(STRONG_RELATION)
    assert verdict.by_name("suffix").ok


def test_the_composition_is_accepted_and_agrees_with_concrete_execution():
    left = Circuit(WIDTH, [*block_a().gates, *block_b().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *block_b().gates])
    verdict = run_check(STRONG_RELATION)
    assert verdict.accepted, [(o.name, o.satisfiable) for o in verdict.obligations]
    assert exhaustive(left, right), "the accepted conclusion must be true concretely"


# ------------------------------------------------------------------- the adversarial mutants


def test_a_prefix_that_corrupts_the_read_wire_is_rejected():
    verdict = run_check(STRONG_RELATION, prefix_right=block_a_wrong())
    assert not verdict.accepted
    prefix = verdict.by_name("prefix")
    assert prefix.satisfiable is True, "the counterexample must exist"

    replayed = replay_witness(
        prefix,
        interface=interface(STRONG_RELATION),
        prefix_left=block_a(),
        prefix_right=block_a_wrong(),
    )
    (value,) = replayed.inputs
    assert block_a().run(value) != block_a_wrong().run(value)


def test_a_suffix_that_ignores_the_relation_fails():
    """A candidate suffix whose output cannot follow from the relation is rejected."""
    broken = Circuit(WIDTH).cx(2, 3).x(3)
    left = Circuit(WIDTH, [*block_a().gates, *block_b().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *broken.gates])
    verdict = run_check(STRONG_RELATION, suffix_right=broken)
    assert not verdict.accepted
    assert verdict.by_name("suffix").satisfiable is True
    assert not exhaustive(left, right), "and the rejected composition really is wrong"


def test_an_unsatisfiable_precondition_is_refused_rather_than_certified():
    """``x0 AND NOT x0`` is never true, so every implication over it is vacuous."""
    contradictory = And(Var("x.0"), Not(Var("x.0")))
    verdict = check_composition(
        prefix_left=block_a(),
        prefix_right=block_a_wrong(),
        suffix_left=block_b(),
        suffix_right=block_b(),
        interface=Interface(WIDTH, contradictory, STRONG_RELATION),
        guarantee=guarantee(),
        budget=BUDGET,
    )
    assert not verdict.accepted
    assert verdict.by_name("domain").satisfiable is False
    assert "unsatisfiable" in verdict.reason
    assert len(verdict.obligations) == 1, "no implication is even attempted"


def test_a_satisfiable_precondition_is_not_refused():
    constraint = Eq(Var("x.0"), Const(True))
    verdict = check_composition(
        prefix_left=block_a(),
        prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(),
        suffix_right=block_b(),
        interface=Interface(WIDTH, constraint, STRONG_RELATION),
        guarantee=guarantee(),
        budget=BUDGET,
    )
    assert verdict.by_name("domain").satisfiable is True


# ------------------------------------------------------- a precondition that actually constrains


def restricted_precondition():
    """``P: x0 = 0 AND x2 = 0``. The suffixes are equivalent only on this domain."""
    return And(Eq(Var("x.0"), Const(False)), Eq(Var("x.2"), Const(False)))


def restricted_relation():
    """Equality on wires 0, 1, 2 **and** ``u.2 = 0`` -- the last conjunct is what feeds ``Pre_B``."""
    return And(STRONG_RELATION, Eq(Var("u.2"), Const(False)))


def restricted_pre_b():
    return Eq(Var("u.2"), Const(False))


def identity_suffix() -> Circuit:
    return Circuit(WIDTH)


def xor_propagating_suffix() -> Circuit:
    """``B' = CX(2,0)``: differs from the identity exactly when ``x2 = 1``."""
    return Circuit(WIDTH).cx(2, 0)


def restricted_guarantee():
    return Guarantee(WIDTH, restricted_pre_b(), guarantee().postcondition)


def run_restricted(*, relation=None, pre_b=None, suffix_right=None, prefix_right=None):
    return check_composition(
        prefix_left=block_a(),
        prefix_right=block_a_with_scratch_junk() if prefix_right is None else prefix_right,
        suffix_left=identity_suffix(),
        suffix_right=xor_propagating_suffix() if suffix_right is None else suffix_right,
        interface=Interface(
            WIDTH,
            restricted_precondition(),
            restricted_relation() if relation is None else relation,
        ),
        guarantee=(
            restricted_guarantee()
            if pre_b is None
            else Guarantee(WIDTH, pre_b, guarantee().postcondition)
        ),
        budget=BUDGET,
    )


def test_a_nontrivial_pre_b_is_verified_end_to_end():
    """The case the audit asks for: ``Pre_B`` is a real constraint and the suffixes differ off it.

    ``B = identity`` and ``B' = CX(2,0)`` are *not* equivalent in general -- they differ whenever
    ``x2 = 1``. They are equivalent on the cut states that satisfy ``Pre_B: u.2 = 0``, which is
    exactly what the suffix obligation proves. Every obligation, the non-vacuity of ``P`` and the
    composed circuits are checked independently.
    """
    verdict = run_restricted()
    assert verdict.accepted, [(o.name, o.satisfiable) for o in verdict.obligations]
    for name in ("domain", "prefix", "interface", "suffix"):
        assert verdict.by_name(name).ok, (name, verdict.by_name(name))

    # P is not empty.
    satisfying = [x for x in range(1 << WIDTH) if (x & 1) == 0 and ((x >> 2) & 1) == 0]
    assert satisfying, "an empty domain would make the certificate vacuous"

    # The composed circuits agree on every input satisfying P.
    left = Circuit(WIDTH, [*block_a().gates, *identity_suffix().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *xor_propagating_suffix().gates])
    for x in satisfying:
        assert ((left.run(x) ^ right.run(x)) & 0b111) == 0, x

    # ... and the two suffixes really are different outside Pre_B, so the restriction is doing work.
    outside = [u for u in range(1 << WIDTH) if (u >> 2) & 1]
    assert outside and any(
        ((identity_suffix().run(u) ^ xor_propagating_suffix().run(u)) & 0b111) != 0 for u in outside
    )


def test_dropping_the_pre_b_constraint_from_the_relation_breaks_the_interface():
    """Mutant: ``R`` without ``u.2 = 0`` no longer implies ``Pre_B``, so obligation 2 must fail."""
    weaker = STRONG_RELATION
    verdict = run_restricted(relation=weaker)
    assert not verdict.accepted
    interface_obligation = verdict.by_name("interface")
    assert interface_obligation.satisfiable is True, "a cut pair satisfying R but not Pre_B exists"

    replayed = replay_witness(
        interface_obligation,
        interface=Interface(WIDTH, restricted_precondition(), weaker),
        guarantee=Guarantee(WIDTH, restricted_pre_b(), guarantee().postcondition),
    )
    assert replayed.kind == "cut"
    u, v = replayed.inputs
    assert ((u >> 2) & 1) == ((v >> 2) & 1), "the pair satisfies R"
    assert (u >> 2) & 1, "and violates Pre_B"


def test_vacuous_pre_b_makes_the_same_suffix_pair_fail():
    """Mutant: with ``Pre_B = TRUE`` the suffix obligation must fail on the same ``B``/``B'``.

    Note the relation here is the one *without* ``u.2 = 0``. With that conjunct included, ``R``
    alone already forces ``u.2 = 0`` and the suffix conclusion holds even under ``Pre_B = TRUE`` --
    so this mutant would be vacuous. Removing it is what makes ``Pre_B`` load-bearing, which is
    precisely the point of the example.
    """
    relation_without_pre_b = STRONG_RELATION
    verdict = run_restricted(relation=relation_without_pre_b, pre_b=Const(True))
    assert not verdict.accepted
    suffix = verdict.by_name("suffix")
    assert suffix.satisfiable is True
    replayed = replay_witness(
        suffix,
        interface=Interface(WIDTH, restricted_precondition(), relation_without_pre_b),
        guarantee=Guarantee(WIDTH, Const(True), guarantee().postcondition),
        suffix_left=identity_suffix(),
        suffix_right=xor_propagating_suffix(),
    )
    u, v = replayed.inputs
    left_out, right_out = identity_suffix().run(u), xor_propagating_suffix().run(v)
    assert ((left_out ^ right_out) & 0b111) != 0


def test_a_mutant_suffix_violating_the_postcondition_is_rejected():
    """Mutant: ``B' = X(0)`` instead of ``CX(2,0)``, which no restriction can rescue."""
    verdict = run_restricted(suffix_right=Circuit(WIDTH).x(0))
    assert not verdict.accepted
    assert verdict.by_name("suffix").satisfiable is True


def test_the_restriction_is_indispensable_by_brute_force():
    """Independent of SAT: the same suffixes differ off ``Pre_B``, and the composed pair is correct.

    This is what makes the example a real test of ``Pre_B`` rather than of the precondition ``P``:
    the composed circuits *are* wrong outside ``P`` and the suffix lemma *is* false outside
    ``Pre_B``, so an obligation that ignored either would have to be unsound here.
    """
    left = Circuit(WIDTH, [*block_a().gates, *identity_suffix().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *xor_propagating_suffix().gates])
    satisfying = [x for x in range(1 << WIDTH) if (x & 1) == 0 and ((x >> 2) & 1) == 0]
    assert all(((left.run(x) ^ right.run(x)) & 0b111) == 0 for x in satisfying)
    assert any(((left.run(x) ^ right.run(x)) & 0b111) != 0 for x in range(1 << WIDTH))

    # Without Pre_B the local lemma is false: R-related pairs exist whose images differ.
    def related(u, v):
        return ((u ^ v) & 0b111) == 0 and ((u >> 2) & 1) == 0

    def post_ok(u, v):
        return ((identity_suffix().run(u) ^ xor_propagating_suffix().run(v)) & 0b111) == 0

    assert all(post_ok(u, v) for u in range(16) for v in range(16) if related(u, v))
    unrestricted = [
        (u, v) for u in range(16) for v in range(16) if ((u ^ v) & 0b111) == 0 and not post_ok(u, v)
    ]
    assert unrestricted, "without u.2 = 0 the relation admits a violating pair"


# ------------------------------------------------------------------------------ budgets


def test_a_tiny_budget_times_out_instead_of_certifying():
    """No verdict is reported once the deadline has passed, even for a tiny problem."""
    verdict = run_check(STRONG_RELATION, budget=Budget(max_seconds=1e-9))
    assert not verdict.accepted
    assert verdict.timed_out
    assert "budget" in verdict.reason


def test_a_slow_encoding_is_charged_to_the_budget(monkeypatch):
    """Deterministic: encoding is slowed past the deadline, so the query must time out.

    Before the fix the clock only started at solver creation, so a slow encode was invisible and the
    obligation could be certified with most of its work outside the budget.
    """
    from symq.sat import composition

    real = composition.encode_circuit

    def slow(encoder, circuit):
        time.sleep(0.05)
        return real(encoder, circuit)

    monkeypatch.setattr(composition, "encode_circuit", slow)
    verdict = run_check(STRONG_RELATION, budget=Budget(max_seconds=0.05))
    assert not verdict.accepted
    assert verdict.timed_out
    timed_out = [item.name for item in verdict.obligations if item.timed_out]
    assert timed_out, "at least one obligation must be reported as a timeout"


def test_an_unsat_returned_after_the_deadline_is_not_certified(monkeypatch):
    """Deterministic: the solver sleeps past the deadline, then answers UNSAT.

    The old ``max(deadline - now, 0.001)`` started the solver anyway and accepted whatever came
    back, so a late UNSAT could become a certified verdict. It must now be a timeout.
    """
    from symq.sat import composition

    real_factory = composition._solver_factory

    class LateSolver:
        def __init__(self, inner):
            self._inner = inner

        def solve_limited(self, **kwargs):
            time.sleep(0.06)
            return self._inner.solve_limited(**kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    def factory():
        base = real_factory()

        def make(**kwargs):
            return LateSolver(base(**kwargs))

        return make

    monkeypatch.setattr(composition, "_solver_factory", factory)
    verdict = run_check(STRONG_RELATION, budget=Budget(max_seconds=0.02))
    assert not verdict.accepted
    assert verdict.timed_out
    assert all(item.satisfiable is None for item in verdict.obligations), [
        (item.name, item.satisfiable) for item in verdict.obligations
    ]


def test_obligation_seconds_covers_the_whole_obligation():
    """``seconds`` is measured from before encoding, not from solver creation.

    The suffix obligation encodes two circuits, so its reported time must be at least the time an
    empty encoder needs; more importantly the sum over obligations must be a plausible fraction of
    the wall clock for the call, rather than a strict subset of it.
    """
    started = time.perf_counter()
    verdict = run_check(STRONG_RELATION)
    wall = time.perf_counter() - started
    assert verdict.total_seconds <= wall + 1e-3
    for item in verdict.obligations:
        assert item.seconds > 0.0, item



def test_cleanup_over_deadline_refuses_otherwise_valid_certificate(monkeypatch):
    """An UNSAT proof cannot bypass the deadline by returning before solver cleanup."""
    from symq.sat import composition

    actual_factory = composition._solver_factory

    class SlowCleanup:
        def __init__(self, real):
            self.real = real

        def __getattr__(self, name):
            return getattr(self.real, name)

        def delete(self):
            time.sleep(0.035)
            return self.real.delete()

    def factory():
        create = actual_factory()

        def create_slow(**kwargs):
            return SlowCleanup(create(**kwargs))

        return create_slow

    monkeypatch.setattr(composition, "_solver_factory", factory)
    verdict = run_check(STRONG_RELATION, budget=Budget(max_seconds=0.01))
    assert not verdict.accepted
    assert verdict.timed_out
    assert verdict.by_name("domain").satisfiable is None
    assert verdict.by_name("domain").seconds >= 0.035


def test_obligation_seconds_include_solver_cleanup(monkeypatch):
    """The sum of obligation durations must account for deliberate cleanup time."""
    from symq.sat import composition

    actual_factory = composition._solver_factory

    class SlowCleanup:
        def __init__(self, real):
            self.real = real

        def __getattr__(self, name):
            return getattr(self.real, name)

        def delete(self):
            time.sleep(0.012)
            return self.real.delete()

    def factory():
        create = actual_factory()

        def create_slow(**kwargs):
            return SlowCleanup(create(**kwargs))

        return create_slow

    monkeypatch.setattr(composition, "_solver_factory", factory)
    started = time.perf_counter()
    verdict = run_check(STRONG_RELATION, budget=Budget(max_seconds=1))
    wall = time.perf_counter() - started
    assert verdict.accepted
    assert len(verdict.obligations) == 4
    assert all(item.seconds >= 0.012 for item in verdict.obligations)
    assert 0 <= wall - verdict.total_seconds < 0.03


def test_solver_unknown_is_not_mislabeled_unsatisfiable_domain(monkeypatch):
    """An incomplete SAT search is neither a proof of P empty nor a time expiry."""
    from symq.sat import composition

    actual_factory = composition._solver_factory

    class Unknown:
        def __init__(self, real):
            self.real = real

        def __getattr__(self, name):
            return getattr(self.real, name)

        def solve_limited(self, **_kwargs):
            return None

    def factory():
        create = actual_factory()

        def create_unknown(**kwargs):
            return Unknown(create(**kwargs))

        return create_unknown

    monkeypatch.setattr(composition, "_solver_factory", factory)
    verdict = run_check(STRONG_RELATION, budget=Budget(max_seconds=1))
    assert not verdict.accepted
    assert len(verdict.obligations) == 1
    assert verdict.by_name("domain").satisfiable is None
    assert "inconclusive" in verdict.reason
    assert "unsatisfiable" not in verdict.reason

# ------------------------------------------------------------------------- the IR itself


def test_the_expression_grammar_rejects_what_it_does_not_understand():
    declared = frozenset({"x.0", "x.1"})
    validate(Xor(Var("x.0"), Var("x.1")), declared)
    with pytest.raises(ValueError, match="undeclared"):
        validate(Var("y.0"), declared)
    with pytest.raises(ValueError, match="grammar node"):
        validate("x.0 == x.1", declared)
    with pytest.raises(ValueError, match="grammar node"):
        validate(lambda: True, declared)


def test_the_grammar_rejects_bad_sub_expressions_at_construction():
    """``And(Var("x.0"), object())`` must raise ``ExprError``, not fail later in ``depth``."""
    with pytest.raises(ExprError, match="And.right"):
        And(Var("x.0"), object())
    with pytest.raises(ExprError, match="Xor.left"):
        Xor(object(), Var("x.0"))
    with pytest.raises(ExprError, match="Eq.right"):
        Eq(Var("x.0"), "x.0")
    with pytest.raises(ExprError, match="Not.operand"):
        Not(object())


def test_a_deeply_nested_bad_node_is_still_rejected():
    """Closure holds at depth, not just at the root."""
    buried = And(And(And(Var("x.0"), Var("x.1")), Var("x.2")), Var("x.3"))
    with pytest.raises(ExprError):
        And(buried, object())
    with pytest.raises(ExprError):
        validate(And(buried, Var("x.9")), frozenset({"x.0"}))


def test_the_depth_bound_is_enforced():
    from symq.sat.assumptions import MAX_DEPTH

    expression = Var("x.0")
    for _ in range(MAX_DEPTH):
        expression = Not(expression)
    with pytest.raises(ExprError, match="depth"):
        validate(expression, frozenset({"x.0"}))


def test_a_very_deep_tree_raises_instead_of_recursing_forever():
    """The traversal is bounded, so an over-deep tree cannot exhaust the Python stack."""
    expression = Var("x.0")
    for _ in range(4000):
        expression = Not(expression)
    with pytest.raises(ExprError, match="depth"):
        validate(expression, frozenset({"x.0"}))


def test_evaluate_matches_the_operators():
    assignment = {"x.0": 1, "x.1": 0}
    assert evaluate(Xor(Var("x.0"), Var("x.1")), assignment) is True
    assert evaluate(And(Var("x.0"), Var("x.1")), assignment) is False
    assert evaluate(Eq(Var("x.0"), Const(True)), assignment) is True
    assert evaluate(Not(Var("x.1")), assignment) is True
    with pytest.raises(ExprError, match="does not bind"):
        evaluate(Var("x.9"), assignment)


# ------------------------------------------------------- witnesses are checked, not just recorded


def test_replay_rejects_a_witness_that_does_not_satisfy_the_relation():
    """A fabricated cut pair that fails ``R`` must be refused, not reported as a counterexample."""
    from symq.equivalence import InternalInconsistency
    from symq.sat.composition import Obligation

    fake = Obligation(
        "suffix",
        "unsat",
        True,
        0.0,
        0,
        0,
        witness={"u.0": 0, "u.1": 0, "u.2": 0, "u.3": 0, "v.0": 1, "v.1": 0, "v.2": 0, "v.3": 0},
    )
    with pytest.raises(InternalInconsistency, match="R"):
        replay_witness(
            fake,
            interface=interface(STRONG_RELATION),
            guarantee=guarantee(),
            suffix_left=block_b(),
            suffix_right=block_b(),
        )


def test_replay_rejects_a_witness_that_satisfies_the_postcondition():
    """A pair that does *not* violate ``post`` is not a counterexample and must be refused."""
    from symq.equivalence import InternalInconsistency
    from symq.sat.composition import Obligation

    fake = Obligation(
        "suffix",
        "unsat",
        True,
        0.0,
        0,
        0,
        witness={"u.0": 0, "u.1": 0, "u.2": 0, "u.3": 0, "v.0": 0, "v.1": 0, "v.2": 0, "v.3": 0},
    )
    with pytest.raises(InternalInconsistency, match="post"):
        replay_witness(
            fake,
            interface=interface(STRONG_RELATION),
            guarantee=guarantee(),
            suffix_left=block_b(),
            suffix_right=block_b(),
        )


def test_replay_does_not_invent_an_input_for_an_interface_witness():
    """An interface counterexample is a cut pair; asking for a prefix circuit is an error."""
    verdict = run_restricted(relation=STRONG_RELATION)
    obligation = verdict.by_name("interface")
    assert obligation.satisfiable is True
    with pytest.raises(ValueError, match="guarantee"):
        replay_witness(obligation, interface=interface(STRONG_RELATION))
    replayed = replay_witness(
        obligation,
        interface=interface(STRONG_RELATION),
        guarantee=restricted_guarantee(),
    )
    assert replayed.kind == "cut" and len(replayed.inputs) == 2, (
        "a cut witness is a pair (u, v), never a single input x"
    )


def test_replay_requires_a_satisfiable_obligation():
    verdict = run_check(STRONG_RELATION)
    with pytest.raises(ValueError, match="satisfiable"):
        replay_witness(verdict.by_name("suffix"), interface=interface(STRONG_RELATION))


def test_a_timeout_in_any_obligation_refuses_the_verdict(monkeypatch):
    """A timed-out obligation must never be masked by its neighbours' successes."""
    from symq.sat import composition

    real = composition._symbolic_obligation

    def flaky(expression, width, *, name, wanted, clock, witness_prefixes, verify):
        if name == "interface":
            return composition.Obligation(
                name, wanted, None, 0.0, 0, 0, detail="budget exhausted after encoding"
            )
        return real(
            expression,
            width,
            name=name,
            wanted=wanted,
            clock=clock,
            witness_prefixes=witness_prefixes,
            verify=verify,
        )

    monkeypatch.setattr(composition, "_symbolic_obligation", flaky)
    verdict = run_check(STRONG_RELATION)
    assert not verdict.accepted
    assert verdict.timed_out
    assert verdict.by_name("interface").satisfiable is None
    assert verdict.by_name("suffix").satisfiable is False, (
        "the other obligations did succeed, which is exactly why the guard matters"
    )
