"""Regression tests for the typed proof contract and the real-circuit qualification.

The accounting has to stay honest:

* a resource limit is ``INCONCLUSIVE``, never ``DIFFERENT``;
* an unexpected crash is ``INTERNAL_ERROR``, distinct from a budget exhaustion;
* an out-of-grammar input is ``UNSUPPORTED``;
* only an ``EQUIVALENT`` verdict moves along a forgetful map;
* ``DIFFERENT`` on the full channel does not become ``DIFFERENT`` after the partial trace;
* ``DIFFERENT`` on an instrument does not become ``DIFFERENT`` on the channel;
* the QCEC qualification is a classical permutation check, and wires above 32 stay decidable
  on that path because the native mask is one variable per wire.
"""

from __future__ import annotations

import pytest

from research.hmr_native_channel.benchmark import case
from research.hmr_native_channel.native_channel import _scalar
from research.hybrid_channel.oracle import HybridProgram, same_channel, same_instrument
from research.verification_api.contracts import (
    AncillaContract,
    Domain,
    ProofRequest,
    ProofResult,
    TheoremClass,
    Verdict,
    classify_exception,
    forget_instrument,
    implies,
    restate,
)
from research.verification_api.corpus_qualification import (
    CLASSICAL_NATIVE_MAX_WIRES,
    COHERENT_PAIR_MAX_DATA,
    CaseResult,
    agreement,
    qualify,
    split_totals,
    summary,
)
from symq.circuit import UnsupportedOperation
from symq.resources import ResourceLimitExceeded


def test_implications_are_one_edge_not_a_ladder():
    assert implies(TheoremClass.FULL_QUANTUM_CHANNEL, TheoremClass.TRACED_CHANNEL)
    assert implies(TheoremClass.FULL_QUANTUM_CHANNEL, TheoremClass.FULL_QUANTUM_CHANNEL)
    assert implies(TheoremClass.TRACED_CHANNEL, TheoremClass.FULL_QUANTUM_CHANNEL) is False
    assert implies(TheoremClass.FULL_QUANTUM_CHANNEL, TheoremClass.FULL_CLASSICAL) is False
    assert implies(TheoremClass.FULL_CLASSICAL, TheoremClass.FULL_QUANTUM_CHANNEL) is False
    assert (
        implies(TheoremClass.FULL_QUANTUM_CHANNEL, TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT)
        is False
    )
    assert (
        implies(TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT, TheoremClass.FULL_QUANTUM_CHANNEL)
        is False
    )
    assert implies(TheoremClass.RESTRICTED_HMR_BRANCH, TheoremClass.FULL_QUANTUM_CHANNEL) is False


def test_equivalent_full_channel_may_be_restated_as_traced():
    result = ProofResult(
        Verdict.EQUIVALENT, TheoremClass.FULL_QUANTUM_CHANNEL, detail="checked", checked_pairs=4
    )
    traced = restate(result, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace on both sides")
    assert traced.theorem is TheoremClass.TRACED_CHANNEL
    assert traced.verdict is Verdict.EQUIVALENT
    assert traced.checked_pairs == 4
    assert "restated" in traced.detail


def test_sideways_and_upward_restatements_are_refused():
    result = ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_CLASSICAL)
    with pytest.raises(ValueError, match="does not establish"):
        restate(result, as_=TheoremClass.FULL_QUANTUM_CHANNEL, reason="wishful")
    channel = ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_QUANTUM_CHANNEL)
    with pytest.raises(ValueError, match="does not establish"):
        restate(channel, as_=TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT, reason="wishful")


def test_only_equivalent_verdicts_are_restated():
    for verdict in (
        Verdict.DIFFERENT,
        Verdict.INCONCLUSIVE,
        Verdict.UNSUPPORTED,
        Verdict.INTERNAL_ERROR,
    ):
        witness = (0, 1) if verdict is Verdict.DIFFERENT else None
        result = ProofResult(verdict, TheoremClass.FULL_QUANTUM_CHANNEL, witness=witness)
        with pytest.raises(ValueError, match="only EQUIVALENT"):
            restate(result, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace")


def test_a_different_verdict_requires_a_witness():
    with pytest.raises(ValueError, match="witness"):
        ProofResult(Verdict.DIFFERENT, TheoremClass.FULL_CLASSICAL)
    with pytest.raises(ValueError, match="witness"):
        ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_CLASSICAL, witness=(0, 1))
    assert ProofResult(Verdict.DIFFERENT, TheoremClass.FULL_CLASSICAL, witness=(3,)).proved is False
    assert ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_CLASSICAL).proved is True


def test_an_unsupported_verdict_cannot_claim_work_was_done():
    with pytest.raises(ValueError, match="non-decision"):
        ProofResult(Verdict.UNSUPPORTED, TheoremClass.FULL_CLASSICAL, checked_pairs=5)


