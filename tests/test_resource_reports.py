"""An ``inconclusive`` research result says which limit it reached, and with what.

A downstream report on 0.2.0 found an affine table check stopped at 1,002,598 products
for a limit of 1,000,000, with only ``reason="products"`` to go on, and clean-ancilla
checks that returned no counters at all. Each cap is exercised here on synthetic
fixtures: the result names the resource, the limit and the count when it stopped, the
parameter that controls it, and the limits of the call; and for a cap set one below what
the fixture needs, raising it to the reported count lets the same call conclude.
"""
from __future__ import annotations

import pytest

from benchmarks.affine_table import wide_fixture
from benchmarks.anchored_kraus import chain
from symq import Circuit
from symq.errors import ResourceLimitExceeded
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs.affine_table import verify_affine_table
from symq.labs.anchored_kraus import Limit, verify
from symq.labs.anchored_stream import verify_stream
from symq.labs.backward_ancilla import AncillaLimits, check_clean_ancilla, replay_clean_ancilla
from symq.labs.resource_report import PARAMETERS, resource_report
from symq.labs.shared_table import SharedTable, verify_shared_table
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal
from symq.resources import Budget, VerificationSession

REPORT = ("resource", "limit", "observed", "hint", "limits")


@pytest.fixture(scope="module")
def wide():
    source, contract = wide_fixture()
    anf = verify_affine_table(source, contract)
    sat = verify_affine_table(source, contract, backend="sat") if _has_sat() else None
    return source, contract, anf, sat


def _has_sat():
    try:
        import pysat  # noqa: F401
    except ImportError:
        return False
    return True


def _assert_stopped(result, resource, parameter, limit, observed):
    assert result["status"] == "inconclusive"
    assert result["obligation"] == "resources" and result["witness"] is None
    assert (result["resource"], result["limit"], result["observed"]) == (resource, limit, observed)
    assert result["hint"] == (f"stopped at {observed} with {parameter}={limit}; "
                              f"a larger {parameter} may conclude, or may not")
    assert result["limits"][parameter] == limit


# --- the table verifiers, one cap at a time ------------------------------------------------

@pytest.mark.parametrize(("counter", "parameter", "resource"), [
    ("products", "max_products", "products"),
    ("peak_terms", "max_terms", "terms"),
])
def test_an_anf_cap_one_below_the_need_stops_at_the_need(wide, counter, parameter, resource):
    source, contract, done, _ = wide
    assert done["status"] == "equivalent"
    need = done[counter]
    stopped = verify_affine_table(source, contract, **{parameter: need - 1})
    _assert_stopped(stopped, resource, parameter, need - 1, need)
    assert stopped["reason"] == (resource if resource == "products" else
                                 f"terms limit exceeded: observed {need}, limit {need - 1}")
    assert verify_affine_table(source, contract,
                               **{parameter: stopped["observed"]})["status"] == "equivalent"


@pytest.mark.sat
@pytest.mark.parametrize(("counter", "parameter", "resource"), [
    ("graph_nodes", "max_graph_nodes", "Boolean DAG nodes"),
    ("cnf_clauses", "max_clauses", "CNF clauses"),
])
def test_a_sat_cap_one_below_the_need_stops_at_the_need(wide, counter, parameter, resource):
    source, contract, _, done = wide
    assert done["status"] == "equivalent"
    need = done[counter]
    stopped = verify_affine_table(source, contract, backend="sat", **{parameter: need - 1})
    _assert_stopped(stopped, resource, parameter, need - 1, need)
    assert stopped["reason"] == resource
    assert verify_affine_table(source, contract, backend="sat",
                               **{parameter: stopped["observed"]})["status"] == "equivalent"


