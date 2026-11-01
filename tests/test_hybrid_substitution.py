"""Public coherent-channel substitution adapter and negative controls."""
import json
import time
from dataclasses import replace

import pytest

from symq import Budget
from symq.experimental.hybrid import HOp, HybridProgram, same_channel
from symq.labs.channel_composition import HybridFragment
from symq.labs.hybrid_substitution import (
    check_hybrid_substitution,
    replay_hybrid_substitution,
)
from symq.labs.rewrite import ReceiptMismatch, Weights


def reference_and_replacement():
    ops = (
        HOp("ccx", (0, 1, 3)),
        HOp("cx", (3, 2)),
        HOp("ccx", (0, 1, 3)),
    )
    replacement = HybridFragment(4, (
        HOp("ccx", (0, 1, 3)),
        HOp("cx", (3, 2)),
        HOp("hmr", (3,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ))
    return ops, replacement


def test_temporary_and_channel_and_independent_scalar_oracle():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    result = check_hybrid_substitution(
        source, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
    )
    assert result.certified and result.equivalent
    assert result.checked_pairs == 64
    assert result.cost.reference_ops == 3
    assert result.cost.candidate_ops == 4
    assert result.cost.candidate_ops - result.cost.reference_ops == 1  # no invented hardware speedup
    candidate = HybridProgram(3, 1, list(replacement.ops))
    assert same_channel(source, candidate).equivalent
    assert result.reference_sha256 != result.candidate_sha256
    assert result.contract_sha256 in json.dumps(result.to_dict())


def test_missing_phase_correction_does_not_pass_diagonal_only_check():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    mutant = HybridFragment(4, replacement.ops[:-1])
    result = check_hybrid_substitution(
        source, (0, 3), mutant, wires=(0, 1, 2, 3), clean=(3,),
    )
    assert result.outcome == "not_proved" and not result.certified
    assert "coherent channel" in result.reason


def test_clean_cut_must_be_established_by_the_real_prefix():
    ops, replacement = reference_and_replacement()
    unprepared = HybridProgram(4, 0, list(ops))
    result = check_hybrid_substitution(
        unprepared, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
    )
    assert result.outcome == "not_proved"
    assert "preparation" in result.reason


def test_borrowed_dirty_wire_retains_entanglement_not_just_bit_value():
    source = HybridProgram(2, 0, [HOp("cz", (0, 1))])
    replacement = HybridFragment(2, (HOp("cz", (0, 1)),))
    result = check_hybrid_substitution(
        source, (0, 1), replacement, wires=(0, 1), preserved=(1,),
    )
    assert result.outcome == "not_proved"
    assert "identity correlation" in result.reason


def test_connected_global_frame_can_exceed_local_oracle_width():
    ops, replacement = reference_and_replacement()
    prefix = [HOp("cx", (i, i+1)) for i in range(70)]
    # Reset is a real CPTP reset and the engine proves zero preparation at
    # the insertion site; it does not assume an unknown data wire is clean.
    prefix.append(HOp("reset", (3,)))
    suffix = [HOp("cx", (2, 70))]
    source = HybridProgram(70, 1, prefix + list(ops) + suffix)
    result = check_hybrid_substitution(
        source, (len(prefix), len(prefix)+len(ops)), replacement,
        wires=(0, 1, 2, 3), clean=(3,),
    )
    assert result.equivalent and result.checked_pairs == 64


def test_a_live_classical_result_requires_instrument_equality():
    ops = (
        HOp("reset", (1,)),
        HOp("measure_z", (1,), slot="b0"),
        HOp("x", (0,), condition="b0"),
    )
    source = HybridProgram(2, 0, list(ops))
    replacement = HybridFragment(2, (
        HOp("reset", (1,)),
        HOp("measure_z", (1,), slot="b0"),
        HOp("invert", slot="b0"),
    ))
    result = check_hybrid_substitution(
        source, (0, 2), replacement, wires=(0, 1),
    )
    assert result.outcome == "not_proved"
    assert "instrument" in result.reason


def test_strict_span_mapping_and_budget_are_fail_closed():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    with pytest.raises(ValueError, match="span"):
        check_hybrid_substitution(source, (0, 4), replacement, wires=(0, 1, 2, 3))
    with pytest.raises(ValueError, match="injectively"):
        check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 2))
    with pytest.raises(ValueError, match="injectively"):
        check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 4))
    small = check_hybrid_substitution(
        source, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
        budget=Budget(max_seconds=1e-12),
    )
    assert small.outcome == "inconclusive"
    with pytest.raises(ValueError, match="budget"):
        check_hybrid_substitution(
            source, (0, 3), replacement, wires=(0, 1, 2, 3),
            budget=Budget(max_nodes=2),
        )


