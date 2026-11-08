"""Support facts, borrowed graph restoration and independent tiny instruments."""
from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import replace
from itertools import permutations, product

import pytest
from test_kmb_window import _packets
from testkit.kraus_oracle import independent_kraus

pytest.importorskip("numpy")

from symq.errors import ResourceLimitExceeded
from symq.experimental.hybrid import HOp, HybridProgram
from symq.hashing import canonical_sha256
from symq.labs.kmb_affine_resources import (
    AffineResourceLimits,
    assess_affine_kmb_resources,
    replay_affine_kmb_resources,
)
from symq.labs.rewrite import ReceiptMismatch
from symq.resources import Budget


def setup(tmp_path, prefix=None, body=None, resource=None, suffix=()):
    prefix = prefix if prefix is not None else [(80, (2,), 0, None), (33, (0, 2), None, None)]
    body = body if body is not None else [(49, (0, 1, 3), None, None), (32, (0, 1), None, None)]
    source = tmp_path / "source.kmb"
    raw = _packets(*prefix, *body, *suffix)
    source.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    request = {"kind": "symq_kmb_affine_resources", "schema_version": 1,
        "source_file_sha256": pin, "analysis_window": [0, len(prefix)],
        "reservation_window": [len(prefix), len(prefix) + len(body)],
        "domain": "all_source_quantum_states_and_classical_values",
        "resources": [resource or {"wire": 2, "parents": [0], "constant": 0}]}
    return source, request


def pins(request):
    return {"expected_source_sha256": request["source_file_sha256"],
            "expected_request_sha256": canonical_sha256(request)}


def prove(source, request, **kw):
    return assess_affine_kmb_resources(source, request, **pins(request), **kw)


def test_borrowed_graph_is_not_misreported_as_an_initially_clean_wire(tmp_path):
    source, request = setup(tmp_path)
    result = prove(source, request)
    assert result["outcome"] == "proved" and result["usable_resources"] == [2]
    fact = result["facts"][0]
    assert fact["initial_cleanliness"] == "unknown"
    assert fact["relation"] == "proved"
    assert fact["preparation"] == fact["restoration"] == [["cx", 0, 2]]
    assert fact["borrowed_graph_and_correlations_restored_after_inverse_preparation"]
    assert not result["candidate_authorized"] and not result["global_substitution_proved"]
    assert "own fresh" in result["phase_scope"]
    assert replay_affine_kmb_resources(source, request, result, **pins(request)) == result
    # All original quantum and classical outputs observed, including an old HMR.
    prefix = [HOp("hmr", (2,), slot="b0"), HOp("cx", (0, 2))]
    body = [HOp("ccx", (0, 1, 3)), HOp("cz", (0, 1))]
    prep = [HOp("cx", (0, 2))]
    original = HybridProgram(4, 0, prefix + body)
    wrapped = HybridProgram(4, 0, prefix + prep + body + prep)
    for x, y in product(range(16), repeat=2):
        assert independent_kraus(original, x, y, ("b0",)) == independent_kraus(wrapped, x, y, ("b0",))


@pytest.mark.parametrize("mutation", ["wrong_parent", "assumed_clean", "product_overwritten",
                                      "resource_read", "parent_written", "phase_on_resource"])
def test_wrong_relations_and_interference_are_separate_obligations(tmp_path, mutation):
    prefix = [(80, (2,), 0, None), (33, (0, 2), None, None)]
    body = [(49, (0, 1, 3), None, None)]
    item = {"wire": 2, "parents": [0], "constant": 0}
    if mutation == "wrong_parent":
        item["parents"] = [1]
    elif mutation == "assumed_clean":
        item["parents"] = []
    elif mutation == "product_overwritten":
        prefix += [(17, (0,), None, None)]
    elif mutation == "resource_read":
        body += [(33, (2, 3), None, None)]
    elif mutation == "parent_written":
        body += [(17, (0,), None, None)]
    else:
        body += [(16, (2,), None, None)]
    source, request = setup(tmp_path, prefix, body, item)
    result = prove(source, request)
    assert result["outcome"] == "not_proved" and not result["usable_resources"]
    fact = result["facts"][0]
    if mutation in ("resource_read", "phase_on_resource"):
        assert fact["relation"] == "proved" and fact["reservation"] == "source_interference"
    elif mutation == "parent_written":
        assert fact["relation"] == "proved" and fact["parents_preserved"] == "source_interference"
    else:
        assert fact["relation"] == "not_proved"