def test_the_limits_are_those_of_the_call_and_of_its_backend(wide):
    source, contract, _, _ = wide
    anf = verify_affine_table(source, contract, max_products=10, max_terms=777,
                              max_operations=5000, max_json_items=90000)
    assert anf["limits"] == {"max_terms": 777, "max_seconds": 10.0, "max_operations": 5000,
                             "max_json_items": 90000, "max_products": 10}
    with VerificationSession(Budget(max_terms=500)):
        inherited = verify_affine_table(source, contract, max_products=10)
    assert inherited["limits"]["max_terms"] == 500


@pytest.mark.sat
def test_a_sat_call_lists_its_own_limits(wide):
    source, contract, _, _ = wide
    sat = verify_affine_table(source, contract, backend="sat", max_graph_nodes=10,
                              max_clauses=123)
    assert sat["limits"] == {"max_terms": 100000, "max_seconds": 10.0, "max_operations": 100000,
                             "max_json_items": 1000000, "max_graph_nodes": 10,
                             "max_clauses": 123}


def test_the_structural_caps_report_their_counts(wide):
    source, contract, _, _ = wide
    operations = len(source["ops"])
    _assert_stopped(verify_affine_table(source, contract, max_operations=10),
                    "operations", "max_operations", 10, operations)
    _assert_stopped(verify_affine_table(source, contract, max_json_items=100),
                    "JSON items", "max_json_items", 100, 101)


def test_a_deadline_reports_seconds_and_its_parameter(wide):
    source, contract, _, _ = wide
    stopped = verify_affine_table(source, contract, max_seconds=1e-9)
    assert stopped["status"] == "inconclusive" and stopped["resource"] == "seconds"
    assert 0 < stopped["limit"] < stopped["observed"]
    assert stopped["hint"].endswith("a larger max_seconds may conclude, or may not")


@pytest.mark.parametrize("check", ["verify", "anf", pytest.param("sat", marks=pytest.mark.sat)])
def test_every_table_verifier_reports_the_same_way(check):
    source, contract = chain(4)
    run = {"verify": lambda **kw: verify(source, contract, **kw),
           "anf": lambda **kw: verify_stream(source, contract, **kw),
           "sat": lambda **kw: verify_stream(source, contract, backend="sat", **kw)}[check]
    assert run()["status"] == "equivalent"
    stopped = run(max_json_items=10)
    _assert_stopped(stopped, "JSON items", "max_json_items", 10, 11)
    assert stopped["reason"] == "JSON items"
    if check != "sat":
        need = run()["products"]
        _assert_stopped(run(max_products=need - 1), "products", "max_products", need - 1, need)


def test_the_reference_verifier_lists_its_limits():
    source, contract = chain(1)
    stopped = verify(source, contract, max_json_items=10, max_products=99, max_terms=55)
    assert stopped["limits"] == {"max_terms": 55, "max_products": 99, "max_seconds": 10.0,
                                 "max_operations": 100000, "max_json_items": 10}


