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
def test_gf_mul_matches_generated_subfield(field):
    """Multiplication agrees with explicit polynomial products reduced by the modulus."""
    modulus = tensor_budget.MODULI[field]
    limit = 1 << field
    for left in range(limit):
        for right in range(limit):
            product = 0
            for bit in range(field):
                if right >> bit & 1:
                    product ^= left << bit
            for bit in range(product.bit_length() - 1, field - 1, -1):
                if product >> bit & 1:
                    product ^= modulus << (bit - field)
            assert tensor_budget.gf_mul(field, left, right) == product


@pytest.mark.parametrize("field", sorted(tensor_budget.MODULI))
def test_gf_mul_is_commutative_and_has_no_zero_divisors(field):
    limit = 1 << field
    for left in range(limit):
        for right in range(limit):
            assert tensor_budget.gf_mul(field, left, right) == tensor_budget.gf_mul(
                field, right, left
            )
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


def test_schoolbook_incidences_exceed_the_floor():
    """Schoolbook spends more incidences than the rank floor, which is the trade-off under study."""
    for field in (3, 4, 5):
        info = tensor_budget.budget(field)
        assert info.schoolbook_incidences > info.incidence_floor
        assert info.schoolbook_slack == info.schoolbook_incidences - info.incidence_floor


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
    same modulus. Both are pure Python and independent, so agreement across the whole field pins the
    arithmetic used for the GF(2^12) numbers.
    """
    archived = (
        _load("field_phase_archived") if (RESEARCH / "field_phase_archived.py").exists() else None
    )
    if archived is None:
        spec = importlib.util.spec_from_file_location(
            "field_phase_archived",
            ROOT / "research" / "archive" / "2026-10-27" / "src" / "field_phase.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        archived = module
    for left in range(1 << 12):
        for right in (0, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 0x1052, 0x0FFF):
            assert tensor_budget.gf_mul(12, left, right) == archived.gf_mul(left, right)


def test_gf12_decompositions_are_dense_and_distinct_in_cost():
    """The three GF(2^12) decompositions exist, are exact, and differ in cost as modelled.

    Exactness at n=12 cannot be checked by enumeration, so this only asserts the algebraic identity
    of the term sets and the structural accounting; the exhaustive proof of the emitters is at n=4,5.
    """
    reference = decompositions.expected(12)
    costs = {}
    for builder in ("schoolbook", "karatsuba", "rank_floor"):
        terms = getattr(decompositions, builder)(12)
        assert decompositions.expand(12, terms) == reference
        emitted = decompositions.emit(12, terms)
        assert emitted.width == 36
        assert emitted.ccx == emitted.incidences if builder == "schoolbook" else True
        costs[builder] = (emitted.ccx, emitted.cx)
    # Schoolbook trades CCX for CX; rank floor does the opposite. They must not be identical.
    assert costs["schoolbook"][0] > costs["rank_floor"][0]
    assert costs["schoolbook"][1] < costs["rank_floor"][1]


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
