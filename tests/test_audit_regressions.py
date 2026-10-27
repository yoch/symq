"""Proposed RED regression tests for yoch/symq @ 5bfd6f0f482968a762d26ac056fabf61fa4e6489.

Copy into symq/tests/, run `python -m pytest -q tests/test_audit_regressions.py`.
These tests were prepared from inspected remote source, NOT run against that exact
package in this audit environment (GitHub DNS inaccessible in the container).
Each test expresses intended behavior after a fix and is expected to fail on main.
"""
import pytest

from symq import ANF, Budget, Circuit, make_algebra, simulate
from symq.circuit import UnsupportedOperation
from symq.phase import Op, PhaseProgram, check_phase_equivalence, phase_semantics
from symq.qasm import parse_qasm
from symq.resources import ResourceLimitExceeded


def test_phase_rejects_negative_feedforward_outcome_without_measurement():
    bad = PhaseProgram(1, 0, [Op("mcz_if", (0,), outcome=-1)])
    good = PhaseProgram(1).z(0)
    with pytest.raises((ValueError, UnsupportedOperation)):
        check_phase_equivalence(bad, good)


def test_phase_rejects_hmr_with_outcome_index_not_matching_order():
    bad = PhaseProgram(1, 1, [Op("mcx", (0, 1)), Op("hmr", (1,), outcome=1)])
    good = PhaseProgram(1)
    with pytest.raises((ValueError, UnsupportedOperation)):
        check_phase_equivalence(bad, good)


def test_phase_revalidates_operations_after_mutation():
    bad = PhaseProgram(1).z(0)
    bad.ops.append(Op("mcz_if", (0,), outcome=-1))
    with pytest.raises((ValueError, UnsupportedOperation)):
        check_phase_equivalence(bad, PhaseProgram(1))


def test_qasm_unknown_include_rejected():
    text = 'OPENQASM 3.0; include "missing_nonstandard.inc"; qubit[1] q; x q[0];'
    with pytest.raises((ValueError, UnsupportedOperation)):
        parse_qasm(text)


def test_packed_fallback_products_are_counted_once():
    # A degree-3 control product forces the packed->sparse fallback.
    circuit = Circuit(4).mcx(0, 1, 2, 3)
    algebra = make_algebra("packed-fallback", circuit.width)
    simulate(circuit, algebra)
    assert algebra.stats.products == 1


def test_packed_fallback_public_product_updates_statistics():
    algebra = make_algebra("packed-fallback", 3)
    factors = [algebra.variable(i) for i in (0, 1)]
    result = algebra.product(factors)
    assert not algebra.is_zero(result)
    assert algebra.stats.products == 1


def test_anf_constructor_preserves_immutability():
    original = {1}
    value = ANF(original)
    original.add(0)
    assert value.terms == frozenset({1})


def test_packed_intermediate_monomial_budget_takes_precedence():
    # This is an explicit-monomial temporary, even though final degree>2.
    k = 10
    algebra = make_algebra("packed", 2*k, Budget(max_terms=16))
    factors = [algebra.xor(algebra.variable(i), algebra.variable(i+k)) for i in range(k)]
    with pytest.raises(ResourceLimitExceeded) as exc:
        algebra.product(factors)
    assert exc.value.resource == "terms", (
        "The packed materialization should not build 2**k explicit terms then "
        "report only a post-hoc degree overflow."
    )


# --- Contract coverage added with the fixes (not part of the original red tests) ---

@pytest.mark.parametrize("backend", ["reference", "sparse-copy", "sparse", "zdd", "zdd-native",
                                     "truthtable", "packed", "packed-fallback",
                                     "adaptive-wire", "auto-zdd"])
@pytest.mark.parametrize("index", [-1, 4, 2**31])
def test_variable_index_is_validated_by_every_backend(backend, index):
    algebra = make_algebra(backend, 4)
    with pytest.raises((ValueError, IndexError)):
        algebra.variable(index)


@pytest.mark.parametrize("backend", ["sparse", "zdd", "zdd-native", "reference", "packed"])
def test_variable_index_type_is_validated(backend):
    with pytest.raises(TypeError):
        make_algebra(backend, 3).variable(True)