def test_refuse_spans_that_touch_undeclared_quantum_wires():
    source = HybridProgram(3, 0, [HOp("cx", (0, 2))])
    with pytest.raises(ValueError, match="outside"):
        check_hybrid_substitution(
            source, (0, 1), HybridFragment(2, (HOp("cx", (0, 1)),)),
            wires=(0, 1),
        )


def test_public_source_pinned_qualtran_m1_substitution_in_real_context():
    # Public Apache-2.0 Qualtran GF2MulMBUC fixture, with its existing source
    # hash and upstream decomposition provenance checked by load_manifest().
    # This was already explored in SymQ; it is NOT a fresh independent holdout.
    from benchmarks.hmr_qualification import hybrid, load_manifest, programs

    cases = {item["id"]: item for item in load_manifest()["cases"]}
    a, b = (hybrid(p) for p in programs(cases["m1-full-none"]))
    prefix = [HOp("cx", (0, 1))]
    suffix = [HOp("cx", (0, 1))]
    source = HybridProgram(a.data, a.ancillas, prefix + a.ops + suffix)
    good = HybridFragment(a.width, tuple(b.ops))
    result = check_hybrid_substitution(
        source, (1, 1 + len(a.ops)), good, wires=tuple(range(a.width)),
        clean=(a.data,), preserved=tuple(range(a.data)),
    )
    assert result.equivalent and result.checked_pairs == 16
    # Existing independent full-program oracle on the actual public gadget.
    assert same_channel(a, b).equivalent

    _, bad = (hybrid(p) for p in programs(cases["m1-full-missing_correction"]))
    mutant = check_hybrid_substitution(
        source, (1, 1 + len(a.ops)), HybridFragment(a.width, tuple(bad.ops)),
        wires=tuple(range(a.width)), clean=(a.data,),
        preserved=tuple(range(a.data)),
    )
    assert mutant.outcome == "not_proved" and not mutant.certified


def test_hybrid_hashing_is_counted_in_one_deadline(monkeypatch):
    from symq.labs import hybrid_substitution as module

    original_digest = module.hybrid_digest

    def delayed_digest(program):
        time.sleep(0.02)
        return original_digest(program)

    monkeypatch.setattr(module, "hybrid_digest", delayed_digest)
    ops, replacement = reference_and_replacement()
    result = module.check_hybrid_substitution(
        HybridProgram(3, 1, list(ops)), (0, 3), replacement,
        wires=(0, 1, 2, 3), clean=(3,),
        budget=Budget(max_seconds=0.005),
    )
    assert result.outcome == "inconclusive" and not result.certified


def test_explicit_heterogeneous_operation_weights_are_just_a_cost_proxy():
    ops, replacement = reference_and_replacement()
    weights = Weights(
        (("ccx", 10), ("cx", 1), ("hmr", 0), ("cz", 2)),
        unit="illustrative_compiler_units",
    )
    result = check_hybrid_substitution(
        HybridProgram(3, 1, list(ops)), (0, 3), replacement,
        wires=(0, 1, 2, 3), clean=(3,), weights=weights,
    )
    assert result.equivalent
    assert result.cost.reference_weighted == 21
    assert result.cost.candidate_weighted == 13
    assert result.cost.weighted_delta == -8
    assert result.cost.candidate_ops - result.cost.reference_ops == 1
    assert result.to_dict()["cost"]["weights"]["unit"] == "illustrative_compiler_units"
    for pairs in (
        (("cx", 1), ("cx", 2)),
        (("cz", 1.5),),
        (("unknown", 1),),
        (("cx", -1),),
    ):
        with pytest.raises(ValueError, match="weights|weighted|operation"):
            Weights(pairs)


def test_hybrid_receipt_replay_rebinds_original_source_contract_and_costs():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    weights = Weights((("ccx", 10), ("hmr", 1)))
    receipt = check_hybrid_substitution(
        source, (0, 3), replacement, wires=(0, 1, 2, 3),
        clean=(3,), weights=weights,
    )
    assert receipt.certified
    assert replay_hybrid_substitution(
        receipt, source, (0, 3), replacement, wires=(0, 1, 2, 3),
        clean=(3,),
    ).certified
    with pytest.raises(ValueError, match="does not describe"):
        replay_hybrid_substitution(
            receipt, source, (0, 3), replacement, wires=(0, 1, 2, 3),
            clean=(3,), max_events=7,
        )
    with pytest.raises(ValueError, match="does not describe"):
        replay_hybrid_substitution(
            replace(receipt, cost=replace(receipt.cost, candidate_weighted=123)),
            source, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
        )
    with pytest.raises(ValueError, match="does not describe"):
        replay_hybrid_substitution(
            replace(receipt, theorem="local_coherent_instrument", instrument_slots=("b0",)),
            source, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
        )
    source.ops.append(HOp("x", (0,)))
    with pytest.raises(ValueError, match="does not describe"):
        replay_hybrid_substitution(
            receipt, source, (0, 3), replacement, wires=(0, 1, 2, 3),
            clean=(3,),
        )


