"""Tests for the XAG/reversible-synthesis research modules.

The private ``yoch/qant`` block these modules were meant to study is not readable from this
environment, so these tests pin properties of the GF(2^n) *function* and of the emitters built here.
They do not certify anything about qant.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from symq.circuit import Circuit

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research" / "xag-synthesis"


def _load(name: str):
    """Import a research module by path, with its sibling directory on ``sys.path``.

    The modules import each other by bare name (``from tensor_budget import ...``), so the directory
    has to be importable before the spec is executed.
    """
    if str(RESEARCH) not in sys.path:
        sys.path.insert(0, str(RESEARCH))
    spec = importlib.util.spec_from_file_location(name, RESEARCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tensor_budget = _load("tensor_budget")
decompositions = _load("decompositions")


@pytest.mark.parametrize("field", sorted(tensor_budget.MODULI))
def test_pinned_moduli_are_irreducible(field):
    """A reducible modulus would make gf_mul a ring and invalidate the rank argument."""
    assert tensor_budget.is_irreducible(field)


@pytest.mark.parametrize("field", sorted(tensor_budget.MODULI))
def test_gf_mul_matches_an_independent_polynomial_product(field):
    """Multiplication agrees with explicit polynomial products reduced by the modulus.

    Every input pair is checked where the field is small enough to afford it. For GF(2^12) the full
    sweep is 2^24 pairs, which is too expensive for every CI job, so the sweep is replaced by
    (a) the complete set of single-bit operands, which pins the bilinear structure that the tensors
    are built from, and (b) a deterministic cover of mixed operands including the extremes.
    """
    modulus = tensor_budget.MODULI[field]

    def reference(left: int, right: int) -> int:
        product = 0
        for bit in range(field):
            if right >> bit & 1:
                product ^= left << bit
        for bit in range(product.bit_length() - 1, field - 1, -1):
            if product >> bit & 1:
                product ^= modulus << (bit - field)
        return product

    limit = 1 << field
    basis = [1 << bit for bit in range(field)]
    # Single-bit operands on both sides are exactly the tensor entries the bound is computed from.
    pairs = [(a, b) for a in basis for b in basis] + [(a, b) for b in basis for a in basis]
    if field <= 8:
        pairs = [(a, b) for a in range(limit) for b in range(limit)]
    else:
        edge = [0, 1, 2, limit - 1, limit - 2, modulus & (limit - 1), (limit - 1) >> 1]
        pairs += [(a, b) for a in edge for b in edge]
        pairs += [(a, a) for a in range(limit)]
    for left, right in pairs:
        assert tensor_budget.gf_mul(field, left, right) == reference(left, right), (left, right)


@pytest.mark.parametrize("field", sorted(tensor_budget.MODULI))
def test_gf_mul_is_a_field_with_nonzero_multiplication_a_bijection(field):
    """Fact 2 of the bound: GF(2^n) is a field, so ``b -> a*b`` is injective for ``a != 0``.

    This is the premise the rank theorem needs; it is checked exhaustively only where affordable, and
    sampled deterministically otherwise. The general argument is the field axiom, not this test.
    """
    limit = 1 << field
    if field <= 8:
        assert tensor_budget.nonzero_multiplication_is_a_bijection(field)
    else:
        for a in (1, 2, 3, limit - 1, limit - 2, 0x555, 0x0F0F):
            images = {tensor_budget.gf_mul(field, a, b) for b in range(limit)}
            assert len(images) == limit, a
    # Commutativity on the same bounded cover, plus the zero-divisor check the field forbids.
    mask = limit - 1
    cover = ((1, 2), (0xAA & mask, 0x55 & mask), (mask, mask), (3 & mask, 5 & mask))
    for left, right in cover:
        assert tensor_budget.gf_mul(field, left, right) == tensor_budget.gf_mul(field, right, left)
        if left and right:
            assert tensor_budget.gf_mul(field, left, right) != 0


@pytest.mark.parametrize("field", sorted(tensor_budget.MODULI))
def test_coordinate_slices_have_full_rank(field):
    """The core structural fact: every output coordinate has rank n over GF(2)."""
    info = tensor_budget.budget(field)
    assert info.coordinate_ranks == (field,) * field
    assert info.full_rank
    assert info.incidence_floor == field * field


def test_rank_algorithms_are_cross_checked():
    """``budget`` raises if the two independent rank computations ever disagree."""
    for field in sorted(tensor_budget.MODULI):
        slices = tensor_budget.coordinate_slices(field)
        for rows in slices:
            assert tensor_budget.rank_gaussian(rows, field) == tensor_budget.rank_incremental(rows)


def test_schoolbook_incidences_are_computed_independently_of_the_floor():
    """The schoolbook incidence count is recomputed from term masks, not restated from ``Budget``.

    ``schoolbook_slack == schoolbook_incidences - incidence_floor`` would be a definition, so the
    meaningful check is that the emitter's own term set independently reproduces the count that
    ``budget`` reports, and that it exceeds the floor.
    """
    for field in (3, 4, 5):
        info = tensor_budget.budget(field)
        terms = decompositions.schoolbook(field)
        assert len(terms) == info.schoolbook_terms
        assert sum(term.fanout_weight for term in terms) == info.schoolbook_incidences
        assert info.schoolbook_incidences > info.incidence_floor
        assert info.schoolbook_slack > 0


@pytest.mark.parametrize("field", (4, 5))
@pytest.mark.parametrize("builder", ("schoolbook", "karatsuba", "rank_floor"))
def test_decomposition_expands_to_the_true_tensor(field, builder):
    """Each term set denotes exactly GF(2^n) multiplication, checked algebraically."""
    terms = getattr(decompositions, builder)(field)
    assert decompositions.expand(field, terms) == decompositions.expected(field)


@pytest.mark.parametrize("field", (4, 5))
@pytest.mark.parametrize("builder", ("schoolbook", "karatsuba", "rank_floor"))
def test_emitted_circuit_is_exact_on_every_input(field, builder):
    """Exhaustive over every ``(a, b, z)``: a, b restored, z accumulates the product."""
    terms = getattr(decompositions, builder)(field)
    emitted = decompositions.emit(field, terms)
    assert decompositions.exhaustive_failures(field, emitted) == 0


@pytest.mark.parametrize("field", (4, 5))
@pytest.mark.parametrize("builder", ("schoolbook", "karatsuba", "rank_floor"))
def test_circuit_never_uses_more_than_three_n_wires(field, builder):
    """Zero scratch: width is exactly 3n on every emitted decomposition."""
    terms = getattr(decompositions, builder)(field)
    emitted = decompositions.emit(field, terms)
    assert emitted.width == 3 * field


@pytest.mark.parametrize("field", (4, 5))
def test_fanout_shortcut_is_rejected(field):
    """The mutant test the mission requires: a plausible optimisation must fail the check.

    Copying a product from one accumulator bit to another with CX is only sound when the source bit
    starts at zero. With a dirty accumulator it leaks junk, and the exhaustive check must say so.
    """
    terms = decompositions.schoolbook(field)
    invalid = decompositions.fanout_shortcut(field, terms)
    emitted = decompositions.Emitted(
        circuit=invalid,
        ccx=sum(1 for gate in invalid.gates if gate.name == "ccx"),
        cx=sum(1 for gate in invalid.gates if gate.name == "cx"),
        fold_cx=0,
        n=field,
        terms=len(terms),
        incidences=sum(term.fanout_weight for term in terms),
    )
    assert decompositions.exhaustive_failures(field, emitted) > 0


def test_cx_copies_junk_so_the_incidence_floor_is_not_a_cx_bound():
    """Guard against re-deriving a gate bound from the incidence floor.

    A CX copies the *whole* bit, junk included, so it cannot deliver a product to a second accumulator
    bit without also delivering the source bit's previous contents. That is precisely why
    ``sum |w_s| >= n^2`` constrains term sets but says nothing about CX.
    """
    circuit = Circuit(6)
    circuit.append("ccx", 0, 3, 4)
    circuit.append("ccx", 1, 3, 4)
    circuit.append("cx", 4, 5)
    for assignment in range(1 << 6):
        result = circuit.run(assignment)
        a0, a1, b1 = assignment & 1, (assignment >> 1) & 1, (assignment >> 3) & 1
        product = (a0 & b1) ^ (a1 & b1)
        z0 = (assignment >> 4) & 1
        z1 = (assignment >> 5) & 1
        assert (result >> 4) & 1 == z0 ^ product
        # The copy adds z0's whole value, not the product.
        assert (result >> 5) & 1 == z1 ^ (z0 ^ product)
    # On a clean accumulator (z0 = z1 = 0) the shortcut is sound, which is why it is tempting.
    for assignment in range(1 << 4):
        result = circuit.run(assignment)
        a0, a1, b1 = assignment & 1, (assignment >> 1) & 1, (assignment >> 3) & 1
        product = (a0 & b1) ^ (a1 & b1)
        assert (result >> 5) & 1 == product


@pytest.mark.parametrize("field", (4, 5, 6))
def test_minimum_distance_of_a_linear_code_is_not_assumed(field):
    """Sanity check that the tensor is dense: every entry is nonzero.

    A zero entry would mean a product is identically zero and could be dropped for free; that never
    happens in a field, which is why schoolbook costs the full n^2 terms.
    """
    table = tensor_budget.tensor(field)
    assert all(value != 0 for row in table for value in row)


def test_gf12_tensor_matches_the_archived_field_implementation():
    """Cross-check the GF(2^12) arithmetic against the archived qant handoff implementation.

    ``research/archive/2026-10-27/src/field_phase.py`` carries an independent ``gf_mul`` with the
    same modulus. Agreement on a deterministic cover pins the arithmetic used for the GF(2^12)
    numbers without sweeping all 2^24 pairs in every CI job; the tensor itself is built only from
    single-bit operands, which the cover includes exhaustively.
    """
    spec = importlib.util.spec_from_file_location(
        "field_phase_archived",
        ROOT / "research" / "archive" / "2026-10-27" / "src" / "field_phase.py",
    )
    archived = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archived)

    operands = [1 << bit for bit in range(12)]
    operands += [0, 1, 2, 3, 0x0FFF, 0x0FFE, 0x0555, 0x0AAA, 0x0800, 0x0001]
    operands += [0x800, 0x400, 0x200, 0x100, 0x0FF, 0x101, 0x7FF]
    for left in operands:
        for right in operands:
            assert tensor_budget.gf_mul(12, left, right) == archived.gf_mul(left, right), (
                left,
                right,
            )


def test_gf12_decompositions_differ_on_each_cost_axis():
    """The three GF(2^12) decompositions are exact and occupy different points on the Pareto front.

    Exactness at n=12 cannot be enumerated, so this asserts the algebraic identity of the term sets
    plus the structural accounting per axis. It deliberately does **not** rank them by an unweighted
    gate total: a Toffoli and a CNOT are not interchangeable, so ``CCX + CX`` is not a cost.
    """
    reference = decompositions.expected(12)
    table = {}
    for builder in ("schoolbook", "karatsuba", "rank_floor"):
        terms = getattr(decompositions, builder)(12)
        assert decompositions.expand(12, terms) == reference, builder
        emitted = decompositions.emit(12, terms)
        assert emitted.width == 36
        # The accounting in the emitter must agree with the gates it actually emitted.
        assert emitted.ccx == sum(1 for gate in emitted.circuit.gates if gate.name == "ccx")
        assert emitted.cx == sum(1 for gate in emitted.circuit.gates if gate.name == "cx")
        # Every term contributes exactly one CCX per accumulator bit it targets.
        assert emitted.ccx == emitted.incidences
        table[builder] = emitted

    # Schoolbook wins on CX (none) and loses on CCX; the rank floor does the opposite.
    assert table["schoolbook"].cx == 0
    assert table["schoolbook"].ccx > table["rank_floor"].ccx
    assert table["rank_floor"].cx > table["schoolbook"].cx
    # Karatsuba is strictly between them on CCX, which is the only axis it improves.
    assert table["rank_floor"].ccx < table["karatsuba"].ccx < table["schoolbook"].ccx
    # Depth is a real axis: schoolbook is the shallowest of the three here.
    assert table["schoolbook"].depth < table["rank_floor"].depth


proof = _load("proof")


@pytest.mark.parametrize("field", (4, 5))
@pytest.mark.parametrize("builder", ("schoolbook", "karatsuba", "rank_floor"))
def test_symbolic_proof_accepts_the_emitted_circuit(field, builder):
    """The ANF oracle and exhaustive enumeration must agree on the same circuits."""
    terms = getattr(decompositions, builder)(field)
    emitted = decompositions.emit(field, terms)
    assert decompositions.exhaustive_failures(field, emitted) == 0
    assert proof.prove_against_terms(field, emitted.circuit, terms).equivalent


@pytest.mark.parametrize("builder", ("schoolbook", "karatsuba", "rank_floor"))
def test_gf12_candidates_are_proved_equivalent(builder):
    """GF(2^12) cannot be enumerated (2^36 inputs); the ANF proof covers every input at once."""
    terms = getattr(decompositions, builder)(12)
    emitted = decompositions.emit(12, terms)
    assert emitted.width == 36
    result = proof.prove_against_terms(12, emitted.circuit, terms)
    assert result.equivalent, result
    assert result.wires_checked == 36


def test_reference_and_term_oracles_agree():
    """Two independent constructions of the expected function must produce identical ANFs."""
    for field in (4, 12):
        algebra = proof._algebra(3 * field)
        reference = proof.reference_outputs(field)
        for builder in ("schoolbook", "karatsuba", "rank_floor"):
            terms = getattr(decompositions, builder)(field)
            derived = proof.term_outputs(field, terms)
            assert all(algebra.equal(a, b) for a, b in zip(reference, derived)), (
                f"{builder} disagrees with the field-table oracle at n={field}"
            )


def test_mutant_missing_ccx_is_rejected_at_gf12():
    """Replay the mission's drop-a-CCX mutant: the proof must refuse it."""
    terms = decompositions.karatsuba(12)
    emitted = decompositions.emit(12, terms)
    gates = list(emitted.circuit.gates)
    index = next(i for i, gate in enumerate(gates) if gate.name == "ccx")
    del gates[index]
    mutant = Circuit(36, gates)
    result = proof.prove_against_terms(12, mutant, terms)
    assert not result.equivalent
    assert result.mismatches


