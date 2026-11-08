"""Independent exhaustive value and coherent-support oracles for resource facts."""
from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import replace
from itertools import product

import pytest
from test_kmb_window import _packets
from testkit.kraus_oracle import independent_kraus

pytest.importorskip("numpy")

from symq.experimental.hybrid import HOp, HybridProgram
from symq.hashing import canonical_sha256
from symq.labs import kmb_resource_frontier as api
from symq.labs.rewrite import ReceiptMismatch
from symq.resources import Budget


def problem(tmp_path, operations, *, cut=None, stop=None, constants=(), width=3):
    raw = _packets(*operations, registers=(("all", [(True, q) for q in range(width)]),))
    path = tmp_path / "source.kmb"
    path.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    request = {"kind": "symq_kmb_resource_frontier", "schema_version": 1,
               "source_file_sha256": pin, "cut_op": len(operations) if cut is None else cut,
               "lease_stop_op": len(operations) if stop is None else stop,
               "wires": list(range(width)), "initial_constants": [list(p) for p in constants]}
    return path, request


def pins(request):
    return {"expected_source_sha256": request["source_file_sha256"],
            "expected_request_sha256": canonical_sha256(request)}


def assess(path, request, **kwargs):
    return api.assess_kmb_resources(path, request, **pins(request), **kwargs)


def scalar(operations, value, classical, choices, width=3):
    bits = [value >> q & 1 for q in range(width)]
    memory = [classical >> q & 1 for q in range(3)]
    stack, position = [], 0
    for code, qs, bit, condition in operations:
        if code == 129:
            stack.append(bool(memory[condition]))
            continue
        if code == 1:
            if stack:
                stack.pop()
            continue
        event = None
        if code & 127 == 80:
            event = choices[position]
            position += 1
        if not all(stack) or (code & 128 and not memory[condition]):
            continue
        base = code & 127
        if base == 17:
            bits[qs[0]] ^= 1
        elif base == 33:
            bits[qs[1]] ^= bits[qs[0]]
        elif base == 49:
            bits[qs[2]] ^= bits[qs[0]] & bits[qs[1]]
        elif base == 34:
            bits[qs[0]], bits[qs[1]] = bits[qs[1]], bits[qs[0]]
        elif base == 50:
            if bits[qs[0]]:
                bits[qs[1]], bits[qs[2]] = bits[qs[2]], bits[qs[1]]
        elif base in (18, 80):
            bits[qs[0]] = 0
            if base == 80:
                memory[bit] = event
        elif base == 64:
            memory[bit] = 0
        elif base == 65:
            memory[bit] = 1
        elif base == 66:
            memory[bit] ^= 1
        elif base not in (16, 32, 48, 0):
            raise AssertionError(base)
    return bits


def test_origin_has_arbitrary_inputs_never_implicit_zero(tmp_path):
    path, request = problem(tmp_path, [(17, (2,), None, None)], cut=0)
    result = assess(path, request)
    assert result["status"] == "assessed"
    assert all(f["cleanliness"] == "unknown" for f in result["facts"])
    assert result["available_zero_wires"] == []
    request["initial_constants"] = [[0, 0], [1, 1]]
    result = assess(path, request)
    assert result["available_zero_wires"] == [0]
    assert result["facts"][1]["cleanliness"] == "proved_one"
    assert result["facts"][0]["initial_value_is_supplied_assumption"]
    assert not result["external_preparation_proved"]


@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 1024])
def test_top_level_x_parity_after_reset_and_later_writes(tmp_path, chunk):
    ops = [(18, (0,), None, None), (17, (0,), None, None), (17, (0,), None, None),
           (80, (1,), 0, None), (17, (1,), None, None), (33, (0, 2), None, None),
           (32, (0, 1), None, None)]
    path, request = problem(tmp_path, ops, cut=6)
    result = assess(path, request, limits=replace(api.FrontierLimits(), chunk_ops=chunk))
    assert [f["value"] for f in result["facts"]] == [0, 1, None]
    assert result["facts"][0]["top_level_x_after_anchor"] == 2
    assert result["facts"][1]["top_level_x_after_anchor"] == 1
    assert result["facts"][0]["reservation"] == "source_interference"
    assert result["facts"][0]["source_touches"] == [6]
    assert result["available_zero_wires"] == []


def test_conditional_stack_reset_and_x_never_supply_unconditional_facts(tmp_path):
    ops = [(18, (0,), None, None), (129, (), None, 0),
           (17, (0,), None, None), (18, (1,), None, None),
           (129, (), None, 1), (18, (2,), None, None), (1, (), None, None), (1, (), None, None)]
    path, request = problem(tmp_path, ops)
    for chunk in (1, 3, 5, 100):
        result = assess(path, request, limits=replace(api.FrontierLimits(), chunk_ops=chunk))
        assert all(f["value"] is None for f in result["facts"])
    # An empty POP is an actual no-op, not a negative stack depth.
    ops = [(1, (), None, None), (18, (0,), None, None), (129, (), None, 0),
           (18, (1,), None, None), (1, (), None, None)]
    path, request = problem(tmp_path, ops)
    result = assess(path, request)
    assert [f["value"] for f in result["facts"]] == [0, None, None]
    assert result["work"]["empty_pop_noop_count"] == 1


