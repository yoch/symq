"""Second-pass qualification: the #98 public kit and #94's new multi-debt field-MAC gadget.

Pinned sources:

    #98  9d0e0a3546d152ec3aa5ad79d1f582c7997bd4d3   (public qualification kit)
    #94  ddd64606693042259fa76e1fe39dc161b0e34bcd   (multi-output field-MAC HMR case)

Everything here is public code. No private fixture, path or payload is referenced.

Three questions are answered, and they are different:

1. **Does the public field oracle agree with #94's synthesised repair on a real multi-debt
   gadget?** #94's own test checks basis branches through `run_program`. This module additionally
   checks **off-diagonal coherences** with the #90 CPTP oracle, which is the stronger statement and
   the one a channel claim needs.

2. **Do the new multi-debt corrections survive mutation?** A synthesised repair that cannot be
   broken is not evidence that it does anything.

3. **Can #95 handle a 36-bit coherent data contract?** Three 12-bit registers need 72 pair
   variables, above the native 64 limit. The algebraic precondition must be *rejected*, never
   assumed.
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
    "pr94_new": "ddd64606693042259fa76e1fe39dc161b0e34bcd",
    "pr95": "af8a874db66a8176e14419cda13cff13c6db0ef2",
    "pr98": "9d0e0a3546d152ec3aa5ad79d1f582c7997bd4d3",
}


def _worktree(name: str) -> Path:
    base = Path(os.environ.get("AUDIT_WORKTREE_ROOT", "/tmp/audit-ci"))
    target = base / name
    if target.exists() and (target / "src" / "symq").is_dir():
        return target
    base.mkdir(parents=True, exist_ok=True)
    sha = PINS[name]
    fetched = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", sha],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if fetched.returncode != 0:
        pytest.skip(f"{name} not fetchable ({sha[:12]})")
    added = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), sha],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if added.returncode != 0 and not target.exists():
        pytest.skip(f"cannot create worktree for {name}: {added.stderr.strip()}")
    return target


def _import_from(checkout: Path, module: str):
    """Import a module from a checkout, evicting any same-named package first.

    ``research`` is a namespace that exists in this repository too, so a plain re-import would keep
    resolving to the *audit* checkout instead of the PR worktree. Clearing the cached top-level
    package is what makes the path change take effect.
    """
    for path in (str(checkout), str(checkout / "src")):
        if path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, str(checkout / "src"))
    sys.path.insert(0, str(checkout))
    top = module.split(".")[0]
    for name in [n for n in sys.modules if n == top or n.startswith(top + ".")]:
        del sys.modules[name]
    return importlib.import_module(module)


def _native_built() -> bool:
    try:
        from symq.backends import has_native

        return has_native()
    except Exception:  # noqa: BLE001 - a missing build is a skip, not a failure
        return False


# ------------------------------------------------------------------ the public kit itself


def test_the_public_kit_oracle_runs_for_both_degrees():
    """#98's standalone field oracle must produce a report for GF(4) and GF(8).

    It is stdlib-only, so this also confirms it carries no hidden dependency on another branch.
    """
    checkout = _worktree("pr98")
    for degree in (2, 3):
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "research.public_qualification.field_hmr_reference",
                "--degree",
                str(degree),
            ],
            cwd=str(checkout),
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(checkout / "src")},
        )
        assert done.returncode == 0, done.stderr[-800:]
        assert "oracle" in done.stdout or "modulus_binary" in done.stdout


def test_the_public_kit_supplies_no_private_payload():
    """Guard the confidentiality constraint: the kit must not create an external dependency.

    The check is textual and deliberately narrow: it looks for an import or a path manipulation that
    would reach outside SymQ, which is what the repository rules forbid.
    """
    checkout = _worktree("pr98")
    offenders = []
    for path in (checkout / "research" / "public_qualification").rglob("*.py"):
        text = path.read_text()
        for needle in ("import external reference project", "from external reference project", "/external reference project/", "sys.path.insert"):
            if needle in text:
                offenders.append((path.name, needle))
    assert not offenders, offenders


# ------------------------------------------------------------------ #94 field MAC: channel level
#
# The gadget is **reimplemented here** from its specification rather than imported from the PR's test
# module. Importing it would drag in the `research.hmr_feedback` namespace, which collides with this
# repository's own `research/` package, and more importantly an imported builder would make the check
# a restatement rather than an independent reconstruction.


def _reduce_poly(poly: int, degree: int, irreducible: int) -> int:
    while poly.bit_length() > degree:
        poly ^= irreducible << (poly.bit_length() - degree - 1)
    return poly


def _field_multiply(a: int, b: int, degree: int, irreducible: int) -> int:
    result = 0
    for i in range(degree):
        for j in range(degree):
            if (a >> i & 1) and (b >> j & 1):
                result ^= 1 << (i + j)
    return _reduce_poly(result, degree, irreducible)


def _build_field_mac(degree: int, irreducible: int):
    """Rebuild #94's multi-debt field MAC from its description.

    Data wires are A, B and accumulator C (``degree`` bits each). A product register of ``degree``
    ancillas is computed by schoolbook convolution-and-reduce, folded into C, then each product bit is
    HMR'd -- which leaves one phase debt per product bit.
    """
    _checkout = _worktree("pr94_new")
    from symq.phase import PhaseProgram

    data = 3 * degree
    raw = PhaseProgram(data, degree)
    reference = PhaseProgram(data, degree)
    for i in range(degree):
        for j in range(degree):
            word = _reduce_poly(1 << (i + j), degree, irreducible)
            for k in range(degree):
                if word >> k & 1:
                    raw.ccx(i, degree + j, data + k)
                    reference.ccx(i, degree + j, 2 * degree + k)
    for k in range(degree):
        raw.cx(data + k, 2 * degree + k)
    for k in range(degree):
        raw.hmr(data + k)
    return raw, reference


def _synthesize(program, degree):
    checkout = _worktree("pr94_new")
    repair = _import_from(checkout, "research.hmr_feedback.repair")
    return repair.synthesize_feedback(
        program, max_arity=2, max_data=3 * degree, max_candidates=200, max_ops=512
    )


@pytest.fixture(scope="module")
def hybrid():
    checkout = _worktree("pr90")
    return _import_from(checkout, "research.hybrid_channel.oracle")


def _to_hybrid(module, program):
    """Translate a PhaseProgram into the #90 oracle's HybridProgram."""
    instance = module.HybridProgram(data=program.data, ancillas=program.ancillas)
    for op in program.ops:
        if op.kind == "mcx":
            instance.mcx(*op.qubits)
        elif op.kind == "cx":
            instance.cx(*op.qubits)
        elif op.kind == "hmr":
            instance.hmr(op.qubits[0], f"b{op.outcome}")
        elif op.kind == "mcz_if":
            if len(op.qubits) == 2:
                instance.cz(*op.qubits, condition=f"b{op.outcome}")
            else:
                instance.z(*op.qubits, condition=f"b{op.outcome}")
        else:  # pragma: no cover - the gadget uses only these four
            raise AssertionError(f"untranslatable op {op.kind!r}")
    return instance