def test_a_resource_limit_is_inconclusive_and_never_different():
    verdict = classify_exception(ResourceLimitExceeded("seconds", 30.0, 31.0))
    assert verdict is Verdict.INCONCLUSIVE
    assert verdict.decided is False
    assert verdict.is_failure_to_decide
    assert classify_exception(TimeoutError("budget")) is Verdict.INCONCLUSIVE
    assert classify_exception(MemoryError("rss")) is Verdict.INCONCLUSIVE


def test_an_out_of_grammar_gate_is_unsupported():
    verdict = classify_exception(UnsupportedOperation("unitary 'h'"))
    assert verdict is Verdict.UNSUPPORTED
    assert verdict.decided is False


def test_an_unexpected_error_is_internal_and_not_inconclusive():
    """A crash is a verifier defect. Collapsing it into ``INCONCLUSIVE`` would hide it."""
    for exc in (TypeError("bad"), ValueError("odd"), ZeroDivisionError("x")):
        verdict = classify_exception(exc)
        assert verdict is Verdict.INTERNAL_ERROR
        assert verdict is not Verdict.INCONCLUSIVE
        assert verdict.decided is False


def test_ancilla_contract_must_match_the_theorem_class():
    with pytest.raises(ValueError, match="traced"):
        AncillaContract(clean=True, traced=False).validate(TheoremClass.TRACED_CHANNEL)
    with pytest.raises(ValueError, match="retain"):
        AncillaContract(clean=True, traced=True).validate(TheoremClass.FULL_QUANTUM_CHANNEL)
    AncillaContract(clean=True, traced=True).validate(TheoremClass.TRACED_CHANNEL)
    AncillaContract(clean=False).validate(TheoremClass.FULL_QUANTUM_CHANNEL)


def test_an_empty_or_duplicated_domain_is_refused():
    with pytest.raises(ValueError, match="vacuous"):
        Domain(points=(), coherent_span=False).validate()
    with pytest.raises(ValueError, match="distinct"):
        Domain(points=(1, 1), coherent_span=False).validate()
    with pytest.raises(ValueError, match="nonnegative"):
        Domain(points=(-1,), coherent_span=False).validate()
    Domain(points=(0, 3), coherent_span=True).validate()


def test_instrument_requests_must_name_their_slots():
    with pytest.raises(ValueError, match="observed"):
        ProofRequest(
            class_=TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
            programs=("a", "b"),
            ancillas=AncillaContract(clean=True),
        ).validate()
    with pytest.raises(ValueError, match="observed slots"):
        ProofRequest(
            class_=TheoremClass.FULL_QUANTUM_CHANNEL,
            programs=("a", "b"),
            ancillas=AncillaContract(clean=True),
            observed_slots=("b0",),
        ).validate()
    ProofRequest(
        class_=TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
        programs=("a", "b"),
        ancillas=AncillaContract(clean=True),
        observed_slots=("b0",),
    ).validate()


def test_a_request_must_name_one_or_two_programs():
    with pytest.raises(ValueError, match="one or two"):
        ProofRequest(
            class_=TheoremClass.FULL_CLASSICAL,
            programs=("a", "b", "c"),
            ancillas=AncillaContract(clean=True),
        ).validate()


