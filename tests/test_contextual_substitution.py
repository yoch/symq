"""Adversarial and independent small-domain tests of contextual SAT substitutions."""
import copy
import json
import random
import time
from dataclasses import replace

import pytest

from symq import Budget, Circuit
from symq.labs.contextual_substitution import (
    SubstitutionContract,
    check_substitution,
    replay_substitution,
)
from symq.labs.rewrite import ReceiptMismatch, Weights
from symq.sat.assumptions import Not, Var

pytestmark = pytest.mark.sat


def replace_at(circuit, span, candidate):
    return Circuit(
        circuit.width,
        circuit.gates[:span[0]] + candidate.gates + circuit.gates[span[1]:],
    )


def test_clean_at_real_cut_and_cost_report():
    # Prefix computes/uncomputes q2, which is initially prepared as classical zero.
    source = Circuit(3).cx(0, 2).cx(0, 2).cx(2, 0).cx(0, 1)
    candidate = Circuit(3)
    contract = SubstitutionContract(initial_constants=((2, 0),), clean_at_cut=(2,))
    result = check_substitution(
        source, (2, 3), candidate, contract=contract, weights=Weights.from_mapping({"cx": 7})
    )
    assert result.equivalent and result.certified and not result.different
    assert result.cost.reference_ops == 4
    assert result.cost.candidate_ops == 3
    assert result.cost.weighted_delta == -7
    assert [o.name for o in result.obligations] == [
        "domain", "prefix", "interface", "suffix", "restore_original", "restore_candidate",
    ]
    assert all(o.status == "passed" for o in result.obligations)
    for x in range(8):
        if not (x & (1 << 2)):
            assert source.run(x) == replace_at(source, (2, 3), candidate).run(x)
    assert source.run(4) != replace_at(source, (2, 3), candidate).run(4)
    encoded = json.dumps(result.to_dict(), sort_keys=True)
    assert result.reference_sha256 in encoded
    assert result.contract_sha256 in encoded


def test_clean_at_cut_is_not_a_free_assumption():
    source = Circuit(3).cx(2, 0)
    result = check_substitution(
        source, (0, 1), Circuit(3),
        contract=SubstitutionContract(clean_at_cut=(2,)),
    )
    assert result.outcome == "precondition_failed" and not result.certified
    prefix = next(o for o in result.obligations if o.name == "prefix")
    assert prefix.status == "failed"
    assert prefix.witness_kind == "input"
    assert prefix.witness[0] & 4


def test_general_cut_predicate_is_proved_from_prefix_and_input_domain():
    source = Circuit(3).cx(0, 1)
    contract = SubstitutionContract(
        initial_constants=((0, 0),),
        cut_assumption=Not(Var("u.0")),
    )
    result = check_substitution(source, (0, 1), Circuit(3), contract=contract)
    assert result.equivalent
    for x in range(8):
        if not (x & 1):
            assert source.run(x) == x

    wrong = check_substitution(
        source, (0, 1), Circuit(3),
        contract=SubstitutionContract(
            initial_constants=((0, 0),), cut_assumption=Var("u.0"),
        ),
    )
    assert wrong.outcome == "precondition_failed"


def test_local_counterexample_is_not_claimed_to_be_a_global_difference():
    # No cut assumption: this local mismatch is conclusive against the
    # specified local lemma, but a cut-state witness is not a global input.
    source = Circuit(3).ccx(0, 1, 2)
    result = check_substitution(
        source, (0, 1), Circuit(3), contract=SubstitutionContract()
    )
    assert result.outcome == "not_proved"
    assert not result.equivalent and not result.different
    suffix = next(o for o in result.obligations if o.name == "suffix")
    assert suffix.status == "failed" and suffix.witness_kind == "cut"
    assert len(suffix.witness) == 2


def test_both_equal_blocks_must_restore_the_borrowed_bit():
    source = Circuit(3).cx(0, 2)
    same = Circuit(3).cx(0, 2)
    result = check_substitution(
        source, (0, 1), same,
        contract=SubstitutionContract(restored_at_cut=(2,)),
    )
    assert result.outcome == "not_proved"
    proof = next(o for o in result.obligations if o.name == "restore_original")
    assert proof.status == "failed" and proof.witness_kind == "cut"
    assert proof.witness[0] & 1