def test_the_shared_transport_reports_its_own_exhaustion():
    """A deadline that ends the outer session (not the inner affine check) is reported too."""
    table = SharedTable.from_rows([0] * 4, address_bits=2, target_bits=1)
    contract = {"kind": "symq_shared_affine_table_contract", "schema_version": 3, "width": 3,
                "address_wires": [0, 1], "target_wires": [2], "clean_wires": [],
                "borrowed_wires": [], "table": table.to_dict(),
                "address_domain": PredicateValues.below(2, 4).to_dict(),
                "target_space": {"kind": "affine_image", "offset": 0, "columns": [1]},
                "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}
    source = program_to_dict(HybridProgram(3, 0))
    assert verify_shared_table(source, contract)["status"] == "equivalent"
    result = verify_shared_table(source, contract, budget=Budget(absolute_deadline=0))
    assert result["status"] == "inconclusive" and result["obligation"] == "resources"
    assert result["witness"] is None and result["resource"] == "seconds"
    assert result["limit"] == 0.0
    assert result["hint"] == ("the deadline had already passed when this computation started; "
                              "controlled by max_seconds")
    assert result["limits"] == {"max_terms": None, "max_seconds": None}
    assert result["actual_context_preparation_proved"] is False
    assert result["reason"].startswith("seconds limit exceeded")


# --- the clean-ancilla checkers -------------------------------------------------------------

def _compute_uncompute() -> HybridProgram:
    program = HybridProgram(4, 2)
    for a, b, t in ((0, 1, 4), (2, 4, 5), (3, 5, 4), (3, 5, 4), (2, 4, 5), (0, 1, 4)):
        program.ccx(a, b, t)
    return program


def test_a_pauli_cap_one_below_the_need_stops_at_the_need():
    program = _compute_uncompute()
    done = check_clean_ancilla(program, 4)
    assert done.clean
    need = done.pauli_products
    stopped = check_clean_ancilla(program, 4, limits=AncillaLimits(max_products=need - 1))
    assert stopped.status == "inconclusive"
    assert stopped.certificate is None and stopped.witness is None
    assert (stopped.resource, stopped.limit, stopped.observed) == ("pauli_products", need - 1, need)
    assert stopped.pauli_products == need and stopped.peak_terms == done.peak_terms
    assert stopped.checked_operations == done.checked_operations
    assert stopped.hint == (f"stopped at {need} with AncillaLimits.max_products={need - 1}; "
                            "a larger AncillaLimits.max_products may conclude, or may not")
    assert stopped.limits["max_products"] == need - 1 and stopped.limits["max_terms"] == 4096
    assert stopped.reason == f"pauli_products limit exceeded: observed {need}, limit {need - 1}"
    assert check_clean_ancilla(program, 4,
                               limits=AncillaLimits(max_products=stopped.observed)).clean


def test_a_pauli_term_cap_and_a_width_cap_are_reported():
    program = _compute_uncompute()
    peak = check_clean_ancilla(program, 4).peak_terms
    terms = check_clean_ancilla(program, 4, budget=Budget(max_terms=peak - 1))
    assert (terms.resource, terms.limit, terms.observed) == ("terms", peak - 1, peak)
    assert terms.limits["max_terms"] == peak - 1 and terms.pauli_products > 0
    width = check_clean_ancilla(program, 4, limits=AncillaLimits(max_width=3))
    assert (width.resource, width.limit, width.observed) == ("width", 3, 6)
    assert width.hint.startswith("stopped at 6 with AncillaLimits.max_width=3")
    assert width.pauli_products == 0 and width.checked_operations == 0  # stopped, not unknown


def test_a_replay_reports_the_same_way():
    program = _compute_uncompute()
    done = check_clean_ancilla(program, 4)
    need = done.pauli_products
    stopped = replay_clean_ancilla(program, done.certificate,
                                   limits=AncillaLimits(max_products=need - 1))
    assert (stopped.status, stopped.resource, stopped.observed) == ("inconclusive",
                                                                    "pauli_products", need)
    assert stopped.pauli_products == need and stopped.certificate is None


def test_a_shift_diagonal_cap_one_below_the_need_stops_at_the_need():
    program = _compute_uncompute()
    done = check_shift_diagonal(program, 4)
    assert done.status == "clean"
    need = done.products
    stopped = check_shift_diagonal(program, 4, limits=AncillaLimits(max_products=need - 1))
    assert stopped.status == "inconclusive" and stopped.assignment is None
    assert stopped.source_sha256 is None and stopped.probability is None
    assert (stopped.resource, stopped.limit, stopped.observed) == ("polynomial_products",
                                                                  need - 1, need)
    assert stopped.products == need and stopped.checked_operations == done.checked_operations
    assert stopped.peak_terms is not None and stopped.peak_shifts is not None
    assert stopped.promotions is not None and stopped.limits["max_products"] == need - 1
    assert stopped.hint.startswith(f"stopped at {need} with AncillaLimits.max_products=")
    assert check_shift_diagonal(program, 4,
                                limits=AncillaLimits(max_products=need)).status == "clean"


def test_a_conclusive_ancilla_result_carries_no_report():
    program = _compute_uncompute()
    for result in (check_clean_ancilla(program, 4), check_shift_diagonal(program, 4)):
        assert (result.resource, result.limit, result.observed, result.hint,
                result.limits) == (None,) * 5


# --- the report itself ----------------------------------------------------------------------

def test_a_structured_limit_keeps_its_text():
    error = Limit("products", 10, 12)
    assert str(error) == "products"
    assert (error.resource, error.limit, error.observed) == ("products", 10, 12)
    assert str(Limit("deadline")) == "deadline" and Limit("deadline").limit is None


def test_report_fields_for_each_kind_of_error():
    assert resource_report(Limit("SAT deadline")) == {
        "resource": "SAT deadline", "limit": None, "observed": None,
        "hint": "controlled by max_seconds"}
    assert resource_report(ResourceLimitExceeded("shared table JSON bytes", 2, 3))["hint"] == (
        "a fixed limit of this verifier")
    assert resource_report(ResourceLimitExceeded("seconds", 0.0, 1.0, "too late"))["hint"] == (
        "too late; controlled by max_seconds")
    unknown = resource_report(ValueError("something else"), {"max_terms": 3})
    assert unknown == {"resource": "something else", "limit": None, "observed": None,
                       "hint": None, "limits": {"max_terms": 3}}


def test_every_resource_an_engine_names_has_a_parameter():
    for name in ("products", "terms", "Boolean DAG nodes", "CNF clauses", "operations",
                 "JSON items", "deadline", "seconds", "SAT deadline",
                 "SAT undecided or interrupted", "pauli_products", "polynomial_products",
                 "width", "gate_qubits", "classical_slots"):
        assert name in PARAMETERS


def test_a_graph_counts_its_nodes_as_its_metric_does():
    """Both node checks report the count ``metrics()`` calls ``graph_nodes``."""
    from symq.labs.kraus_graph import Graph
    from symq.resources import Guard

    graph = Graph(Guard(Budget()), max_nodes=3)
    graph.var(0)
    graph.var(1)
    assert graph.metrics()["graph_nodes"] == 3
    with pytest.raises(Limit) as adding:
        graph.var(2)
    assert (adding.value.limit, adding.value.observed) == (3, 4)
    graph.max_nodes = 2  # the defensive check, reached only if a node slipped past _node
    with pytest.raises(Limit) as checking:
        graph.check()
    assert (checking.value.limit, checking.value.observed) == (2, 3)


def test_the_limits_given_are_copied():
    limits = {"max_terms": 3}
    report = resource_report(Limit("terms", 3, 4), limits)
    limits["max_terms"] = 99
    assert report["limits"] == {"max_terms": 3}


# --- the stable SAT check: limits it does not apply are named -------------------------------

def _pair(different: bool):
    left, right = Circuit(3), Circuit(3)
    left.ccx(0, 1, 2)
    right.ccx(1, 0, 2)
    if different:
        right.x(2)
    return left, right


@pytest.mark.sat
@pytest.mark.parametrize("different", [False, True])
def test_sat_names_the_limits_it_ignores_without_changing_the_verdict(different):
    from symq.sat import check_sat_equivalence

    left, right = _pair(different)
    plain = check_sat_equivalence(left, right)
    assert plain.ignored_limits == ()
    capped = check_sat_equivalence(left, right, budget=Budget(max_terms=1, max_bytes=1))
    assert capped.outcome == plain.outcome == ("different" if different else "equivalent")
    assert capped.ignored_limits == ("max_terms", "max_bytes")
    with VerificationSession(Budget(max_nodes=1)):
        inherited = check_sat_equivalence(left, right, budget=Budget(max_seconds=60))
    assert inherited.outcome == plain.outcome and inherited.ignored_limits == ("max_nodes",)
    assert check_sat_equivalence(left, right,
                                 budget=Budget(max_seconds=60)).ignored_limits == ()