def test_the_reconstructed_gadget_matches_the_prs_own_builder():
    """Sanity: my independent rebuild must produce the same programme as #94's own builder.

    If these diverge, every conclusion below would be about my reconstruction rather than the PR.
    """
    checkout = _worktree("pr94_new")
    spec = importlib.util.spec_from_file_location(
        "field_mac_case", checkout / "tests" / "test_hmr_field_mac_research.py"
    )
    theirs_module = importlib.util.module_from_spec(spec)
    # The PR test imports `research.hmr_feedback`, so its checkout must win on sys.path here.
    for path in (str(checkout / "src"), str(checkout)):
        if path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, str(checkout / "src"))
    sys.path.insert(0, str(checkout))
    for name in [n for n in sys.modules if n == "research" or n.startswith("research.")]:
        del sys.modules[name]
    spec.loader.exec_module(theirs_module)

    for degree, irreducible in ((2, 0b111), (3, 0b1011)):
        theirs_raw, theirs_ref = theirs_module._build(degree, irreducible)
        mine_raw, mine_ref = _build_field_mac(degree, irreducible)
        assert [(o.kind, o.qubits, o.outcome) for o in theirs_raw.ops] == [
            (o.kind, o.qubits, o.outcome) for o in mine_raw.ops
        ], degree
        assert [(o.kind, o.qubits) for o in theirs_ref.ops] == [
            (o.kind, o.qubits) for o in mine_ref.ops
        ], degree


def test_gf4_field_mac_is_equivalent_as_a_full_channel(hybrid):
    """**Off-diagonal check that the PR's own test does not perform.**

    #94 verifies basis branches through `run_program`. A channel claim also needs every `|x><y|`,
    which is what distinguishes a real feedback correction from mere outcome dephasing.
    """
    raw, reference = _build_field_mac(2, 0b111)
    repaired, receipt = _synthesize(raw, 2)
    assert receipt.repairs, "the synthesiser produced no correction"
    full = hybrid.same_channel(
        _to_hybrid(hybrid, repaired),
        _to_hybrid(hybrid, reference),
        trace_ancillas=False,
        max_width=9,
        max_branches=64,
    )
    assert full.equivalent, full.witness
    traced = hybrid.same_channel(
        _to_hybrid(hybrid, repaired),
        _to_hybrid(hybrid, reference),
        trace_ancillas=True,
        max_width=9,
        max_branches=64,
    )
    assert traced.equivalent, traced.witness


