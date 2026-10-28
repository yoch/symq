"""A worked two-block composition, and the mutants that must break it.

The example is deliberately tiny and self-contained -- no qant circuit is copied, since
``yoch/qant`` is private and the issue forbids importing its raw circuits without authorization.

Circuit, width 4, wires ``x0 x1 x2 x3``:

* block ``A``: ``ccx(x0, x1, x2)`` -- the AND of ``x0`` and ``x1`` lands on ``x2``;
* block ``B``: ``cx(x2, x3)``      -- propagates ``x2`` to ``x3``.

The cut after ``A`` carries ``x2 = x0 AND x1``, which is what ``B`` reads. A candidate ``A'`` may
compute that AND differently -- here through a scratch wire ``x3`` that it restores -- so the two
prefixes leave **different** cut states on ``x3`` while agreeing on everything ``B`` reads. That is
the case the issue asks for: an interface *relation*, not wire-by-wire equality.

    R(u, v)  :=  u.x2 = v.x2   (the only wire B reads)

Everything else is checked against concrete execution, which shares no code with the SAT encoding.
"""
from __future__ import annotations

import pytest

from symq import Budget, Circuit
from symq.sat import available
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor
from symq.sat.composition import (
    Guarantee,
    Interface,
    check_composition,
    replay_witness,
)

pytestmark = pytest.mark.skipif(not available(), reason="python-sat is not installed")

WIDTH = 4
READS_X2 = Eq(Var("u.2"), Var("v.2"))


def block_a() -> Circuit:
    """``x2 ^= x0 AND x1``."""
    return Circuit(WIDTH).ccx(0, 1, 2)


def block_a_with_scratch_junk() -> Circuit:
    """The same product, plus a flip of ``x3`` that the suffix never reads.

    This is the pair the issue asks for: the two prefixes leave *different* cut states (``x3``
    differs), so no wire-by-wire equality can relate them, yet they agree on everything the second
    block reads.
    """
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
    """``post``: the final states agree on the wires that carry information.

    Wire 3 is excluded because ``block_a_with_scratch_junk`` deliberately flips it and the suffix
    never reads it; a contract states which wires matter, which is what a partial-output obligation
    is for.
    """
    expression = And(Eq(Var("s.0"), Var("t.0")), Eq(Var("s.1"), Var("t.1")))
    expression = And(expression, Eq(Var("s.2"), Var("t.2")))
    return Guarantee(WIDTH, Const(True), expression)


def interface() -> Interface:
    return Interface(WIDTH, Const(True), READS_X2)


OBSERVED = (0, 1, 2)
"""Wires the contract observes; wire 3 is the scratch the variant flips and is excluded."""


def exhaustive(left: Circuit, right: Circuit) -> bool:
    """The contract's conclusion, by concrete execution: the observed wires agree on every input."""
    return all(((left.run(x) >> wire) & 1) == ((right.run(x) >> wire) & 1)
               for x in range(1 << WIDTH) for wire in OBSERVED)


def fully_identical(left: Circuit, right: Circuit) -> bool:
    """Every wire equal; used to show the pair is *not* identical, so the relation is doing work."""
    return all(left.run(x) == right.run(x) for x in range(1 << WIDTH))


# ------------------------------------------------------------------ the positive composition


def test_the_prefixes_establish_the_interface():
    """Obligation 1: under no input assumption, both prefixes agree on the wire B reads."""
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=interface(), guarantee=guarantee(), budget=Budget(max_seconds=20))
    prefix = verdict.by_name("prefix")
    assert prefix.ok, prefix
    assert prefix.satisfiable is False, "P and NOT R must be unsatisfiable"


def test_the_interface_implies_the_suffix_precondition():
    """Obligation 2: the relation is enough for B to run; here Pre_B is vacuous and must follow."""
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=interface(), guarantee=guarantee(), budget=Budget(max_seconds=20))
    assert verdict.by_name("interface").ok


def test_the_composition_is_accepted_and_agrees_with_concrete_execution():
    """The whole point: an accepted composition whose conclusion is true by brute force."""
    left = Circuit(WIDTH, [*block_a().gates, *block_b().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *block_b().gates])
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=interface(), guarantee=guarantee(), budget=Budget(max_seconds=20))
    assert verdict.accepted, [(o.name, o.satisfiable) for o in verdict.obligations]
    assert exhaustive(left, right), "the accepted conclusion must be true concretely"
    assert not fully_identical(left, right), (
        "the pair must differ somewhere, or the relation would be proving nothing")