def test_mutant_swapped_controls_is_rejected_at_gf12():
    """A control swap is a plausible typo that changes the function; it must be caught."""
    terms = decompositions.karatsuba(12)
    emitted = decompositions.emit(12, terms)
    gates = list(emitted.circuit.gates)
    index = next(i for i, gate in enumerate(gates) if gate.name == "ccx")
    qubits = list(gates[index].qubits)
    qubits[0] ^= 1
    qubits[1] ^= 1
    gates[index] = type(gates[index])("ccx", tuple(qubits))
    result = proof.prove_against_terms(12, Circuit(36, gates), terms)
    assert not result.equivalent


def test_mutant_dirty_accumulator_fanout_is_rejected_at_gf12():
    """The fan-out shortcut is only sound on a clean accumulator, so it must fail the proof."""
    terms = decompositions.karatsuba(12)
    invalid = decompositions.fanout_shortcut(12, terms)
    result = proof.prove_against_terms(12, invalid, terms)
    assert not result.equivalent


def test_broken_term_set_is_rejected():
    """Guard the guard: a term set that is not GF(2^n) multiplication must be refused outright."""
    terms = decompositions.schoolbook(12)
    damaged = list(terms)
    damaged[0] = type(damaged[0])(damaged[0].left, damaged[0].right, damaged[0].into ^ 1)
    circuit = decompositions.emit(12, damaged).circuit
    with pytest.raises(AssertionError):
        proof.prove_against_terms(12, circuit, damaged)