def test_source_and_replacement_must_be_validated_and_unmodified():
    source = Circuit(3).cx(0, 1)
    candidate = Circuit(3).cx(0, 1)
    result = check_substitution(
        source, (0, 1), candidate, contract=SubstitutionContract()
    )
    assert result.equivalent and len(source.gates) == len(candidate.gates) == 1
    source.x(2)
    changed = check_substitution(
        source, (0, 1), candidate, contract=SubstitutionContract()
    )
    assert changed.reference_sha256 != result.reference_sha256
    with pytest.raises(ValueError, match="same|width"):
        check_substitution(source, (0, 1), Circuit(2), contract=SubstitutionContract())
    with pytest.raises(ValueError, match="span"):
        check_substitution(source, (0, 3), candidate, contract=SubstitutionContract())
    with pytest.raises(ValueError, match="duplicate"):
        check_substitution(
            source, (0, 1), candidate,
            contract=SubstitutionContract(initial_constants=((0, 0), (0, 1))),
        )
    with pytest.raises(ValueError, match="undeclared"):
        check_substitution(
            source, (0, 1), candidate,
            contract=SubstitutionContract(cut_assumption=Var("v.0")),
        )


def test_balanced_cut_relations_work_beyond_the_expression_depth_limit():
    width = 33
    source = Circuit(width).cx(32, 0)
    result = check_substitution(
        source, (0, 1), Circuit(width),
        contract=SubstitutionContract(
            initial_constants=((32, 0),), clean_at_cut=(32,),
        ),
        budget=Budget(max_seconds=20),
    )
    assert result.equivalent


def test_timeout_and_sat_budget_fail_closed():
    source = Circuit(3).cx(0, 1)
    result = check_substitution(
        source, (0, 1), Circuit(3),
        contract=SubstitutionContract(),
        budget=Budget(max_seconds=1e-12),
    )
    assert result.outcome == "inconclusive" and not result.certified
    with pytest.raises(ValueError, match="SAT"):
        check_substitution(
            source, (0, 1), Circuit(3), contract=SubstitutionContract(),
            budget=Budget(max_nodes=5),
        )


def test_independent_exhaustive_oracle_for_positive_small_rewrites():
    for width in (3, 4):
        source = Circuit(width).cx(0, 1).cx(0, 1).ccx(0, 1, 2)
        result = check_substitution(
            source, (0, 2), Circuit(width),
            contract=SubstitutionContract(),
        )
        assert result.equivalent
        full_candidate = replace_at(source, (0, 2), Circuit(width))
        for x in range(1 << width):
            assert source.run(x) == full_candidate.run(x)
        # An arbitrary mutant must not be certified.
        mutant = check_substitution(
            source, (0, 3), Circuit(width), contract=SubstitutionContract(),
        )
        assert not mutant.certified


def test_fingerprinting_is_included_in_the_original_call_deadline(monkeypatch):
    from symq.labs import contextual_substitution as module

    original_digest = module.digest

    def intentionally_slow_digest(program):
        time.sleep(0.02)
        return original_digest(program)

    monkeypatch.setattr(module, "digest", intentionally_slow_digest)
    result = module.check_substitution(
        Circuit(3).cx(0, 1), (0, 1), Circuit(3).cx(0, 1),
        contract=SubstitutionContract(), budget=Budget(max_seconds=0.005),
    )
    assert result.outcome == "inconclusive" and not result.certified


def test_replay_recomputes_and_binds_source_candidate_contract_and_costs():
    original = Circuit(3).cx(0, 1).cx(0, 1).cx(1, 2)
    replacement = Circuit(3)
    contract = SubstitutionContract()
    receipt = check_substitution(
        original, (0, 2), replacement, contract=contract,
        weights=Weights.from_mapping({"cx": 7}),
    )
    assert receipt.equivalent
    assert replay_substitution(
        receipt, original, (0, 2), replacement, contract=contract,
    ).equivalent
    with pytest.raises(ValueError, match="does not describe"):
        replay_substitution(receipt, original, (0, 1), replacement, contract=contract)
    with pytest.raises(ValueError, match="does not describe"):
        replay_substitution(
            receipt, original, (0, 2), Circuit(3).x(0), contract=contract,
        )
    with pytest.raises(ValueError, match="does not describe"):
        replay_substitution(
            receipt, original, (0, 2), replacement,
            contract=SubstitutionContract(initial_constants=((0, 0),)),
        )
    # An edited proved receipt cannot even be built: the seal pins its cost.
    with pytest.raises(ValueError, match="not the result the checker proved"):
        replace(receipt, cost=replace(receipt.cost, candidate_weighted=-999))