def test_seeded_complete_sources_against_independent_exhaustive_scalar(tmp_path):
    rng = random.Random(2026110803)
    templates = [(17, (0,), None, None), (18, (1,), None, None), (80, (2,), 0, None),
                 (33, (0, 1), None, None), (49, (0, 1, 2), None, None),
                 (34, (1, 2), None, None), (50, (0, 1, 2), None, None),
                 (145, (1,), None, 0), (146, (2,), None, 0),
                 (16, (0,), None, None), (160, (0, 2), None, 0), (64, (), 0, None)]
    for _ in range(35):
        operations = [rng.choice(templates) for _ in range(9)]
        if sum(c & 127 == 80 for c, *_ in operations) > 2:
            continue
        cut = rng.randrange(10)
        path, request = problem(tmp_path, operations, cut=cut)
        result = assess(path, request, limits=replace(api.FrontierLimits(), chunk_ops=rng.randint(1, 7)))
        facts = {f["wire"]: f["value"] for f in result["facts"] if f["value"] is not None}
        events = sum(c & 127 == 80 for c, *_ in operations[:cut])
        for value, classical in product(range(8), range(2)):
            for choices in product((0, 1), repeat=events):
                output = scalar(operations[:cut], value, classical, choices)
                assert all(output[q] == bit for q, bit in facts.items())


def test_known_bit_is_pure_even_on_coherent_inputs_and_external_correlations(tmp_path):
    ops = [(18, (1,), None, None), (17, (1,), None, None), (32, (1, 2), None, None),
           (33, (1, 0), None, None)]
    path, request = problem(tmp_path, ops)
    result = assess(path, request)
    assert result["facts"][1]["value"] == 1
    program = HybridProgram(3, 0, [HOp("reset", (1,)), HOp("x", (1,)),
                                    HOp("cz", (1, 2)), HOp("cx", (1, 0))])
    for x, y in product(range(8), repeat=2):
        channel = independent_kraus(program, x, y)
        assert all((a >> 1 & 1) == (b >> 1 & 1) == 1
                   for output in channel.values() for a, b in output)


def test_forged_stale_dependency_and_type_mutations_require_full_replay(tmp_path):
    path, request = problem(tmp_path, [(18, (0,), None, None)], cut=1)
    result = assess(path, request)
    assert api.replay_kmb_resources(path, request, json.loads(json.dumps(result)), **pins(request)) == result
    for mutate in (
        lambda d: d.update(schema_version=True), lambda d: d.update(verified=True),
        lambda d: d["facts"][0].update(value=1),
        lambda d: d["dependencies"].update(numpy="forged"),
        lambda d: d["facts"][0].update(source_touches=[0]),
        lambda d: d.update(available_zero_wires=[0, 1, 2]),
    ):
        modified = copy.deepcopy(result)
        mutate(modified)
        with pytest.raises(ReceiptMismatch):
            api.replay_kmb_resources(path, request, modified, **pins(request))
    request["cut_op"] = 0
    with pytest.raises(ReceiptMismatch):
        api.assess_kmb_resources(path, request, **pins(result["request"]))
    with pytest.raises(ReceiptMismatch):
        api.replay_kmb_resources(path, request, result, **pins(request))


def test_unsupported_operations_anywhere_and_budgets_never_supply_facts(tmp_path):
    path, request = problem(tmp_path, [(18, (0,), None, None), (0x13, (1,), None, None)], cut=1)
    assert assess(path, request)["status"] == "unsupported"
    path, request = problem(tmp_path, [(18, (0,), None, None)], cut=1)
    receipt = assess(path, request)
    expired = Budget(absolute_deadline=0)
    assert assess(path, request, budget=expired)["facts"] == []
    assert api.replay_kmb_resources(path, request, receipt, **pins(request), budget=expired)["facts"] == []
    assert assess(path, request, limits=replace(api.FrontierLimits(), max_source_bytes=1))["status"] == "inconclusive"
    with pytest.raises(ValueError, match="time"):
        assess(path, request, budget=Budget(max_terms=1))
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ReceiptMismatch):
        assess(path, request)


def test_complete_source_validation_and_reservation_limits(tmp_path):
    # Invalid operations beyond the cut still invalidate the full-source theorem.
    path, request = problem(tmp_path, [(18, (0,), None, None), (33, (1, 1), None, None)], cut=1)
    with pytest.raises(ValueError, match="aliased"):
        assess(path, request)
    path, request = problem(tmp_path, [(18, (0,), None, None), (129, (), None, 0)], cut=1)
    assert assess(path, request)["status"] == "unsupported"
    path, request = problem(tmp_path, [(18, (0,), None, None)] * 3, cut=0)
    assert assess(path, request, limits=replace(api.FrontierLimits(), max_lease_ops=1))["facts"] == []
    request["initial_constants"] = [[0, 0], [0, 1]]
    with pytest.raises(ValueError, match="unique"):
        assess(path, request)


def test_expiration_after_scan_clears_even_previously_computed_facts(tmp_path, monkeypatch):
    from symq.errors import ResourceLimitExceeded

    path, request = problem(tmp_path, [(18, (0,), None, None)])

    def expired(*_):
        raise ResourceLimitExceeded("seconds", 1, 2)

    monkeypatch.setattr(api, "_dependencies", expired)
    result = assess(path, request)
    assert result["status"] == "inconclusive"
    assert result["facts"] == result["available_zero_wires"] == []
