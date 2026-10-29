"""Regression tests for the typed proof certificate and the real-circuit qualification.

Every guard here is exercised by a **mutant**: a deliberately wrong certificate, frame or
environment that the guard must reject. A test that only says "the docstring mentions this" would
pass while the guard was deleted, so each assertion below is paired with a specific mutation.

The physical reference is the merged bounded CPTP oracle (``research.hybrid_channel.oracle``),
which is an implementation independent of this adapter. The five all-coherence fixtures of the
separate public kit (PR #101) are the semantic ground truth for the counterexamples; this module
does not import that kit, so the two remain independent evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from research.hmr_native_channel.benchmark import case
from research.hmr_native_channel.native_channel import _scalar
from research.hybrid_channel.oracle import (
    HybridProgram,
    same_channel,
    same_instrument,
)
from research.verification_api.contracts import (
    AncillaContract,
    Domain,
    PhysicalFrame,
    ProofRequest,
    ProofResult,
    TheoremClass,
    Verdict,
    certifies,
    classify_exception,
    forget_instrument,
    implies,
    require_certificate,
    restate,
)
from research.verification_api.corpus_qualification import (
    BACKEND_UNAVAILABLE,
    CLASSICAL_NATIVE_MAX_WIRES,
    COHERENT_PAIR_MAX_DATA,
    INTERNAL_ERROR,
    NATIVE,
    OUTPUT_DIFFERENCE,
    PURE,
    UNSUPPORTED_INPUT,
    CaseResult,
    agreement,
    native_available,
    qualify,
    split_totals,
    summary,
)
from symq.circuit import UnsupportedOperation
from symq.resources import ResourceLimitExceeded

ROOT = Path(__file__).resolve().parents[1]
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


# --------------------------------------------------------------------------- frame helpers


def full_frame(**overrides) -> PhysicalFrame:
    """A frame that retains both quantum outputs, with the ancilla among them, and observes b0."""
    fields = {
        "programs": ("left", "right"),
        "program_sha256": (DIGEST_A, DIGEST_B),
        "domain": Domain(points=(0, 1), coherent_span=True),
        "ancillas": AncillaContract(clean=True, traced=False),
        "retained_outputs": ("data0", "ancilla0"),
        "traced_outputs": (),
        "ancilla_outputs": ("ancilla0",),
        "observed_slots": ("b0",),
    }
    fields.update(overrides)
    return PhysicalFrame(**fields)


def traced_frame(**overrides) -> PhysicalFrame:
    """The same experiment, with the ancilla traced and no classical record kept."""
    fields = {
        "programs": ("left", "right"),
        "program_sha256": (DIGEST_A, DIGEST_B),
        "domain": Domain(points=(0, 1), coherent_span=True),
        "ancillas": AncillaContract(clean=True, traced=True),
        "retained_outputs": ("data0",),
        "traced_outputs": ("ancilla0",),
        "ancilla_outputs": (),
        "observed_slots": (),
    }
    fields.update(overrides)
    return PhysicalFrame(**fields)


def channel_frame(**overrides) -> PhysicalFrame:
    return full_frame(observed_slots=(), **overrides)


# ------------------------------------------------------- 1. implications are not a ladder


def test_implications_are_one_edge_not_a_ladder():
    channel = TheoremClass.FULL_QUANTUM_CHANNEL
    assert implies(channel, TheoremClass.TRACED_CHANNEL)
    assert implies(channel, channel)
    assert implies(TheoremClass.TRACED_CHANNEL, channel) is False
    assert implies(channel, TheoremClass.FULL_CLASSICAL) is False
    assert implies(TheoremClass.FULL_CLASSICAL, channel) is False
    assert implies(channel, TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT) is False
    assert implies(TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT, channel) is False
    assert implies(TheoremClass.RESTRICTED_HMR_BRANCH, channel) is False


def test_equivalent_full_channel_can_only_be_restated_as_traced():
    result = ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_QUANTUM_CHANNEL, channel_frame())
    narrowed = restate(result, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace")
    assert narrowed.theorem is TheoremClass.TRACED_CHANNEL
    assert narrowed.verdict is Verdict.EQUIVALENT
    assert narrowed.frame.traced_outputs == ("ancilla0",)
    assert narrowed.frame.retained_outputs == ("data0",)
    assert narrowed.frame.ancillas.traced is True
    assert "not recomputed" in narrowed.detail

    # MUTANT: the same call on a sideways class must refuse, not silently keep the frame.
    with pytest.raises(ValueError, match="does not establish"):
        restate(result, as_=TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT, reason="wishful")

    # MUTANT: a classical result cannot be promoted to a quantum one.
    classical = ProofResult(
        Verdict.EQUIVALENT,
        TheoremClass.FULL_CLASSICAL,
        PhysicalFrame(
            programs=("left", "right"),
            program_sha256=(DIGEST_A, DIGEST_B),
            domain=Domain(points=(0, 1), coherent_span=False),
            ancillas=AncillaContract(clean=True),
            retained_outputs=("data0",),
        ),
    )
    with pytest.raises(ValueError, match="does not establish"):
        restate(classical, as_=TheoremClass.FULL_QUANTUM_CHANNEL, reason="wishful")


# ------------------------------------------- 2. DIFFERENT cannot cross a forgetful map


def test_different_full_channel_cannot_be_restated_as_traced():
    """The physical counterexample, then the certificate that must not transport it.

    ``identity`` versus ``X`` on a clean ancilla: the full data+ancilla channels differ, the
    reduced data channels agree. A ``DIFFERENT`` verdict is therefore not transportable.
    """
    left = HybridProgram(1, 1)
    right = HybridProgram(1, 1).x(1)
    full = same_channel(left, right, trace_ancillas=False)
    traced = same_channel(left, right, trace_ancillas=True)
    assert full.equivalent is False and full.witness is not None
    assert traced.equivalent is True and traced.checked_pairs == 4

    different = ProofResult(
        Verdict.DIFFERENT,
        TheoremClass.FULL_QUANTUM_CHANNEL,
        channel_frame(),
        witness=full.witness,
    )
    with pytest.raises(ValueError, match="refuses verdict 'different'"):
        restate(different, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace")

    # The traced equality is a separate proof with its own frame.
    separate = ProofResult(
        Verdict.EQUIVALENT, TheoremClass.TRACED_CHANNEL, traced_frame(), checked_pairs=4
    )
    assert separate.proved is True


# ------------------------------------- 3. a traced instrument never becomes a full channel


def test_traced_instrument_equality_does_not_become_full_channel_equality():
    """The P0 blocker of review comment 6500010453, on the exact admitted programs.

    L = ``store(b0, 0)``; R = ``x(ancilla)`` then ``store(b0, 0)``. Both observed reduced
    instruments agree; the retained-ancilla instruments do not; the channels behave identically.
    """
    slots = ("b0",)
    left = HybridProgram(1, 1).store("b0", 0)
    right = HybridProgram(1, 1).x(1).store("b0", 0)

    assert same_instrument(left, right, observed_slots=slots, trace_ancillas=True).equivalent
    assert not same_instrument(left, right, observed_slots=slots, trace_ancillas=False).equivalent
    assert same_channel(left, right, trace_ancillas=True).equivalent
    assert not same_channel(left, right, trace_ancillas=False).equivalent

    # A genuine reduced-instrument certificate can only become a reduced channel.
    reduced = ProofResult(
        Verdict.EQUIVALENT,
        TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
        traced_frame(observed_slots=slots),
        checked_pairs=4,
    )
    narrowed = forget_instrument(reduced)
    assert narrowed.theorem is TheoremClass.TRACED_CHANNEL
    assert narrowed.theorem is not TheoremClass.FULL_QUANTUM_CHANNEL
    assert narrowed.frame.retained_outputs == ("data0",)
    assert narrowed.frame.traced_outputs == ("ancilla0",)
    assert narrowed.frame.observed_slots == ()

    # MUTANT that the old adapter allowed: claim the retained-ancilla frame while the proof traced.
    with pytest.raises(ValueError, match="instrument claim must name"):
        ProofResult(
            Verdict.EQUIVALENT,
            TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
            channel_frame(),
        )
    forged = ProofResult(
        Verdict.EQUIVALENT,
        TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
        full_frame(observed_slots=slots),
        checked_pairs=4,
    )
    widened = forget_instrument(forged)
    assert widened.theorem is TheoremClass.FULL_QUANTUM_CHANNEL
    # ... and that stronger claim is not the reduced certificate that was actually asked for.
    assert certifies(widened, ProofRequest(narrowed.frame, TheoremClass.TRACED_CHANNEL)) is False


# --------------------------------------- 4. an overwritten slot changes only the instrument


def test_an_overwritten_slot_changes_the_instrument_and_not_the_channel():
    measured = HybridProgram(1).measure_z(0, "b0")
    overwritten = HybridProgram(1).measure_z(0, "b0").store("b0", 0)
    channel = same_channel(measured, overwritten)
    instrument = same_instrument(measured, overwritten, observed_slots=("b0",))
    assert channel.equivalent is True
    assert instrument.equivalent is False and instrument.witness is not None

    divergent = ProofResult(
        Verdict.DIFFERENT,
        TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT,
        full_frame(),
        witness=instrument.witness,
    )
    with pytest.raises(ValueError, match="refuses verdict 'different'"):
        forget_instrument(divergent)


# ------------------------------------------ 5. crashes and limits are never decisions


def test_a_resource_limit_is_inconclusive_and_never_different():
    for exc in (
        ResourceLimitExceeded("seconds", 30.0, 31.0),
        TimeoutError("budget"),
        MemoryError("rss"),
    ):
        verdict = classify_exception(exc)
        assert verdict is Verdict.INCONCLUSIVE
        assert verdict.decided is False


def test_an_internal_crash_stays_internal_and_is_never_inconclusive_or_different():
    for exc in (TypeError("bad"), ValueError("odd"), ZeroDivisionError("x")):
        verdict = classify_exception(exc)
        assert verdict is Verdict.INTERNAL_ERROR
        assert verdict is not Verdict.INCONCLUSIVE
        assert verdict is not Verdict.DIFFERENT
        assert verdict.decided is False


def test_a_non_decision_cannot_be_transported_or_claim_work():
    for verdict in (Verdict.INCONCLUSIVE, Verdict.UNSUPPORTED, Verdict.INTERNAL_ERROR):
        result = ProofResult(verdict, TheoremClass.FULL_QUANTUM_CHANNEL, channel_frame())
        assert result.proved is False
        with pytest.raises(ValueError, match="refuses verdict"):
            restate(result, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace")
        instrument = ProofResult(
            verdict, TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT, full_frame()
        )
        with pytest.raises(ValueError, match="refuses verdict"):
            forget_instrument(instrument)
    with pytest.raises(ValueError, match="non-decision"):
        ProofResult(
            Verdict.UNSUPPORTED, TheoremClass.FULL_QUANTUM_CHANNEL, channel_frame(), checked_pairs=5
        )


def test_an_unsupported_gate_is_unsupported_not_a_verdict():
    verdict = classify_exception(UnsupportedOperation("unitary 'h'"))
    assert verdict is Verdict.UNSUPPORTED
    assert verdict.decided is False


def test_a_difference_needs_a_witness_and_an_equality_must_not_carry_one():
    with pytest.raises(ValueError, match="witness"):
        ProofResult(Verdict.DIFFERENT, TheoremClass.FULL_CLASSICAL, channel_frame())
    with pytest.raises(ValueError, match="witness"):
        ProofResult(
            Verdict.EQUIVALENT, TheoremClass.FULL_CLASSICAL, channel_frame(), witness=(0, 1)
        )


# ------------------------------- 6. any contract change invalidates the certificate


@pytest.mark.parametrize(
    "field, value",
    [
        ("programs", ("left", "other")),
        ("program_sha256", (DIGEST_A, "c" * 64)),
        ("domain", Domain(points=(0,), coherent_span=False)),
        ("ancillas", AncillaContract(clean=False)),
        ("retained_outputs", ("data0", "data1")),
        ("traced_outputs", ("ancilla0", "other")),
        ("ancilla_outputs", ("data0",)),
        ("observed_slots", ("b0", "b1")),
    ],
)
def test_changing_any_frame_field_invalidates_the_certificate(field, value):
    """Either the mutated frame is refused outright, or it stops certifying the request.

    Both outcomes close the hole: a certificate must not survive a change to the experiment it
    describes. Refusal is the stronger of the two and is accepted here deliberately.
    """
    frame = traced_frame()
    request = ProofRequest(frame, TheoremClass.TRACED_CHANNEL)
    result = ProofResult(
        Verdict.EQUIVALENT, TheoremClass.TRACED_CHANNEL, frame, checked_pairs=4
    )
    assert certifies(result, request) is True
    require_certificate(result, request)

    try:
        mutated = ProofResult(
            Verdict.EQUIVALENT,
            TheoremClass.TRACED_CHANNEL,
            traced_frame(**{field: value}),
            checked_pairs=4,
        )
    except ValueError:
        return  # refused at construction: the change cannot even form a claim
    assert certifies(mutated, request) is False
    with pytest.raises(ValueError, match="certificate does not cover the request"):
        require_certificate(mutated, request)


def test_a_different_theorem_class_is_not_the_requested_certificate():
    frame = traced_frame()
    result = ProofResult(Verdict.EQUIVALENT, TheoremClass.TRACED_CHANNEL, frame)
    assert certifies(result, ProofRequest(frame, TheoremClass.TRACED_CHANNEL))
    assert certifies(result, ProofRequest(frame, TheoremClass.FULL_QUANTUM_CHANNEL)) is False
    with pytest.raises(ValueError, match="request asked"):
        require_certificate(result, ProofRequest(frame, TheoremClass.FULL_QUANTUM_CHANNEL))


def test_frame_rejects_contracts_it_cannot_support():
    # A trace claim whose ancilla contract says the ancillas are kept.
    with pytest.raises(ValueError, match="keeps the ancillas"):
        PhysicalFrame(
            programs=("left", "right"),
            program_sha256=(DIGEST_A, DIGEST_B),
            domain=Domain(points=(0,), coherent_span=True),
            ancillas=AncillaContract(clean=True, traced=False),
            retained_outputs=("data0",),
            traced_outputs=("ancilla0",),
        )
    # A trace claim with no traced output at all.
    with pytest.raises(ValueError, match="says the ancillas are traced"):
        PhysicalFrame(
            programs=("left", "right"),
            program_sha256=(DIGEST_A, DIGEST_B),
            domain=Domain(points=(0,), coherent_span=True),
            ancillas=AncillaContract(clean=True, traced=True),
            retained_outputs=("data0",),
        )
    # A "retained ancilla" that is not retained.
    with pytest.raises(ValueError, match="must be retained while they are retained"):
        PhysicalFrame(
            programs=("left", "right"),
            program_sha256=(DIGEST_A, DIGEST_B),
            domain=Domain(points=(0,), coherent_span=True),
            ancillas=AncillaContract(clean=True),
            retained_outputs=("data0",),
            ancilla_outputs=("ancilla0",),
        )
    # A full channel that quietly traced an output.
    with pytest.raises(ValueError, match="retain the ancillas, not trace them"):
        ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_QUANTUM_CHANNEL, traced_frame())
    # An output cannot be both retained and traced.
    with pytest.raises(ValueError, match="both retained and traced"):
        full_frame(traced_outputs=("data0",), ancillas=AncillaContract(clean=True, traced=True))
    # Digests must be real digests, not labels.
    with pytest.raises(ValueError, match="64 lowercase hex"):
        full_frame(program_sha256=("left", "right"))
    with pytest.raises(ValueError, match="exactly one digest"):
        full_frame(program_sha256=(DIGEST_A,))
    # An empty domain makes every implication vacuous.
    with pytest.raises(ValueError, match="vacuous"):
        Domain(points=(), coherent_span=False)
    with pytest.raises(ValueError, match="explicit bool"):
        Domain(points=(0,), coherent_span="yes")


def test_a_trace_restatement_cannot_invent_an_ancilla_to_move():
    """A frame with no retained ancilla output cannot be restated as a traced channel.

    This is the guard against silently turning "the data already agrees" into
    "the ancilla was traced", which is the same class of error as the P0 blocker.
    """
    no_ancilla = PhysicalFrame(
        programs=("left", "right"),
        program_sha256=(DIGEST_A, DIGEST_B),
        domain=Domain(points=(0, 1), coherent_span=True),
        ancillas=AncillaContract(clean=True, traced=False),
        retained_outputs=("data0",),
    )
    with pytest.raises(ValueError, match="cannot invent one"):
        no_ancilla.with_ancillas_traced()
    result = ProofResult(Verdict.EQUIVALENT, TheoremClass.FULL_QUANTUM_CHANNEL, no_ancilla)
    with pytest.raises(ValueError, match="cannot invent one"):
        restate(result, as_=TheoremClass.TRACED_CHANNEL, reason="partial trace")


def test_an_equivalent_full_channel_frame_cannot_keep_classical_records():
    with pytest.raises(ValueError, match="belong to an instrument claim"):
        ProofResult(
            Verdict.EQUIVALENT, TheoremClass.FULL_QUANTUM_CHANNEL, full_frame()
        )


# ------------------------------------- 7. HMR phase repair: exact, missing, doubled, shifted


def test_hmr_repair_cancels_exactly_and_detects_missing_or_doubled_repair():
    """The correction aligns the Kraus signs; it does not apply them twice or not at all."""
    reference = HybridProgram(3, 1).ccx(0, 1, 2)
    corrected = (
        HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(0, 1, condition="b0")
    )
    missing = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0")
    doubled = (
        HybridProgram(3, 1)
        .ccx(0, 1, 3)
        .cx(3, 2)
        .hmr(3, "b0")
        .cz(0, 1, condition="b0")
        .cz(0, 1, condition="b0")
    )
    # A correction whose monomial moved: the CZ acts on different wires than the recorded debt.
    shifted = (
        HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(1, 2, condition="b0")
    )

    assert same_channel(corrected, reference, trace_ancillas=False).equivalent
    assert same_channel(corrected, reference, trace_ancillas=True).equivalent
    for broken, label in ((missing, "missing"), (doubled, "doubled"), (shifted, "shifted")):
        verdict = same_channel(broken, reference, trace_ancillas=False)
        assert verdict.equivalent is False, f"{label} repair was not detected"
        assert verdict.witness is not None
        # And the traced comparison agrees with the full one here: the difference is not hidden.
        assert same_channel(broken, reference, trace_ancillas=True).equivalent is False


# ------------------------------------------------ 8. published #95 families: what is timed


def test_published_hmr_timing_families_repair_phase_and_kernel():
    """These families zero ``phi0`` and every ``g_j``; nonlinear still moves the data ``F``."""
    for family, data, hmr in (("affine", 8, 4), ("nonlinear", 6, 3)):
        program, reference = case(data, hmr, family)
        data_mask = (1 << data) - 1
        saw_moved_data = False
        for assignment in range(1 << data):
            bits, phase, coefficients = _scalar(program, assignment)
            ref_bits, ref_phase, ref_coefficients = _scalar(reference, assignment)
            assert phase == 0
            assert coefficients == tuple(0 for _ in coefficients)
            assert ref_phase == 0 and ref_coefficients == ()
            assert bits == ref_bits
            saw_moved_data |= (bits & data_mask) != assignment
        assert saw_moved_data is (family == "nonlinear")


# ------------------------------------------------------- 9. QCEC accounting, both modes


def test_classical_and_coherent_width_limits_are_different_numbers():
    assert CLASSICAL_NATIVE_MAX_WIRES == 64
    assert COHERENT_PAIR_MAX_DATA == 32
    assert 35 <= CLASSICAL_NATIVE_MAX_WIRES
    assert 35 > COHERENT_PAIR_MAX_DATA


def test_undecided_and_unavailable_rows_are_not_agreement():
    rows = [
        CaseResult("x", 40, 10, "dev", PURE, "inconclusive"),
        CaseResult("x", 40, 10, "dev", NATIVE, "inconclusive"),
    ]
    assert agreement(rows) == (0, 0, [])
    unavailable = [
        CaseResult("x", 40, 10, "dev", PURE, OUTPUT_DIFFERENCE, verify_seconds=0.001),
        CaseResult("x", 40, 10, "dev", NATIVE, BACKEND_UNAVAILABLE, detail="not built"),
    ]
    assert agreement(unavailable) == (0, 0, [])
    assert summary(unavailable)["counts"] == {
        f"{PURE}:{OUTPUT_DIFFERENCE}": 1,
        f"{NATIVE}:{BACKEND_UNAVAILABLE}": 1,
    }
    totals = split_totals(unavailable)
    assert totals["dev"] == {"circuits": 1, "decided": 1, "undecided": 0, "unavailable": 0}


def test_an_internal_error_is_reported_with_its_diagnostic_and_never_as_unsupported():
    rows = [
        CaseResult(
            "x", 20, 10, "dev", PURE, INTERNAL_ERROR, detail="ZeroDivisionError: boom"
        )
    ]
    counts = summary(rows)["counts"]
    assert counts == {f"{PURE}:{INTERNAL_ERROR}": 1}
    assert "unsupported" not in counts
    assert rows[0].detail.startswith("ZeroDivisionError")


def test_missing_native_is_a_capability_gap_not_an_unsupported_circuit(monkeypatch):
    # Import the live module object: another audit suite may have reloaded ``research.*``, and a
    # stashed function reference would keep the stale globals.
    import research.verification_api.corpus_qualification as cq

    monkeypatch.setattr(cq, "has_native", lambda: False)
    assert cq.backend_problem(NATIVE, 20) == "native C extension not built"
    assert cq.backend_problem(PURE, 20) is None
    assert cq.requested_backends() == (PURE,)
    with pytest.raises(RuntimeError, match="environment failure"):
        cq.requested_backends(require_native=True)


def test_native_width_ceiling_is_a_capability_gap(monkeypatch):
    import research.verification_api.corpus_qualification as cq

    # Patch the predicate the harness itself consults: in pure-Python mode ``NATIVE`` is not even
    # registered, so patching only ``has_native`` would leave the width branch unreachable.
    monkeypatch.setattr(cq, "native_available", lambda: True)
    monkeypatch.setitem(cq.BACKENDS, NATIVE, object())
    assert cq.backend_problem(NATIVE, cq.CLASSICAL_NATIVE_MAX_WIRES) is None
    assert cq.backend_problem(NATIVE, cq.CLASSICAL_NATIVE_MAX_WIRES + 1) == (
        "width 65 exceeds the 64-wire native mask"
    )


@pytest.fixture(scope="module")
def corpus_rows():
    _manifest, rows = qualify(max_seconds=60.0)
    return rows


def test_real_corpus_decides_every_supported_circuit_with_the_pure_backend(corpus_rows):
    """Mode-independent: whichever engines this environment has, ``zdd`` decides all 19."""
    pure = [row for row in corpus_rows if row.backend == PURE]
    assert len(pure) == 19
    assert all(row.decided for row in pure), [
        (row.name, row.outcome, row.detail) for row in pure if not row.decided
    ]
    assert all(row.outcome == OUTPUT_DIFFERENCE for row in pure)
    by_split = {
        split: totals["decided"] for split, totals in split_totals(corpus_rows).items()
    }
    assert by_split == {"dev": 5, "holdout": 6, "extension": 8}


def test_real_corpus_decides_every_supported_circuit_in_this_environment(corpus_rows):
    """With the C core built, both engines must decide all 19 supported circuits."""
    if not native_available():
        pytest.skip("this environment did not build the C core; the pure-Python job covers it")
    agree, comparable, disagreements = agreement(corpus_rows)
    assert disagreements == []
    assert comparable == 19
    assert agree == 19
    for backend in (PURE, NATIVE):
        decided = [row for row in corpus_rows if row.backend == backend and row.decided]
        assert len(decided) == 19, backend
        assert all(row.outcome == OUTPUT_DIFFERENCE for row in decided)
    native = [row for row in corpus_rows if row.backend == NATIVE and row.decided]
    wide = {row.name for row in native if row.width > COHERENT_PAIR_MAX_DATA}
    assert wide == {"c2_181", "rd84_313"}
    kinds = {row.mutation for row in native}
    assert len(kinds) >= 2, kinds


def test_splits_stay_separate_and_c2_182_is_the_only_unsupported_input(corpus_rows):
    totals = split_totals(corpus_rows)
    assert totals["dev"] == {"circuits": 5, "decided": 5, "undecided": 0, "unavailable": 0}
    assert totals["holdout"] == {"circuits": 6, "decided": 6, "undecided": 0, "unavailable": 0}
    assert totals["extension"] == {"circuits": 9, "decided": 8, "undecided": 1, "unavailable": 0}
    unsupported = [row for row in corpus_rows if row.outcome == UNSUPPORTED_INPUT]
    assert [row.name for row in unsupported] == ["c2_182"]
    assert unsupported[0].backend == "-"


_PURE_PYTHON_PROBE = """
import json
from research.verification_api.corpus_qualification import (
    agreement, qualify, split_totals, summary,
)
_manifest, rows = qualify(max_seconds=60.0)
agree, comparable, disagreements = agreement(rows)
print(json.dumps({
    "agree": agree,
    "comparable": comparable,
    "disagreements": disagreements,
    "splits": split_totals(rows),
    "counts": summary(rows)["counts"],
    "decided_pure": len([
        row for row in rows if row.backend == "zdd" and row.decided
    ]),
    "native_rows": len([row for row in rows if row.backend == "zdd-native"]),
}))
"""

_BLOCK_NATIVE = """
import importlib.abc
import sys


class _NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "symq.backends.zdd_native":
            raise ImportError("blocked: pure-python simulation")
        return None


sys.meta_path.insert(0, _NoNative())
"""


def test_pure_python_mode_still_decides_all_nineteen(tmp_path):
    """Reproduce the pure-Python CI job: no C extension, and the corpus must still be decided.

    The extension is blocked at import time in a subprocess, so this is the real code path the
    failing CI job took -- not a monkeypatched flag.
    """
    script = tmp_path / "probe.py"
    script.write_text(_BLOCK_NATIVE + textwrap.dedent(_PURE_PYTHON_PROBE), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "src"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["decided_pure"] == 19
    assert payload["native_rows"] == 0, "an unavailable backend must not produce rows"
    assert payload["comparable"] == 0, "one engine is not a comparison"
    assert payload["agree"] == 0
    assert payload["disagreements"] == []
    assert payload["splits"]["dev"]["decided"] == 5
    assert payload["splits"]["holdout"]["decided"] == 6
    assert payload["splits"]["extension"]["decided"] == 8
    assert payload["counts"] == {
        "zdd:output_difference": 19,
        "-:unsupported_input": 1,
    }