def test_replay_refuses_forged_positive_outcome_without_a_new_proof():
    source = Circuit(3).ccx(0, 1, 2)
    replacement = Circuit(3)
    failed = check_substitution(
        source, (0, 1), replacement, contract=SubstitutionContract(),
    )
    assert failed.outcome == "not_proved"
    # An artificially positive result cannot even be built: only the checker issues one.
    with pytest.raises(ValueError, match="only issued by the checker"):
        replace(failed, outcome="equivalent")
    with pytest.raises(TypeError, match="typed"):
        replay_substitution(
            failed.to_dict(), source, (0, 1), replacement,
            contract=SubstitutionContract(),
        )


@pytest.mark.parametrize("seed", range(40))
def test_differential_random_insertion_against_exhaustive_global_oracle(seed):
    """For unrestricted inputs, equal prefix/suffix permutations preserve iff equivalence."""
    rng = random.Random(seed)
    width = rng.randint(3, 5)

    def fragment(count):
        c = Circuit(width)
        for _ in range(count):
            name = rng.choice(("x", "cx", "ccx"))
            num = {"x": 1, "cx": 2, "ccx": 3}[name]
            c.append(name, *rng.sample(range(width), num))
        return c

    prefix = fragment(rng.randint(1, 5))
    old = fragment(rng.randint(1, 5))
    suffix = fragment(rng.randint(1, 5))
    variant = Circuit(width, list(old.gates))
    if seed % 3 == 0:
        # Exact equivalent but structurally different candidate.
        target = rng.randrange(width)
        variant.x(target).x(target)
    elif seed % 3 == 1:
        # A final unmatched X changes a bit on EVERY cut input.
        variant.x(rng.randrange(width))
    # Else identical local implementation.

    source = Circuit(width, prefix.gates + old.gates + suffix.gates)
    span = (len(prefix.gates), len(prefix.gates) + len(old.gates))
    result = check_substitution(
        source, span, variant, contract=SubstitutionContract(),
        budget=Budget(max_seconds=10),
    )
    expected = all(
        source.run(x) == replace_at(source, span, variant).run(x)
        for x in range(1 << width)
    )
    assert result.outcome in ("equivalent", "not_proved")
    assert result.equivalent == expected
    assert result.cost.candidate_ops == len(prefix.gates) + len(variant.gates) + len(suffix.gates)


def test_random_restricted_input_domain_is_sound_when_proved():
    """Restricted cuts can be incomplete, but a positive proof must be globally valid."""
    rng = random.Random(919103)
    width = 4
    for _ in range(20):
        control = rng.randrange(width)
        target = (control + 1) % width
        prefix = Circuit(width).cx(control, target).cx(control, target)
        old = Circuit(width).cx(control, target)
        candidate = Circuit(width)
        source = Circuit(width, prefix.gates + old.gates)
        contract = SubstitutionContract(
            initial_constants=((control, 0),),
            cut_assumption=Not(Var(f"u.{control}")),
        )
        result = check_substitution(
            source, (len(prefix.gates), len(source.gates)), candidate,
            contract=contract,
        )
        assert result.equivalent
        for x in range(1 << width):
            if not x >> control & 1:
                assert source.run(x) == x


def test_missing_interruptible_sat_engine_is_explicitly_unsupported(monkeypatch):
    from symq.sat import composition as composition_engine

    monkeypatch.setattr(composition_engine, "solver_available", lambda: False)
    result = check_substitution(
        Circuit(3).cx(0, 1), (0, 1), Circuit(3),
        contract=SubstitutionContract(),
    )
    assert result.outcome == "unsupported" and not result.certified


