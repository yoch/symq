"""GF(2^24) multiplier rewrites proved exactly with the packed degree-two engine.

The chain is exact end to end: the schoolbook circuit's output polynomials are compared with the
field multiplication tensor, and every other circuit is proved equal to the schoolbook circuit on
all 2^72 inputs by the total theorem (no sampling).
"""
from __future__ import annotations

import random

import pytest

from symq import ANF, Circuit, make_algebra, simulate
from symq.generators.gf2n import emit, karatsuba, schoolbook, tensor
from symq.labs.bilinear_substitution import GF24_METHODS, gf24_rewrite, mapped_circuit
from symq.labs.contextual_substitution import (
    SubstitutionContract,
    check_substitution,
    replay_substitution,
)
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_order import pinned_gf24_circuit
from symq.labs.rewrite import ReceiptMismatch, Weights

N, WIDTH = 24, 72
EXPENSIVE_CCX = Weights.from_mapping({"ccx": 32, "cx": 1})


def _schoolbook() -> Circuit:
    return emit(N, schoolbook(N)).circuit


def test_the_schoolbook_circuit_computes_the_field_tensor():
    algebra = make_algebra("packed", WIDTH)
    outputs = [algebra.to_anf(value) for value in simulate(_schoolbook(), algebra)]
    table = tensor(N)
    for k in range(N):
        monomials = {1 << (2 * N + k)}
        monomials |= {(1 << i) | (1 << (N + j)) for i in range(N) for j in range(N)
                      if table[i][j] >> k & 1}
        assert outputs[2 * N + k] == ANF(frozenset(monomials))
    assert all(outputs[w] == ANF(frozenset({1 << w})) for w in range(2 * N))


@pytest.mark.parametrize("name", ["karatsuba", "tower"])
def test_each_alternative_is_proved_equal_to_schoolbook_on_every_input(name):
    base = _schoolbook()
    other = (emit(N, karatsuba(N), strategy="pivot-scheduled").circuit if name == "karatsuba"
             else pinned_gf24_circuit())
    result = check_substitution(base, (0, len(base.gates)), other,
                                contract=SubstitutionContract(), engine="packed")
    assert result.equivalent and result.theorem == "classical_total"


def _context(rng: random.Random):
    """76 wires: the multiplier on a random injective wire map, with an unrestricted prefix and
    suffix acting on the multiplier wires and on four extra wires."""
    width = WIDTH + 4
    wires = tuple(rng.sample(range(width), WIDTH))
    block = mapped_circuit(_schoolbook(), width, wires)
    prefix = Circuit(width).cx(wires[0], wires[30]).ccx(72, 73, wires[60]).x(74)
    suffix = Circuit(width).ccx(wires[1], wires[2], 75).cx(wires[70], 72)
    source = Circuit(width, prefix.gates + block.gates + suffix.gates)
    return source, (len(prefix.gates), len(prefix.gates) + len(block.gates)), wires


def test_rewrite_in_context_with_a_permuted_wire_map():
    source, span, wires = _context(random.Random(7))
    method, result = gf24_rewrite(source, span, wires=wires, weights=EXPENSIVE_CCX)
    assert method == "tower-99-pinned-order" and result.equivalent
    assert result.cost.weighted_delta == (99 * 32 + 2634) - 1419 * 32
    candidate = result.candidate.circuit()
    rng = random.Random(1)
    for value in (0, (1 << source.width) - 1, *(rng.getrandbits(source.width) for _ in range(8))):
        assert candidate.run(value) == source.run(value)  # a spot check; the proof is exact


@pytest.mark.parametrize("mutation", ["drop_ccx", "retarget_ccx", "extra_cx", "swap_operands"])
def test_mutants_are_not_proved(mutation):
    source, span, wires = _context(random.Random(3))
    local = pinned_gf24_circuit()
    gates = list(local.gates)
    if mutation == "drop_ccx":
        gates.remove(next(g for g in gates if g.name == "ccx"))
    elif mutation == "retarget_ccx":
        index = next(i for i, g in enumerate(gates) if g.name == "ccx")
        a, b, t = gates[index].qubits
        gates[index] = type(gates[index])("ccx", (a, b, 2 * N + (t - 2 * N + 1) % N))
    elif mutation == "extra_cx":
        gates.append(type(gates[0])("cx", (0, 2 * N)))
    mutant = Circuit(WIDTH, gates)
    order = wires if mutation != "swap_operands" else wires[N:2 * N] + wires[:N] + wires[2 * N:]
    if mutation == "swap_operands":
        # a*b = b*a: swapping the operand registers is a valid rewrite, not a mutant.
        result = check_substitution(source, span, mapped_circuit(mutant, source.width, order),
                                    contract=SubstitutionContract(), engine="packed")
        assert result.equivalent
        return
    result = check_substitution(source, span, mapped_circuit(mutant, source.width, order),
                                contract=SubstitutionContract(), engine="packed")
    assert result.outcome == "not_proved" and result.candidate is None


def test_a_cubic_block_is_unsupported_not_guessed():
    source = Circuit(WIDTH, list(_schoolbook().gates)).mcx(0, 1, 2, 2 * N)
    result = check_substitution(source, (0, len(source.gates)), pinned_gf24_circuit(),
                                contract=SubstitutionContract(), engine="packed")
    assert result.outcome == "unsupported"


def test_receipts_bind_the_source_and_the_cost_policy_can_refuse():
    source, span, wires = _context(random.Random(5))
    _, proved = gf24_rewrite(source, span, wires=wires, weights=EXPENSIVE_CCX)
    edited = Circuit(source.width, list(source.gates)).x(0)
    replacement = mapped_circuit(pinned_gf24_circuit(), source.width, wires)
    with pytest.raises(ReceiptMismatch):
        replay_substitution(proved, edited, span, replacement, contract=SubstitutionContract())
    # With equal weights the schoolbook circuit is cheapest: no saving, nothing applied.
    method, flat = gf24_rewrite(source, span, wires=wires, weights=Weights())
    assert method == "schoolbook-incidence" and flat.equivalent and flat.candidate is None


def test_selection_and_weights():
    assert choose_gf24(ccx_weight=1, cx_weight=100).method == "schoolbook-incidence"
    assert choose_gf24(ccx_weight=10, cx_weight=1).method == "karatsuba-pivot-scheduled"
    chosen = choose_gf24(ccx_weight=32, cx_weight=1)
    assert chosen.method == "tower-99-pinned-order"
    assert (chosen.cost.ccx, chosen.cost.cx) == (99, 2634)
    assert {c.name for c in chosen.alternatives} == set(GF24_METHODS)
    with pytest.raises(ValueError, match="method"):
        gf24_rewrite(Circuit(WIDTH), (0, 0), wires=tuple(range(WIDTH)), weights=Weights(),
                     method="unknown")


def test_the_evidence_report_proves_every_circuit_and_checks_its_pins(tmp_path):
    from benchmarks import gf24_tower_qualification as qualification

    assert qualification.main(["--output", str(tmp_path / "out" / "gf24.json")]) == 0
    result = qualification.report()
    assert qualification.passed(result)
    assert [c["cx"] for c in result["gate_proxy"]["alternatives"]] == [0, 1856, 2634]
    broken = dict(result, factor_sha256_matches_pin=False)
    assert not qualification.passed(broken)