# ------------------------------------------------------- the bound's scope is enforced by the API


def test_gf_mul_rejects_operands_outside_the_field():
    """A value >= 2^n is not a field element, so it must raise rather than be truncated.

    Silently masking would return the product of a different operand than the caller passed, which
    is exactly how a wrong table can look correct.
    """
    with pytest.raises(ValueError, match="must be in"):
        tensor_budget.gf_mul(12, 0x1000, 1)
    with pytest.raises(ValueError, match="must be in"):
        tensor_budget.gf_mul(12, 1, 0x1053)
    with pytest.raises(ValueError, match="must be in"):
        tensor_budget.gf_mul(4, -1, 1)
    assert tensor_budget.gf_mul(12, 0x0FFF, 1) == 0x0FFF


def test_the_incidence_floor_is_attained_by_the_rank_floor_construction():
    """The bound is tight for this decomposition, which is why it is called a floor.

    This is a property assertion, not a restatement: the rank-floor term set spends exactly ``n^2``
    incidences, and the bound says nothing can spend fewer.
    """
    for field in (4, 5):
        terms = decompositions.rank_floor(field)
        spent = sum(term.fanout_weight for term in terms)
        assert spent == field * field
        assert spent == tensor_budget.budget(field).incidence_floor


def test_the_bound_is_not_a_gate_bound():
    """Explicit statement of the scope: three gates deliver two incidences to one wire.

    ``sum |w_s| >= n^2`` counts (term, accumulator-bit) incidences. A CX copies its whole control bit,
    so a single gate can push every term sitting on that wire to another wire. Any argument turning
    the incidence floor into a CCX/CX/T bound would have to explain why this program is impossible,
    and it is not.
    """
    circuit = Circuit(5)
    circuit.append("ccx", 0, 2, 3)  # w   ^= a0 b0
    circuit.append("ccx", 1, 2, 3)  # w   ^= a1 b0
    circuit.append("cx", 3, 4)  # z0  ^= w     <- both terms, in one gate
    assert len(circuit.gates) == 3
    for assignment in range(1 << 5):
        result = circuit.run(assignment)
        a0, a1, b0 = assignment & 1, (assignment >> 1) & 1, (assignment >> 2) & 1
        product = (a0 & b0) ^ (a1 & b0)
        w_in = (assignment >> 3) & 1
        z_in = (assignment >> 4) & 1
        assert (result >> 3) & 1 == w_in ^ product
        # The single CX delivers *both* terms at once, plus the junk that was on w.
        assert (result >> 4) & 1 == z_in ^ w_in ^ product


