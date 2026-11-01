"""Public coherent-channel substitution adapter and negative controls."""
import json
import time

import pytest

from symq import Budget
from symq.experimental.hybrid import HOp, HybridProgram, same_channel
from symq.labs.channel_composition import HybridFragment
from symq.labs.hybrid_substitution import check_hybrid_substitution


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
    assert result.cost.delta_ops == 1  # no invented hardware speedup
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