@pytest.mark.parametrize(
    "ops",
    [
        pytest.param([Op("mcz", (0, 0))], id="duplicate-qubit"),
        pytest.param([Op("mcz", (-1,))], id="negative-qubit"),
        pytest.param([Op("mcz", (3,))], id="out-of-range"),
        pytest.param([Op("hmr", (0, 1), 0)], id="two-qubit-hmr"),
        pytest.param([Op("mcz_if", (0,), 0)], id="feed-forward-before-measurement"),
        pytest.param([Op("hmr", (0,), 7)], id="wrong-outcome-index"),
        pytest.param([Op("h", (0,))], id="outside-fragment"),
        pytest.param([Op("mcx", (0,), 0)], id="mcx-with-outcome"),
    ],
)
def test_phase_program_validation_rejects_invalid_instructions(ops):
    with pytest.raises(UnsupportedOperation):
        check_phase_equivalence(PhaseProgram(2, 1, list(ops)), PhaseProgram(2))


def test_phase_validation_accepts_a_well_formed_feed_forward():
    # 3 data wires and one ancilla: the ancilla carries x0*x1, ``hmr`` resets it and the
    # feed-forward cancels the phase kickback. Validation must accept it, and the program
    # must then be equivalent to itself (so the certificate path ran on the parsed list).
    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    outcome = program.hmr(3)
    program.cz_if(outcome, 0, 1)
    assert phase_semantics(program).violations() == []
    assert check_phase_equivalence(program, program).equivalent is True


@pytest.mark.parametrize(
    "text",
    [
        'OPENQASM 3.0; include "qelib1.inc"; qubit[1] q; x q[0];',
        'OPENQASM 2.0; include "stdgates.inc"; qreg q[1]; x q[0];',
        'include "stdgates.inc"; OPENQASM 3.0; qubit[1] q; x q[0];',
        'qubit[1] q; x q[0];',
        'OPENQASM 3.0; OPENQASM 3.0; qubit[1] q; x q[0];',
    ],
)
def test_qasm_includes_and_headers_are_version_checked(text):
    with pytest.raises((ValueError, UnsupportedOperation)):
        parse_qasm(text)


def test_qasm_accepts_the_supported_includes():
    for text in (
        'OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\nx q[0];',
        'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[1];\nx q[0];',
    ):
        circuit = parse_qasm(text)
        assert circuit.width == 1 and circuit.gates[0].name == "x"


def test_packed_product_budget_stops_before_the_full_materialisation():
    """16 independent two-term factors would be 65 536 monomials; the budget must stop it."""
    k = 16
    algebra = make_algebra("packed", 2 * k, Budget(max_terms=32))
    factors = [algebra.xor(algebra.variable(i), algebra.variable(i + k)) for i in range(k)]
    with pytest.raises(ResourceLimitExceeded) as exc:
        algebra.product(factors)
    assert exc.value.resource in ("terms", "degree")
    observed = getattr(exc.value, "observed", 0)
    assert observed <= 65_536


@pytest.mark.parametrize("name", ["packed-fallback", "sparse", "zdd", "zdd-native"])
def test_products_are_counted_once_per_controlled_gate(name):
    """A controlled gate multiplies its controls once; a bare ``x`` multiplies nothing."""
    circuit = Circuit(4).x(0).mcx(0, 1, 2, 3).cx(1, 0).mcx(0, 1, 3).x(2)
    algebra = make_algebra(name, 4)
    simulate(circuit, algebra)
    assert algebra.stats.products == sum(1 for g in circuit.gates if len(g.qubits) > 1) == 3


def test_packed_fallback_products_match_controlled_gates_on_the_corpus():
    from pathlib import Path

    from symq.corpus import load_corpus

    manifest = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"
    for entry in load_corpus(manifest).entries:
        if not entry.supported:
            continue
        circuit = entry.load()
        algebra = make_algebra("packed-fallback", circuit.width)
        simulate(circuit, algebra)
        expected = sum(1 for gate in circuit.gates if len(gate.qubits) > 1)
        assert algebra.stats.products == expected, entry.name
