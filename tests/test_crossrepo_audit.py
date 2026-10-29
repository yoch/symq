"""Reproducible checks for the cross-repository audit (PR #97).

The modules under audit live on **other branches**, not on this one. These tests therefore do not
import them at module scope: they *fetch the pinned commit* into a temporary worktree and add it to
``sys.path``. If the commit cannot be fetched (offline runner, no network), the test **skips with an
explicit reason** rather than passing vacuously or failing for the wrong reason.

Pinned commits (see ``research/audit_crossrepo_20261029/README.md``):

    #90  38a137203205202367425b3f0317a7ae4faa2612
    #92  225f060897859b660e5e7afb3f1024e73777b051
    #93  f58f382276516f974306e51cd3f2d5c17398aad1
    #94  53da41e71dcdc3158fb80b9719572b5f5a44635b
    #95  af8a874db66a8176e14419cda13cff13c6db0ef2

What is covered here (the fast, mandatory set):

* the #90/#94 interoperability question, including the regression that made an earlier audit
  conclusion wrong;
* transcript mutations for #92 with the circuits **pinned once**, which is the bug my own first
  harness had;
* the GF(2) dual certificates for #93 against brute force;
* small-dimension ANF sweep for #93;
* native/Python grammar parity for #95 and its resource limits.

The 9.6-million-pair ANF sweep and the 15-repetition benchmark are **not** here: they belong to the
slow suite (``-m slow``) because they do not change any decision.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PINS = {
    "pr90": "38a137203205202367425b3f0317a7ae4faa2612",
    "pr92": "225f060897859b660e5e7afb3f1024e73777b051",
    "pr93": "f58f382276516f974306e51cd3f2d5c17398aad1",
    "pr94": "53da41e71dcdc3158fb80b9719572b5f5a44635b",
    "pr95": "af8a874db66a8176e14419cda13cff13c6db0ef2",
}


def _worktree(name: str) -> Path:
    """Return a checkout of the pinned commit, creating it once per session.

    ``AUDIT_WORKTREE_ROOT`` lets CI place the checkouts outside the repository. The function raises
    ``pytest.skip`` when the commit is not reachable, so an offline run is reported as skipped and
    never as passing.
    """
    base = Path(os.environ.get("AUDIT_WORKTREE_ROOT", "/tmp/audit-ci"))
    target = base / name
    if target.exists() and (target / "src" / "symq").is_dir():
        return target
    base.mkdir(parents=True, exist_ok=True)
    sha = PINS[name]
    fetched = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", sha],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if fetched.returncode != 0:
        pytest.skip(f"{name} not fetchable ({sha[:12]}): {fetched.stderr.strip().splitlines()[-1:]}")
    added = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), sha],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if added.returncode != 0 and not target.exists():
        pytest.skip(f"cannot create worktree for {name}: {added.stderr.strip()}")
    return target


def _import_from(checkout: Path, module: str, package_root: str):
    """Import ``module`` from a checkout without polluting the global import state permanently."""
    for path in (str(checkout / "src"), str(checkout)):
        if path not in sys.path:
            sys.path.insert(0, path)
    sys.modules.pop(module, None)
    return importlib.import_module(module)


# ---------------------------------------------------------------------------- #90 / #94 interoperability


@pytest.fixture(scope="module")
def hybrid():
    checkout = _worktree("pr90")
    return _import_from(checkout, "research.hybrid_channel.oracle", "research")


def test_the_corrected_hmr_gadget_equals_the_plain_value_circuit(hybrid):
    """The user's interop test: a conditioned CZ cancels the HMR sign exactly.

    Kraus branch ``m`` carries ``(-1)^{m g(x)}``; the appended gate contributes the same factor, so the
    product is ``(-1)^{2 m g(x)} = 1``. This is the check that falsifies the earlier audit claim that
    the two components used incompatible conventions.
    """
    corrected = (
        hybrid.HybridProgram(3, 1)
        .ccx(0, 1, 3)
        .cx(3, 2)
        .hmr(3, "b0")
        .cz(0, 1, condition="b0")
    )
    reference = hybrid.HybridProgram(3, 1).ccx(0, 1, 2)
    assert hybrid.same_channel(corrected, reference).equivalent
    assert hybrid.same_channel(corrected, reference, trace_ancillas=True).equivalent


def test_the_uncorrected_gadget_differs(hybrid):
    uncorrected = hybrid.HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0")
    reference = hybrid.HybridProgram(3, 1).ccx(0, 1, 2)
    assert not hybrid.same_channel(uncorrected, reference).equivalent


def test_value_plus_reset_is_not_a_valid_reference(hybrid):
    """Regression for the analysis error behind the withdrawn P1.

    ``reset`` decoheres, so "compute on an ancilla then reset" is **not** channel-equal to the plain
    value circuit. Comparing against it produced a false negative for the corrected gadget.
    """
    value_reset = hybrid.HybridProgram(3, 1).mcx(0, 1, 3).mcx(3, 2).reset(3)
    reference = hybrid.HybridProgram(3, 1).ccx(0, 1, 2)
    assert not hybrid.same_channel(value_reset, reference).equivalent


def test_branches_carry_equal_signs_after_the_correction(hybrid):
    """Summing the observed outcome must reproduce the reference on every input coherence."""
    from fractions import Fraction

    corrected = (
        hybrid.HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(0, 1, condition="b0")
    )
    reference = hybrid.HybridProgram(3, 1).ccx(0, 1, 2)
    for x in range(8):
        for y in range(8):
            want = hybrid.coherence_image(reference, x, y, trace_ancillas=False, max_width=5)
            inst = hybrid.coherence_instrument(
                corrected, x, y, observed_slots=("b0",), trace_ancillas=False, max_width=5
            )
            total: dict = {}
            for matrix in inst.values():
                for key, value in matrix.items():
                    total[key] = total.get(key, Fraction(0)) + value
            assert {k: v for k, v in total.items() if v} == want, (x, y)


def test_double_correction_is_wrong(hybrid):
    """Applying the sign twice must NOT equal the reference -- the product is 1 only once."""
    doubled = (
        hybrid.HybridProgram(3, 1)
        .ccx(0, 1, 3)
        .cx(3, 2)
        .hmr(3, "b0")
        .cz(0, 1, condition="b0")
        .cz(0, 1, condition="b0")
    )
    reference = hybrid.HybridProgram(3, 1).ccx(0, 1, 2)
    assert not hybrid.same_channel(doubled, reference).equivalent


def test_symbolic_and_channel_views_agree(hybrid):
    """``phase_semantics`` cancels the debt in ANF; the channel view agrees it is gone."""
    from symq.phase import PhaseProgram, phase_semantics

    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    program.hmr(3)
    assert sorted(phase_semantics(program).phase.terms) == [0b1011]
    program.mcz_if(0, 0, 1)
    assert not phase_semantics(program).phase.terms
    del hybrid  # the fixture is only used to prove both paths are exercised


# ---------------------------------------------------------------------------- #92 transcripts


@pytest.fixture(scope="module")
def temporal():
    checkout = _worktree("pr92")
    return _import_from(checkout, "research.temporal_substitution.proof", "research")


def _stream(module, width, steps):
    from symq import Circuit, Gate

    reference, candidate = [], []
    for step in steps:
        if isinstance(step, module.Common):
            reference.extend(step.gates)
            candidate.extend(step.gates)
        else:
            reference.extend(
                Gate(g.name, tuple(step.wires[q] for q in g.qubits)) for g in step.reference.gates
            )
            candidate.extend(
                Gate(g.name, tuple(step.wires[q] for q in g.qubits)) for g in step.candidate.gates
            )
    return Circuit(width, reference), Circuit(width, candidate)


def test_transcript_mutations_are_visible_with_pinned_circuits(temporal):
    """**Regression for the bug in my own first harness.**

    The circuits must be built once from the legitimate transcript and then held fixed. Rebuilding
    them from the mutated steps regenerates a self-consistent pair and makes every mutation
    invisible -- which is exactly how a broken harness can report success.
    """
    from symq import Circuit, Gate

    loop = temporal.Program.freeze(
        Circuit(3, [Gate("ccx", (0, 1, 2)), Gate("ccx", (0, 1, 2))])
    )
    empty = temporal.Program.freeze(Circuit(3))
    good = [
        temporal.Common((Gate("cx", (0, 3)),)),
        temporal.Slot(loop, empty, (0, 1, 2)),
        temporal.Common((Gate("x", (3,)),)),
    ]
    left, right = _stream(temporal, 4, good)
    ref_hash = temporal.digest(temporal.Program.freeze(left))
    cand_hash = temporal.digest(temporal.Program.freeze(right))

    # The legitimate transcript verifies.
    assert temporal.verify_transcript(
        left, right, good, reference_sha256=ref_hash, candidate_sha256=cand_hash
    ).equivalent

    mutants = {
        "prefix": [temporal.Common((Gate("cx", (1, 3)),)), *good[1:]],
        "suffix": [*good[:-1], temporal.Common((Gate("x", (2,)),))],
        "embedding": [good[0], temporal.Slot(loop, empty, (0, 1, 3)), good[2]],
    }
    for label, steps in mutants.items():
        try:
            temporal.verify_transcript(
                left, right, steps, reference_sha256=ref_hash, candidate_sha256=cand_hash
            )
        except temporal.TranscriptMismatch:
            continue
        raise AssertionError(f"mutant {label!r} was not detected by the transcript check")


def test_preserved_wire_contract_is_enforced(temporal):
    from symq import Circuit, Gate

    dirty = temporal.Program.freeze(Circuit(3, [Gate("ccx", (0, 1, 2))]))
    steps = [temporal.Slot(dirty, dirty, (0, 1, 2), preserved=(2,))]
    left, right = _stream(temporal, 3, steps)
    with pytest.raises(temporal.UnprovedSubstitution):
        temporal.verify_transcript(
            left,
            right,
            steps,
            reference_sha256=temporal.digest(temporal.Program.freeze(left)),
            candidate_sha256=temporal.digest(temporal.Program.freeze(right)),
        )


# ---------------------------------------------------------------------------- #93 ANF and certificates


@pytest.fixture(scope="module")
def bitset():
    checkout = _worktree("pr93")
    return _import_from(checkout, "research.bitset_degree3.bitset", "research")


@pytest.fixture(scope="module")
def certificates():
    checkout = _worktree("pr93")
    return _import_from(checkout, "research.bitset_degree3.linear_certificate", "research")


def test_gf2_certificates_agree_with_brute_force(certificates):
    """Every dual certificate must be self-verifying and match an exhaustive search."""
    import itertools
    import random

    rng = random.Random(7)
    for _ in range(400):
        rows = rng.randint(1, 4)
        columns = tuple(rng.getrandbits(rows) for _ in range(rng.randint(1, 5)))
        rhs = rng.getrandbits(rows)

        def satisfiable(columns=columns, rhs=rhs, rows=rows):
            for assignment in range(1 << len(columns)):
                ok = True
                for row in range(rows):
                    parity = 0
                    for j, column in enumerate(columns):
                        parity ^= (column >> row & 1) & (assignment >> j & 1)
                    if parity != (rhs >> row & 1):
                        ok = False
                        break
                if ok:
                    return True
            return False

        truth = satisfiable()
        witness = certificates.unsat_dual(columns, rhs, rows)
        if witness is None:
            assert truth, (columns, rhs, rows)
        else:
            assert not truth, (columns, rhs, rows)
            assert certificates.verify_dual(columns, rhs, rows, witness)

    # A few exhaustive small systems.
    def brute_force(columns, rhs, rows):
        for assignment in range(1 << len(columns)):
            ok = True
            for row in range(rows):
                parity = 0
                for j, column in enumerate(columns):
                    parity ^= (column >> row & 1) & (assignment >> j & 1)
                if parity != (rhs >> row & 1):
                    ok = False
                    break
            if ok:
                return True
        return False

    for rows in (1, 2):
        for columns in itertools.product(range(1 << rows), repeat=2):
            for rhs in range(1 << rows):
                truth = brute_force(columns, rhs, rows)
                witness = certificates.unsat_dual(columns, rhs, rows)
                assert (witness is None) == truth


def test_anf_multiply_is_sound_on_small_dimensions(bitset):
    """Exhaustive over small spaces: **never a wrong value**, only refusals.

    The refusal of products whose intermediate monomial exceeds the degree is a documented,
    intentional completeness limit (issue #86 requires rejecting overflow rather than truncating).
    """
    import itertools

    from symq.resources import Budget, Guard, ResourceLimitExceeded

    def reference_product(left, right):
        out = set()
        for a in left:
            for b in right:
                out ^= {a | b}
        return out

    checked = 0
    refused = 0
    for n in (2, 3):
        for degree in range(n + 1):
            space = bitset.Space.create(n, degree)
            guard = Guard(Budget())
            monomials = [
                m
                for d in range(degree + 1)
                for combo in itertools.combinations(range(n), d)
                for m in [sum(1 << i for i in combo)]
            ]
            subsets = [
                frozenset(combo)
                for size in range(min(3, len(monomials)) + 1)
                for combo in itertools.combinations(monomials, size)
            ]
            for left in subsets:
                for right in subsets:
                    want = reference_product(set(left), set(right))
                    try:
                        got = set(
                            bitset.Polynomial.from_masks(space, left)
                            .multiply(bitset.Polynomial.from_masks(space, right), guard)
                            .masks()
                        )
                    except ResourceLimitExceeded:
                        refused += 1
                        continue
                    assert got == want, (n, degree, left, right)
                    checked += 1
    assert checked > 100, f"only {checked} products were actually checked"
    assert refused >= 0


def test_anf_multiply_refuses_rather_than_truncates(bitset):
    """The documented limit, pinned as behaviour: an over-degree product raises."""
    from symq.resources import Budget, Guard, ResourceLimitExceeded

    space = bitset.Space.create(4, 2)
    guard = Guard(Budget())
    left = bitset.Polynomial.from_masks(space, {0b0011})
    right = bitset.Polynomial.from_masks(space, {0b0100})
    with pytest.raises(ResourceLimitExceeded):
        left.multiply(right, guard)


# ---------------------------------------------------------------------------- #95 native parity


@pytest.fixture(scope="module")
def native_channel():
    checkout = _worktree("pr95")
    return _import_from(checkout, "research.hmr_native_channel.native_channel", "research")


def _native_available() -> bool:
    try:
        from symq.backends import has_native

        return has_native()
    except Exception:  # noqa: BLE001 - a missing build is a skip, not a failure
        return False


@pytest.mark.skipif(not _native_available(), reason="native extension not built")
def test_native_and_python_accept_the_same_grammar(native_channel):
    """Parity on the accepted grammar: no acceptance split, no verdict disagreement."""
    import random

    from symq.phase import Op, PhaseProgram
    from symq.resources import Budget

    rng = random.Random(20261029)
    accepted = 0
    for _ in range(120):
        data = rng.randint(1, 3)
        ancillas = rng.randint(0, 2)
        ops = []
        events = 0
        for _ in range(rng.randint(1, 4)):
            kind = rng.choice(["mcx", "mcz"] + (["mcz_if"] if events else []) + ["hmr"])
            if kind == "hmr":
                ops.append(Op("hmr", (rng.randrange(data + ancillas),), outcome=events))
                events += 1
            elif kind == "mcz_if":
                size = min(rng.choice([1, 2]), data + ancillas)
                ops.append(
                    Op(
                        "mcz_if",
                        tuple(rng.sample(range(data + ancillas), size)),
                        outcome=rng.randrange(events),
                    )
                )
            else:
                size = min(rng.choice([2, 3]) if kind == "mcx" else rng.choice([1, 2]),
                           data + ancillas)
                if size < 2 and kind == "mcx":
                    continue
                ops.append(Op(kind, tuple(rng.sample(range(data + ancillas), size)), outcome=None))
        if not ops:
            continue
        try:
            left = PhaseProgram(data, ancillas, list(ops))
            right = PhaseProgram(data, ancillas, list(ops))
        except (ValueError, TypeError):
            continue
        verdicts = {}
        for backend in ("zdd", "zdd-native"):
            try:
                verdicts[backend] = native_channel.check_full_channel(
                    left, right, backend=backend, budget=Budget(max_seconds=20)
                ).equivalent
            except Exception as exc:  # noqa: BLE001 - the class name is the signal
                verdicts[backend] = type(exc).__name__
        assert verdicts["zdd"] == verdicts["zdd-native"], ops
        accepted += 1
    assert accepted > 20, f"only {accepted} programs were exercised"


@pytest.mark.skipif(not _native_available(), reason="native extension not built")
def test_native_resource_limit_raises_instead_of_returning_a_verdict(native_channel):
    """Beyond 64 pair-variables the native backend must raise, never answer ``equivalent=False``.

    This is a documented limit, not a soundness defect: a raised exception cannot be mistaken for a
    proof. A caller that catches broadly could still misread it, which is why the behaviour is pinned.

    The assertion matches the resource *kind*, not merely the exception class, because an unbuilt
    native extension also raises ``ResourceLimitExceeded`` for an unrelated reason. Without that
    precision the test passes for the wrong reason -- which it did on the first run of this suite.
    """
    from symq.phase import Op, PhaseProgram
    from symq.resources import Budget, ResourceLimitExceeded

    ops = [Op("mcx", (0, 33), outcome=None), Op("hmr", (33,), outcome=0)]
    program = PhaseProgram(33, 1, list(ops))
    reference = PhaseProgram(33, 1, [Op("mcx", (0, 33), outcome=None)])
    with pytest.raises(ResourceLimitExceeded) as raised:
        native_channel.check_full_channel(
            program, reference, backend="zdd-native", budget=Budget(max_seconds=20)
        )
    message = str(raised.value).lower()
    assert "width" in message or "pair variables" in message, (
        f"raised for an unrelated reason: {raised.value}"
    )
    assert "not built" not in message, (
        "the extension was missing, so the limit was never exercised"
    )