def test_the_contract_hash_does_not_depend_on_the_order_of_wire_sets():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    one = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                    clean=(3,), preserved=(0, 1))
    other = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                      clean=(3,), preserved=(1, 0))
    assert one.contract_sha256 == other.contract_sha256


def test_hybrid_replay_refuses_forged_positive_without_recomputation():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    mutant = HybridFragment(4, replacement.ops[:-1])
    failed = check_hybrid_substitution(
        source, (0, 3), mutant, wires=(0, 1, 2, 3), clean=(3,),
    )
    assert not failed.equivalent
    fake = replace(failed, outcome="equivalent")
    fresh = replay_hybrid_substitution(
        fake, source, (0, 3), mutant, wires=(0, 1, 2, 3), clean=(3,),
    )
    assert fresh.outcome == "not_proved"
    assert not fresh.certified
    with pytest.raises(TypeError, match="typed"):
        replay_hybrid_substitution(
            fake.to_dict(), source, (0, 3), mutant,
            wires=(0, 1, 2, 3), clean=(3,),
        )



def test_the_proved_candidate_is_bound_to_the_frozen_global_program():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    result = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                       clean=(3,))
    assert result.certified and result.candidate is not None
    assert result.candidate.ops == replacement.ops
    assert same_channel(source, result.candidate.to_program()).equivalent
    source.ops.append(HOp("x", (0,)))
    assert len(result.candidate.ops) == len(replacement.ops)
    with pytest.raises(ReceiptMismatch, match="does not describe"):
        replay_hybrid_substitution(result, source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                   clean=(3,))


def test_a_forged_hybrid_verdict_is_never_authority():
    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    mutant = HybridFragment(4, replacement.ops[:-1])
    failing = check_hybrid_substitution(source, (0, 3), mutant, wires=(0, 1, 2, 3), clean=(3,))
    assert failing.candidate is None
    proved = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                       clean=(3,))
    with pytest.raises(ValueError, match="only be attached by the checker"):
        replace(failing, outcome="equivalent", candidate=proved.candidate)
    fresh = replay_hybrid_substitution(replace(failing, outcome="equivalent"), source, (0, 3),
                                       mutant, wires=(0, 1, 2, 3), clean=(3,))
    assert fresh.outcome == "not_proved" and fresh.candidate is None
    with pytest.raises(ReceiptMismatch):
        replay_hybrid_substitution(proved, source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                   clean=(3,), max_events=7)
    late = replay_hybrid_substitution(proved, source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                      clean=(3,), budget=Budget(max_seconds=1e-12))
    assert late.outcome == "inconclusive" and late.candidate is None


def test_hybrid_deadline_includes_freezing(monkeypatch):
    from symq.labs import hybrid_substitution as module

    ops, replacement = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    original = module.FrozenHybridProgram.freeze

    def delayed(cls, program):
        time.sleep(0.02)
        return original(program)

    monkeypatch.setattr(module.FrozenHybridProgram, "freeze", classmethod(delayed))
    late = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 3),
                                     clean=(3,), budget=Budget(max_seconds=0.005))
    assert late.outcome == "inconclusive" and late.candidate is None


def test_a_permuted_wire_map_is_localized_and_globalized_exactly():
    _, replacement = reference_and_replacement()
    wires = (2, 0, 1, 3)  # local 0, 1, 2, 3 -> global 2, 0, 1, 3
    block = [HOp("ccx", (2, 0, 3)), HOp("cx", (3, 1)), HOp("ccx", (2, 0, 3))]
    source = HybridProgram(3, 1, block)
    result = check_hybrid_substitution(source, (0, 3), replacement, wires=wires, clean=(3,))
    assert result.equivalent
    assert result.candidate.ops[0] == HOp("ccx", (2, 0, 3))
    assert same_channel(source, result.candidate.to_program()).equivalent
    # Swapping the two Toffoli controls is harmless (they are symmetric) ...
    symmetric = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 2, 1, 3),
                                          clean=(3,))
    assert symmetric.equivalent
    # ... but moving a control onto the CX target's data wire is a different local program.
    wrong = check_hybrid_substitution(source, (0, 3), replacement, wires=(1, 0, 2, 3),
                                      clean=(3,))
    assert wrong.outcome == "not_proved"