def test_demonstrated_one_is_distinct_from_unknown_and_can_be_affinely_prepared(tmp_path):
    prefix = [(18, (2,), None, None), (17, (2,), None, None)]
    source, request = setup(tmp_path, prefix=prefix, resource={"wire": 2, "parents": [], "constant": 0})
    result = prove(source, request)
    assert result["outcome"] == "not_proved"
    assert result["facts"][0]["initial_cleanliness"] == "proved_one"
    request["resources"][0]["constant"] = 1
    result = prove(source, request)
    assert result["outcome"] == "proved"
    assert result["facts"][0]["preparation"] == [["x", 2]]


def test_support_proof_preserves_variables_outside_the_analysis_cone(tmp_path):
    source, request = setup(tmp_path, prefix=[(18, (2,), None, None)],
        resource={"wire": 2, "parents": [0], "constant": 0})
    # q0 has no writer in the analysis; it remains arbitrary, never implicit zero.
    assert prove(source, request)["outcome"] == "not_proved"
    request["resources"][0]["parents"] = []
    assert prove(source, request)["outcome"] == "proved"


@pytest.mark.parametrize("case", ["early_read", "defined_zero", "self_invert", "slot_reused"])
def test_classical_conditions_use_current_values_without_implicit_zero(tmp_path, case):
    prefix = [(18, (2,), None, None)]
    if case == "defined_zero":
        prefix += [(64, (), 0, None)]
    elif case == "self_invert":
        prefix += [(194, (), 0, 0)]  # b0 <- b0 XOR b0, independent of initial b0.
    elif case == "slot_reused":
        prefix += [(80, (2,), 0, None), (65, (), 0, None)]
    prefix += [(145, (2,), None, 0)]
    source, request = setup(tmp_path, prefix=prefix, resource={"wire": 2, "parents": [], "constant": 0})
    result = prove(source, request)
    assert result["outcome"] == ("proved" if case in ("defined_zero", "self_invert") else "not_proved")
    if case == "slot_reused":
        assert result["facts"][0]["initial_cleanliness"] == "proved_one"


def test_product_cancellation_and_boolean_idempotence_do_not_expand_terms(tmp_path):
    prefix = [(18, (2,), None, None), (49, (0, 1, 2), None, None), (49, (0, 1, 2), None, None)]
    source, request = setup(tmp_path, prefix=prefix, resource={"wire": 2, "parents": [], "constant": 0})
    assert prove(source, request)["outcome"] == "proved"
    prefix.insert(2, (17, (0,), None, None))
    source, request = setup(tmp_path, prefix=prefix, resource={"wire": 2, "parents": [], "constant": 0})
    assert prove(source, request)["outcome"] == "not_proved"


@pytest.mark.parametrize("change", ["mapping", "position", "domain", "old_source", "forged_receipt"])
def test_independent_pins_and_fresh_replay_reject_stale_content(tmp_path, change):
    source, request = setup(tmp_path)
    result = prove(source, request)
    changed = copy.deepcopy(request)
    if change == "mapping":
        changed["resources"][0]["parents"] = [1]
    elif change == "position":
        changed["analysis_window"][0] = 1
    elif change == "domain":
        changed["domain"] = "zero_inputs"
    elif change == "old_source":
        source.write_bytes(source.read_bytes() + b"changed suffix")
    else:
        result["facts"][0]["relation"] = "not_proved"
    with pytest.raises(ReceiptMismatch):
        replay_affine_kmb_resources(source, changed, result, **pins(request))