def test_the_three_gf12_decompositions_are_pareto_incomparable():
    """No decomposition dominates another on (CCX, CX, width, depth).

    This pins the exact relation the report relies on. It also guards against the error the audit
    caught: claiming one construction is "worse in total" than another by summing CCX and CX, which
    prices a Toffoli and a CNOT the same.
    """
    table = {}
    for builder in ("schoolbook", "karatsuba", "rank_floor"):
        emitted = decompositions.emit(12, getattr(decompositions, builder)(12))
        table[builder] = (emitted.ccx, emitted.cx, emitted.width, emitted.depth)

    def dominates(first, second):
        return all(a <= b for a, b in zip(first, second)) and any(
            a < b for a, b in zip(first, second)
        )

    for left_key, left_axes in table.items():
        for right_key, right_axes in table.items():
            if left_key == right_key:
                continue
            assert not dominates(left_axes, right_axes), f"{left_key} dominates {right_key}"

    # And the specific relations the report states, asserted individually.
    assert table["schoolbook"][1] == 0, "schoolbook has no fold CX"
    assert table["rank_floor"][0] < table["schoolbook"][0], "rank floor uses fewer CCX"
    assert table["karatsuba"][0] < table["schoolbook"][0], "karatsuba uses fewer CCX"
    assert table["karatsuba"][1] < table["rank_floor"][1], "karatsuba uses fewer CX"
    assert table["schoolbook"][3] < table["rank_floor"][3], "schoolbook is shallower"