def test_an_empty_span_inserts_a_proved_identity():
    ops, _ = reference_and_replacement()
    source = HybridProgram(3, 1, list(ops))
    pair = HybridFragment(4, (HOp("cx", (0, 2)), HOp("cx", (0, 2))))
    result = check_hybrid_substitution(source, (1, 1), pair, wires=(0, 1, 2, 3))
    assert result.equivalent and len(result.candidate.ops) == len(ops) + 2


def test_oracle_bounds_give_inconclusive_not_a_verdict():
    source = HybridProgram(7, 0, [HOp("cx", (0, 1))])
    fragment = HybridFragment(7, (HOp("cx", (0, 1)),))
    result = check_hybrid_substitution(source, (0, 1), fragment, wires=tuple(range(7)),
                                       max_local_width=6)
    assert result.outcome == "inconclusive" and result.candidate is None
    with pytest.raises(ValueError, match="max_local_width"):
        check_hybrid_substitution(source, (0, 1), fragment, wires=tuple(range(7)),
                                  max_local_width=9)


def test_classical_inputs_are_universally_quantified():
    prefix = [HOp("measure_z", (1,), slot="b0")]
    source = HybridProgram(2, 0, [*prefix, HOp("x", (0,), condition="b0")])
    same = HybridFragment(2, (HOp("x", (0,), condition="b0"),), ("b0",))
    result = check_hybrid_substitution(source, (1, 2), same, wires=(0, 1))
    assert result.equivalent
    flipped = HybridFragment(2, (HOp("x", (0,), condition="!b0"),), ("b0",))
    assert check_hybrid_substitution(source, (1, 2), flipped, wires=(0, 1)).outcome \
        == "not_proved"


def test_discarded_wires_trace_out_only_terminal_globally_discarded_outputs():
    source = HybridProgram(2, 1, [HOp("x", (2,))])
    empty = HybridFragment(3, ())
    traced = check_hybrid_substitution(source, (0, 1), empty, wires=(0, 1, 2), discarded=(2,),
                                       discarded_global=(2,))
    assert traced.equivalent
    kept = check_hybrid_substitution(source, (0, 1), empty, wires=(0, 1, 2))
    assert kept.outcome == "not_proved"


def test_an_observed_record_switches_to_the_instrument_theorem():
    block = [HOp("measure_z", (1,), slot="b0")]
    source = HybridProgram(2, 0, [*block, HOp("x", (0,), condition="b0")])
    same = HybridFragment(2, tuple(block))
    result = check_hybrid_substitution(source, (0, 1), same, wires=(0, 1))
    assert result.equivalent and result.theorem == "local_coherent_instrument"
    assert result.instrument_slots == ("b0",)


_POOL = [
    (HOp("ccx", (0, 1, 2)), HOp("cx", (2, 0)), HOp("ccx", (0, 1, 2))),
    (HOp("ccx", (0, 1, 2)), HOp("cx", (2, 0)), HOp("hmr", (2,), slot="b0"),
     HOp("cz", (0, 1), condition="b0")),
    (HOp("ccx", (0, 1, 2)), HOp("cx", (2, 0)), HOp("hmr", (2,), slot="b0")),
    (HOp("cz", (0, 1)), HOp("cz", (0, 1))),
    (HOp("z", (0,)),),
    (HOp("cx", (0, 1)), HOp("cx", (1, 0)), HOp("cx", (0, 1))),
    (HOp("swap", (0, 1)),),
    (),
]


@pytest.mark.parametrize("seed", range(24))
def test_checker_verdicts_agree_with_the_independent_kraus_oracle(seed):
    """Proved implies equal on every coherence (independent oracle); a difference the oracle
    sees is never proved. Contexts are random one-to-two-gate prefixes and suffixes."""
    import random

    from testkit.kraus_oracle import coherence_images

    rng = random.Random(seed)
    context = [HOp("cx", (0, 1)), HOp("x", (1,)), HOp("z", (0,)), HOp("cz", (0, 1))]
    prefix = rng.sample(context, rng.randint(0, 2))
    suffix = rng.sample(context, rng.randint(0, 2))
    block, other = rng.choice(_POOL), rng.choice(_POOL)
    source = HybridProgram(2, 1, [*prefix, *block, *suffix])
    fragment = HybridFragment(3, tuple(other))
    result = check_hybrid_substitution(source, (len(prefix), len(prefix) + len(block)),
                                       fragment, wires=(0, 1, 2), clean=(2,))
    rewritten = HybridProgram(2, 1, [*prefix, *other, *suffix])
    equal = coherence_images(source) == coherence_images(rewritten)
    if result.equivalent:
        assert equal
    if not equal:
        assert not result.equivalent