def test_gf4_field_mac_uncorrected_is_not_equivalent(hybrid):
    """The correction must be load-bearing: without it the channel differs."""
    raw, reference = _build_field_mac(2, 0b111)
    result = hybrid.same_channel(
        _to_hybrid(hybrid, raw),
        _to_hybrid(hybrid, reference),
        trace_ancillas=False,
        max_width=9,
        max_branches=64,
    )
    assert not result.equivalent


@pytest.mark.parametrize("degree,irreducible", [(2, 0b111), (3, 0b1011)])
def test_field_mac_repairs_every_event(degree, irreducible):
    """Each measurement event must receive at least one correction, and none may be dropped."""
    from symq.phase import phase_semantics

    raw, _reference = _build_field_mac(degree, irreducible)
    repaired, receipt = _synthesize(raw, degree)
    assert {repair.outcome for repair in receipt.repairs} == set(range(degree))
    assert not phase_semantics(repaired).violations()


def test_dropping_any_single_field_mac_correction_is_detected():
    """Mutant sweep over **every** correction, not just the first.

    The PR's own mutant removes one correction at a fixed index; sweeping all of them catches a
    correction that happens to be redundant for the tested branch.
    """
    from symq.phase import PhaseProgram, check_phase_equivalence

    raw, reference = _build_field_mac(3, 0b1011)
    repaired, _receipt = _synthesize(raw, 3)
    indices = [i for i, op in enumerate(repaired.ops) if op.kind == "mcz_if"]
    assert len(indices) >= 3
    undetected = []
    for index in indices:
        mutant = PhaseProgram(repaired.data, repaired.ancillas, list(repaired.ops))
        mutant.ops.pop(index)
        if check_phase_equivalence(mutant, reference).equivalent:
            undetected.append(index)
    assert not undetected, f"corrections {undetected} could be removed without detection"


def test_mutating_a_field_mac_correction_is_detected():
    """Wrong controls and a shifted outcome index must both be rejected."""
    from symq.phase import PhaseProgram, check_phase_equivalence

    raw, reference = _build_field_mac(3, 0b1011)
    repaired, _receipt = _synthesize(raw, 3)
    first = next(i for i, op in enumerate(repaired.ops) if op.kind == "mcz_if")
    original = repaired.ops[first]

    wrong_controls = PhaseProgram(repaired.data, repaired.ancillas, list(repaired.ops))
    shifted = list(original.qubits)
    shifted[0] = (shifted[0] + 1) % repaired.data
    wrong_controls.ops[first] = type(original)(
        original.kind, tuple(shifted), outcome=original.outcome
    )
    assert not check_phase_equivalence(wrong_controls, reference).equivalent

    wrong_outcome = PhaseProgram(repaired.data, repaired.ancillas, list(repaired.ops))
    wrong_outcome.ops[first] = type(original)(
        original.kind, original.qubits, outcome=(original.outcome + 1) % 3
    )
    assert not check_phase_equivalence(wrong_outcome, reference).equivalent


# ------------------------------------------------------------------ #95 and the 36-bit contract


@pytest.mark.skipif(not _native_built(), reason="native extension not built")
def test_native_backend_rejects_a_36_bit_coherent_contract():
    """Mission point 3: 3 x 12-bit registers need 72 pair variables, above the native limit.

    The important property is that the precondition is **rejected**, not silently approximated. A
    caller must never receive a verdict for a contract the engine cannot represent.
    """
    from symq.phase import Op, PhaseProgram
    from symq.resources import Budget, ResourceLimitExceeded

    checkout = _worktree("pr95")
    native_channel = _import_from(checkout, "research.hmr_native_channel.native_channel")
    program = PhaseProgram(36, 1, [Op("mcx", (0, 36), outcome=None), Op("hmr", (36,), outcome=0)])
    reference = PhaseProgram(36, 1, [Op("mcx", (0, 36), outcome=None)])
    with pytest.raises(ResourceLimitExceeded) as raised:
        native_channel.check_full_channel(
            program, reference, backend="zdd-native", budget=Budget(max_seconds=20)
        )
    message = str(raised.value)
    assert "pair variables" in message or "width" in message, message


def test_the_pure_python_backend_still_decides_the_36_bit_contract():
    """The limit is a native-representation limit, not a semantic one: `zdd` still answers.

    This matters for the integration plan: a 36-bit contract is *decidable*, just not natively, so
    the honest statement is "needs the Python backend or a composition theorem", not "unsupported".
    """
    from symq.phase import Op, PhaseProgram
    from symq.resources import Budget

    checkout = _worktree("pr95")
    native_channel = _import_from(checkout, "research.hmr_native_channel.native_channel")
    program = PhaseProgram(36, 1, [Op("mcx", (0, 36), outcome=None), Op("hmr", (36,), outcome=0)])
    reference = PhaseProgram(36, 1, [Op("mcx", (0, 36), outcome=None)])
    verdict = native_channel.check_full_channel(
        program, reference, backend="zdd", budget=Budget(max_seconds=60)
    )
    assert verdict.equivalent is False, "the uncorrected program must not be certified"