def test_clean_ancilla_mcx_decomposition_in_real_prefix_suffix():
    """A nontrivial 3-control gate replacement that is invalid on dirty scratch."""
    source = (Circuit(5).cx(0, 4).cx(0, 4)
              .mcx(0, 1, 2, 3).cx(3, 0))
    replacement = (Circuit(5).ccx(0, 1, 4)
                   .ccx(4, 2, 3).ccx(0, 1, 4))
    contract = SubstitutionContract(
        initial_constants=((4, 0),), clean_at_cut=(4,),
    )
    weights = Weights.from_mapping({"cx": 1, "ccx": 2, "mcx": 10})
    result = check_substitution(
        source, (2, 3), replacement, contract=contract, weights=weights,
    )
    assert result.equivalent and result.cost.weighted_delta == -4
    assert all(item.status == "passed" for item in result.obligations)
    assert replay_substitution(
        result, source, (2, 3), replacement, contract=contract,
    ).equivalent
    candidate = replace_at(source, (2, 3), replacement)
    for x in range(1 << 5):
        if not (x >> 4 & 1):
            assert source.run(x) == candidate.run(x)
    # Deliberately dirty scratch: candidate has a false extra target flip.
    assert source.run((1 << 4) | (1 << 2)) != candidate.run((1 << 4) | (1 << 2))

    unprepared = check_substitution(
        source, (2, 3), replacement,
        contract=SubstitutionContract(clean_at_cut=(4,)),
    )
    assert unprepared.outcome == "precondition_failed"
    unfinished = Circuit(5, list(replacement.gates[:-1]))
    refused = check_substitution(
        source, (2, 3), unfinished, contract=contract,
    )
    assert not refused.certified


def test_the_proved_candidate_is_a_frozen_snapshot_not_a_saved_flag():
    source = Circuit(3).cx(0, 1).cx(0, 1).cx(1, 2)
    replacement = Circuit(3)
    contract = SubstitutionContract()
    result = check_substitution(source, (0, 2), replacement, contract=contract)
    candidate = result.candidate
    assert result.certified and candidate is not None and len(candidate.gates) == 1
    for x in range(8):
        assert candidate.circuit().run(x) == source.run(x)
    # Mutating the caller's circuits cannot change the proved snapshot.
    source.x(0)
    replacement.x(2)
    assert len(result.candidate.gates) == 1
    with pytest.raises(ReceiptMismatch, match="does not describe"):
        replay_substitution(result, source, (0, 2), replacement, contract=contract)
    # A negative receipt that contradicts the fresh positive proof is refused, not overwritten.
    with pytest.raises(ReceiptMismatch, match="contradicts"):
        replay_substitution(replace(result, outcome="not_proved", candidate=None, _token=None),
                            Circuit(3).cx(0, 1).cx(0, 1).cx(1, 2), (0, 2), Circuit(3),
                            contract=contract)


def test_a_candidate_cannot_be_attached_outside_the_checker():
    """Reproduction of the audit's bypass: negative result, edited outcome, candidate whose
    digest matches the recorded candidate_sha256. Every step is refused."""
    from symq.labs import rewrite
    from symq.labs.classical_transcript import Program

    assert not hasattr(rewrite, "attach_candidate")
    source, replacement = Circuit(3).ccx(0, 1, 2), Circuit(3)
    rejected = check_substitution(source, (0, 1), replacement, contract=SubstitutionContract())
    assert rejected.outcome == "not_proved" and rejected.candidate is None
    candidate = Program(3, ())  # exactly the stream named by rejected.candidate_sha256
    with pytest.raises(ValueError):
        replace(rejected, outcome="equivalent")
    with pytest.raises(ValueError):
        replace(rejected, outcome="equivalent", candidate=candidate)
    with pytest.raises(ValueError):
        replace(rejected, candidate=candidate)
    proved = check_substitution(Circuit(3).cx(0, 1).cx(0, 1), (0, 2), Circuit(3),
                                contract=SubstitutionContract())
    # The seal pins the proved result: it cannot be moved to another rewrite or edited.
    with pytest.raises(ValueError, match="only the proved stream"):
        replace(proved, candidate=Program(3, tuple(Circuit(3).x(0).gates)))
    for change in ({"reason": "edited"}, {"contract_sha256": "0" * 64},
                   {"outcome": "not_proved"}, {"span": (0, 1)}):
        with pytest.raises(ValueError):
            replace(proved, **change)
    with pytest.raises(ValueError):
        replace(rejected, outcome="equivalent", _token=proved._token)
    # A fresh or copied seal object is not a seal: only the checker registers one.
    for token in (type(proved._token)(), copy.copy(proved._token)):
        with pytest.raises(ValueError):
            replace(rejected, outcome="equivalent", _token=token)
    assert copy.deepcopy(proved).certified
    # A stored negative receipt that contradicts a fresh positive proof is refused.
    with pytest.raises(ReceiptMismatch, match="contradicts"):
        replay_substitution(replace(proved, outcome="not_proved", candidate=None, _token=None),
                            Circuit(3).cx(0, 1).cx(0, 1), (0, 2), Circuit(3),
                            contract=SubstitutionContract())