def test_x_on_a_clean_ancilla_disappears_after_the_trace():
    """Identity versus ``X`` on a clean ancilla.

    The full data+ancilla channels differ. After the partial trace they agree.
    ``restate`` must refuse to carry that ``DIFFERENT`` verdict onto
    ``TRACED_CHANNEL``. The traced equality is a separate proof.
    """
    copied = HybridProgram(1, 1)
    flipped = HybridProgram(1, 1).x(1)
    full = same_channel(copied, flipped, trace_ancillas=False)
    traced = same_channel(copied, flipped, trace_ancillas=True)
    assert full.equivalent is False and full.witness is not None
    assert traced.equivalent is True and traced.checked_pairs == 4
    different = ProofResult(
        Verdict.DIFFERENT, TheoremClass.FULL_QUANTUM_CHANNEL, witness=full.witness
    )
    with pytest.raises(ValueError, match="only EQUIVALENT"):
        restate(different, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace")
    separate = ProofResult(
        Verdict.EQUIVALENT, TheoremClass.TRACED_CHANNEL, checked_pairs=traced.checked_pairs
    )
    assert separate.proved is True
    assert separate.theorem is TheoremClass.TRACED_CHANNEL


def test_an_overwritten_slot_differs_as_instrument_and_agrees_as_channel():
    """Measuring into ``b0`` and then storing 0 leaves the CPTP map unchanged.

    The observed instrument differs. ``forget_instrument`` must not turn that
    ``DIFFERENT`` into a channel difference.
    """
    observed = HybridProgram(1).measure_z(0, "b0")
    overwritten = HybridProgram(1).measure_z(0, "b0").store("b0", 0)
    channel = same_channel(observed, overwritten)
    instrument = same_instrument(observed, overwritten, observed_slots=("b0",))
    assert channel.equivalent is True
    assert instrument.equivalent is False and instrument.witness is not None
    different = ProofResult(
        Verdict.DIFFERENT,
        TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
        witness=instrument.witness,
    )
    with pytest.raises(ValueError, match="only EQUIVALENT"):
        forget_instrument(different)
    forgotten = forget_instrument(
        ProofResult(
            Verdict.EQUIVALENT,
            TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
            detail="records agree",
            checked_pairs=channel.checked_pairs,
        )
    )
    assert forgotten.theorem is TheoremClass.FULL_QUANTUM_CHANNEL
    assert forgotten.verdict is Verdict.EQUIVALENT


def test_published_hmr_timing_families_cancel_phase_and_kernel():
    """The #95 families repair every debt, so ``phi0`` and every ``g_j`` are identically 0.

    Nonlinear still moves data: the timed work is the shared permutation ``F``.
    Affine leaves data in place: both the kernel and ``F`` are trivial.
    """
    samples = (("affine", 8, 4), ("nonlinear", 6, 3))
    for family, data, hmr in samples:
        program, reference = case(data, hmr, family)
        saw_nontrivial_f = False
        for assignment in range(1 << data):
            bits, phase, coefficients = _scalar(program, assignment)
            ref_bits, ref_phase, ref_coefficients = _scalar(reference, assignment)
            assert phase == 0
            assert coefficients == tuple(0 for _ in coefficients)
            assert ref_phase == 0 and ref_coefficients == ()
            assert bits == ref_bits
            data_mask = (1 << data) - 1
            if (bits & data_mask) != assignment:
                saw_nontrivial_f = True
        if family == "nonlinear":
            assert saw_nontrivial_f
        else:
            assert saw_nontrivial_f is False


def test_classical_and_coherent_width_limits_are_different_numbers():
    assert CLASSICAL_NATIVE_MAX_WIRES == 64
    assert COHERENT_PAIR_MAX_DATA == 32
    assert 35 <= CLASSICAL_NATIVE_MAX_WIRES
    assert 35 > COHERENT_PAIR_MAX_DATA


def test_undecided_rows_are_not_counted_as_agreement():
    rows = [
        CaseResult("x", 40, 10, "dev", "zdd", "inconclusive", None),
        CaseResult("x", 40, 10, "dev", "zdd-native", "inconclusive", None),
    ]
    agree, comparable, _ = agreement(rows)
    assert (agree, comparable) == (0, 0)
    assert summary(rows)["counts"] == {"zdd:inconclusive": 1, "zdd-native:inconclusive": 1}


def test_one_decided_backend_is_not_a_comparison():
    rows = [
        CaseResult("w", 35, 10, "dev", "zdd", "output_difference", 0.001),
        CaseResult("w", 35, 10, "dev", "zdd-native", "inconclusive", None, "width"),
    ]
    agree, comparable, _ = agreement(rows)
    assert (agree, comparable) == (0, 0)


@pytest.fixture(scope="module")
def corpus_rows():
    _manifest, rows = qualify(max_seconds=60.0)
    return rows


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_real_corpus_qualification_has_no_backend_disagreement(corpus_rows):
    agree, comparable, disagreements = agreement(corpus_rows)
    assert disagreements == []
    assert comparable == 19
    assert agree == comparable
    native = [row for row in corpus_rows if row.backend == "zdd-native" and row.decided]
    assert len(native) == 19
    wide = [row for row in native if row.width > COHERENT_PAIR_MAX_DATA]
    assert {row.name for row in wide} == {"c2_181", "rd84_313"}
    assert all(row.outcome == "output_difference" for row in native)
    kinds = {row.detail.split(";", 1)[0] for row in native}
    assert len(kinds) >= 2, kinds


def test_splits_stay_separate_and_c2_182_stays_unsupported(corpus_rows):
    totals = split_totals(corpus_rows)
    assert totals["dev"] == {"circuits": 5, "decided": 5, "undecided": 0}
    assert totals["holdout"] == {"circuits": 6, "decided": 6, "undecided": 0}
    assert totals["extension"] == {"circuits": 9, "decided": 8, "undecided": 1}
    unsupported = [row for row in corpus_rows if row.outcome == "unsupported"]
    assert [row.name for row in unsupported] == ["c2_182"]
    assert unsupported[0].backend == "-"