def test_the_domain_query_is_reported_and_satisfiable():
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=interface(), guarantee=guarantee(), budget=Budget(max_seconds=20))
    domain = verdict.by_name("domain")
    assert domain.wanted == "sat" and domain.satisfiable is True, domain


# ------------------------------------------------------------------- the adversarial mutants


def test_a_prefix_that_corrupts_the_read_wire_is_rejected():
    """The mutant that must fail obligation 1: it writes to ``x2``, which ``B`` reads."""
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_wrong(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=interface(), guarantee=guarantee(), budget=Budget(max_seconds=20))
    assert not verdict.accepted
    prefix = verdict.by_name("prefix")
    assert prefix.satisfiable is True, "the counterexample must exist"
    assert prefix.witness, "and must be reported as an input assignment"
    value = replay_witness(block_a(), block_a_wrong(), prefix)
    assert block_a().run(value) != block_a_wrong().run(value)


def test_dropping_the_correlation_makes_a_false_composition_pass():
    """The soundness argument, tested: wire equality on the *unread* wire rejects a valid pair.

    ``block_a_via_scratch`` leaves ``x3`` different from ``block_a``. An interface that demanded
    equality on every wire -- including ``x3``, which the suffix never reads -- would reject the
    composition even though it is correct. The relation is strictly more useful than blind
    equality, and this test pins that.
    """
    every_wire = And(READS_X2, Eq(Var("u.3"), Var("v.3")))
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=Interface(WIDTH, Const(True), every_wire), guarantee=guarantee(),
        budget=Budget(max_seconds=20))
    assert not verdict.accepted, "full equality cannot relate two different cut states"
    assert verdict.by_name("prefix").satisfiable is True


def test_a_suffix_that_ignores_the_interface_relation_fails():
    """A candidate suffix whose output cannot follow from the relation is rejected."""
    broken_suffix = Circuit(WIDTH).cx(2, 3).x(3)
    left = Circuit(WIDTH, [*block_a().gates, *block_b().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *broken_suffix.gates])
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=broken_suffix,
        interface=interface(), guarantee=guarantee(), budget=Budget(max_seconds=20))
    assert not verdict.accepted
    assert verdict.by_name("composition").satisfiable is True
    assert not exhaustive(left, right), "and the rejected composition really is wrong"


# ------------------------------------------------------------- unsatisfiable preconditions


def test_an_unsatisfiable_precondition_is_refused_rather_than_certified():
    """``x0 AND NOT x0`` is never true, so every implication over it is vacuous.

    A checker that only ran the two implications would return ``accepted`` on an empty domain,
    which is the vacuous certificate the issue forbids.
    """
    contradictory = And(Var("x.0"), Not(Var("x.0")))
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_wrong(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=Interface(WIDTH, contradictory, READS_X2), guarantee=guarantee(),
        budget=Budget(max_seconds=20))
    assert not verdict.accepted
    domain = verdict.by_name("domain")
    assert domain.satisfiable is False
    assert "unsatisfiable" in verdict.reason
    assert len(verdict.obligations) == 1, "no implication is even attempted"


def test_a_satisfiable_precondition_is_not_refused():
    """The control: a constraint that can hold does not trip the vacuity check."""
    constraint = Eq(Var("x.0"), Const(True))
    verdict = check_composition(
        prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
        suffix_left=block_b(), suffix_right=block_b(),
        interface=Interface(WIDTH, constraint, READS_X2), guarantee=guarantee(),
        budget=Budget(max_seconds=20))
    assert verdict.by_name("domain").satisfiable is True


# ------------------------------------------------------------------------- the IR itself


def test_the_expression_grammar_rejects_what_it_does_not_understand():
    from symq.sat.assumptions import validate

    declared = frozenset({"x.0", "x.1"})
    validate(Xor(Var("x.0"), Var("x.1")), declared)
    with pytest.raises(ValueError, match="undeclared"):
        validate(Var("y.0"), declared)
    with pytest.raises(ValueError, match="closed grammar"):
        validate("x.0 == x.1", declared)
    with pytest.raises(ValueError, match="closed grammar"):
        validate(lambda: True, declared)


def test_the_depth_bound_is_enforced():
    from symq.sat.assumptions import MAX_DEPTH, ExprError, validate

    expression = Var("x.0")
    for _ in range(MAX_DEPTH):
        expression = Not(expression)
    with pytest.raises(ExprError, match="depth"):
        validate(expression, frozenset({"x.0"}))