def test_expiration_and_representation_caps_clear_all_usable_facts(tmp_path, monkeypatch):
    source, request = setup(tmp_path)
    result = prove(source, request, budget=Budget(absolute_deadline=0))
    assert result["outcome"] == "inconclusive" and result["facts"] == []
    result = prove(source, request, limits=replace(AffineResourceLimits(), max_atoms=1))
    assert result["outcome"] == "inconclusive" and result["usable_resources"] == []
    import symq.labs.kmb_affine_resources as api

    def expired(*args):
        raise ResourceLimitExceeded("seconds", 1, 2)

    monkeypatch.setattr(api.frontier, "_dependencies", expired)
    result = prove(source, request)
    assert result["outcome"] == "inconclusive" and result["facts"] == []


def test_unsupported_source_instructions_and_condition_stacks_remain_explicit(tmp_path):
    source, request = setup(tmp_path, suffix=[(19, (0,), None, None)])
    assert prove(source, request)["outcome"] == "unsupported"
    prefix = [(129, (), None, 0), (18, (2,), None, None), (1, (), None, None)]
    source, request = setup(tmp_path, prefix=prefix, resource={"wire": 2, "parents": [], "constant": 0})
    assert prove(source, request)["outcome"] == "unsupported"


@pytest.mark.parametrize("change", ["duplicate", "alias", "bool_constant", "empty_domain", "unknown_key"])
def test_closed_requests_refuse_silent_domain_or_mapping_changes(tmp_path, change):
    source, request = setup(tmp_path)
    if change == "duplicate":
        request["resources"] *= 2
    elif change == "alias":
        request["resources"][0]["parents"] = [2]
    elif change == "bool_constant":
        request["resources"][0]["constant"] = False
    elif change == "empty_domain":
        request["domain"] = "empty"
    else:
        request["implicit_zeros"] = True
    if change == "empty_domain":
        assert prove(source, request)["outcome"] == "unsupported"
    else:
        with pytest.raises(ValueError):
            prove(source, request)


def test_support_dag_matches_independent_scalar_trajectories_for_every_tiny_input():
    from symq.labs.kmb_affine_resources import _Support
    from symq.resources import VerificationSession

    rng = random.Random(63011)
    program = []
    for _ in range(35):
        code = rng.choice((17, 18, 33, 34, 49, 50, 80, 64, 65, 66, 16, 32, 48))
        arity = (code & 48) // 16
        wires = tuple(rng.sample(range(4), arity))
        slot = rng.randrange(2) if code & 64 else None
        condition = rng.randrange(2) if rng.randrange(2) else None
        program.append((code | (128 if condition is not None else 0), wires, slot, condition))
    for initial in range(64):
        with VerificationSession(Budget(max_seconds=5)) as guard:
            support = _Support(4, guard, AffineResourceLimits())
            for slot in (0, 1):
                support.bit(slot)
            assignment = {i + 1: initial >> i & 1 for i in range(6)}
            state, memory = initial & 15, {0: initial >> 4 & 1, 1: initial >> 5 & 1}
            for code, qs, slot, condition in program:
                previous_atoms = support.atoms
                support.step(code, qs, slot, condition)
                products = {v: tuple(k) for k, v in support.products.items()}
                fresh = [i for i in range(previous_atoms + 1, support.atoms + 1) if i not in products]
                for i in fresh:
                    assignment[i] = rng.randrange(2)
                base = code & 127
                enabled = condition is None or memory[condition]
                if enabled:
                    if base in (17, 33, 49):
                        if all(state >> q & 1 for q in qs[:-1]):
                            state ^= 1 << qs[-1]
                    elif base in (34, 50):
                        a, b = qs[-2:]
                        if (base == 34 or state >> qs[0] & 1) and (state >> a ^ state >> b) & 1:
                            state ^= (1 << a) | (1 << b)
                    elif base in (18, 80):
                        state &= ~(1 << qs[0])
                        if base == 80:
                            memory[slot] = assignment[fresh[0]]
                    elif base in (64, 65):
                        memory[slot] = base & 1
                    elif base == 66:
                        memory[slot] ^= 1
                known = {0: 1, **assignment}
                for atom, (left, right) in sorted(products.items()):
                    known[atom] = (sum(known[v] for v in left) & 1) & (sum(known[v] for v in right) & 1)
                assert [sum(known[v] for v in value) & 1 for value in support.values] == [state >> q & 1 for q in range(4)]
                assert {k: sum(known[v] for v in value) & 1 for k, value in support.memory.items()} == memory