def test_a_restricted_domain_candidate_is_bound_to_its_contract():
    replacement = Circuit(3)
    restricted = SubstitutionContract(initial_constants=((0, 0),),
                                      cut_assumption=Not(Var("u.0")))
    proof = check_substitution(Circuit(3).cx(0, 2), (0, 1), replacement, contract=restricted)
    assert proof.equivalent
    assert proof.candidate.circuit().run(1) != Circuit(3).cx(0, 2).run(1)
    with pytest.raises(ReceiptMismatch):
        replay_substitution(proof, Circuit(3).cx(0, 2), (0, 1), replacement,
                            contract=SubstitutionContract())


def test_the_deadline_covers_freezing_and_a_timeout_is_inconclusive(monkeypatch):
    from symq.labs import contextual_substitution as module

    source, replacement = Circuit(3).cx(0, 1).cx(0, 1), Circuit(3)
    receipt = check_substitution(source, (0, 2), replacement, contract=SubstitutionContract())
    old = module.Program.freeze

    def delayed(cls, circuit):
        time.sleep(0.02)
        return old(circuit)

    monkeypatch.setattr(module.Program, "freeze", classmethod(delayed))
    late = check_substitution(source, (0, 2), replacement, contract=SubstitutionContract(),
                              budget=Budget(max_seconds=0.005))
    assert late.outcome == "inconclusive" and late.candidate is None
    # A slow replay is inconclusive, not a receipt mismatch: the pins still match.
    replayed = replay_substitution(receipt, source, (0, 2), replacement,
                                   contract=SubstitutionContract(),
                                   budget=Budget(max_seconds=0.005))
    assert replayed.outcome == "inconclusive"


def test_result_satisfies_the_verdict_protocol():
    from symq import Verdict

    result = check_substitution(Circuit(2).cx(0, 1).cx(0, 1), (0, 2), Circuit(2),
                                contract=SubstitutionContract())
    assert isinstance(result, Verdict)
    assert result.witness is None and result.witness_kind is None and not result.different
    assert result.to_dict()["outcome"] == "equivalent"
    json.dumps(result.to_dict())


@pytest.mark.parametrize("seed", range(12))
def test_contextual_verdicts_agree_with_a_global_sat_miter(seed):
    """Second, independent engine: a whole-circuit SAT miter under the same input constants."""
    from symq.sat import Contract, check_sat_equivalence

    rng = random.Random(1000 + seed)
    width = rng.randint(3, 5)
    source = Circuit(width)
    for _ in range(rng.randint(3, 8)):
        a, b, c = rng.sample(range(width), 3)
        if rng.random() < 0.5:
            source.cx(a, b)
        else:
            source.ccx(a, b, c)
    start = rng.randint(0, len(source.gates) - 1)
    stop = rng.randint(start, len(source.gates))
    replacement = Circuit(width, list(source.gates[start:stop]))
    if rng.random() < 0.5:
        a, b = rng.sample(range(width), 2)
        replacement.cx(a, b).cx(a, b)  # still equal
    else:
        a, b, c = rng.sample(range(width), 3)
        replacement.ccx(a, b, c)  # usually different
    constants = ((width - 1, 0),)
    result = check_substitution(source, (start, stop), replacement,
                                contract=SubstitutionContract(initial_constants=constants))
    candidate = replace_at(source, (start, stop), replacement)
    miter = check_sat_equivalence(source, candidate, Contract(input_constants=dict(constants)))
    if result.equivalent:
        assert miter.outcome == "equivalent"
    if miter.outcome == "different":
        assert not result.equivalent


def test_an_unavailable_total_engine_is_unsupported(monkeypatch):
    from symq import backends

    monkeypatch.delitem(backends.BACKENDS, "zdd-native", raising=False)
    source = Circuit(3).cx(0, 1).cx(0, 1)
    result = check_substitution(source, (0, 2), Circuit(3), contract=SubstitutionContract(),
                                engine="zdd-native")
    assert result.outcome == "unsupported" and result.candidate is None