@pytest.mark.parametrize("field,limit", [("max_retained_terms", 1), ("max_value_terms", 1),
                                       ("max_analysis_ops", 1), ("max_reservation_ops", 1)])
def test_specific_representation_and_window_guards_are_inconclusive(tmp_path, field, limit):
    prefix = [(18, (2,), None, None), (33, (0, 2), None, None),
              (33, (1, 2), None, None), (49, (0, 1, 2), None, None)]
    source, request = setup(tmp_path, prefix=prefix)
    result = prove(source, request, limits=replace(AffineResourceLimits(), **{field: limit}))
    assert result["outcome"] == "inconclusive" and result["facts"] == [] and not result["usable_resources"]


@pytest.mark.parametrize("shape", ["cycle", "chain"])
@pytest.mark.parametrize("reverse", [False, True])
def test_resource_batches_refuse_cross_resource_parents(tmp_path, shape, reverse):
    if shape == "cycle":
        prefix = [(80, (0,), 0, None), (33, (1, 0), None, None)]
        items = [{"wire": 0, "parents": [1], "constant": 0},
                 {"wire": 1, "parents": [0], "constant": 0}]
    else:
        prefix = [(80, (1,), 0, None), (33, (2, 1), None, None),
                  (80, (0,), 1, None), (33, (1, 0), None, None)]
        items = [{"wire": 0, "parents": [1], "constant": 0},
                 {"wire": 1, "parents": [2], "constant": 0}]
    source, request = setup(tmp_path, prefix=prefix, body=[(16, (2,), None, None)])
    request["resources"] = list(reversed(items)) if reverse else items
    result = prove(source, request)
    assert result["outcome"] == "unsupported"
    assert "parents of another resource" in result["reason"]
    assert result["facts"] == result["usable_resources"] == []
    assert not result["candidate_authorized"] and not result["global_substitution_proved"]
    for item in items:
        alternative = copy.deepcopy(request)
        alternative["resources"] = [item]
        assert prove(source, alternative)["usable_resources"] == [item["wire"]]


def test_joint_preparation_with_shared_external_parents_is_clean_and_restores_correlations(tmp_path):
    prefix = [(80, (1,), 0, None), (80, (2,), 1, None),
              (33, (0, 1), None, None), (17, (2,), None, None),
              (33, (0, 2), None, None), (33, (3, 2), None, None)]
    body = [(160, (0, 3), None, 0), (144, (0,), None, 1)]
    source, request = setup(tmp_path, prefix=prefix, body=body)
    request["resources"] = [{"wire": 1, "parents": [0], "constant": 0},
                            {"wire": 2, "parents": [0, 3], "constant": 1}]
    result = prove(source, request)
    assert result["outcome"] == "proved" and result["usable_resources"] == [1, 2]
    assert replay_affine_kmb_resources(source, request, result, **pins(request)) == result
    prefix_ops = [HOp("hmr", (1,), slot="b0"), HOp("hmr", (2,), slot="b1"),
                  HOp("cx", (0, 1)), HOp("x", (2,)), HOp("cx", (0, 2)), HOp("cx", (3, 2))]
    body_ops = [HOp("cz", (0, 3), condition="b0"), HOp("z", (0,), condition="b1")]
    original = HybridProgram(4, 0, prefix_ops + body_ops)
    for order in permutations(result["facts"]):
        prep = [HOp(op[0], tuple(op[1:])) for fact in order for op in fact["preparation"]]
        at_cut = HybridProgram(4, 0, prefix_ops + prep)
        wrapped = HybridProgram(4, 0, prefix_ops + prep + body_ops + list(reversed(prep)))
        for x, y in product(range(16), repeat=2):
            prepared = independent_kraus(at_cut, x, y, ("b0", "b1"))
            # Both sides of every nonzero matrix unit have both resources zero.
            assert all(not ((a | b) & 6) for matrix in prepared.values() for a, b in matrix)
            assert independent_kraus(original, x, y, ("b0", "b1")) == independent_kraus(
                wrapped, x, y, ("b0", "b1"))
