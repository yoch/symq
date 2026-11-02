"""HMR-uncomputed finite-table XOR loaders (issue #144 research, ``symq.labs``).

Every checker verdict is compared with the independent dense cq-state oracle in
``tests/testkit/table_channel_oracle.py``: the full channel on every legal ``|x><y|``,
plus a state whose borrowed wire is entangled with an external reference qubit.
"""
from __future__ import annotations

import random
from collections import Counter
from fractions import Fraction
from itertools import product

import pytest

from symq.experimental.hybrid import HOp, HybridProgram, coherence_image
from symq.labs.hmr_table_contract import (
    HmrTableContract,
    and_uncompute_example,
    check_hmr_table_xor,
)
from symq.phase import PhaseProgram, phase_semantics
from symq.resources import Budget
from tests.testkit import table_channel_oracle as oracle
from tests.testkit.hmr_table_cases import (
    ADDRESS,
    ALL_STATES,
    BORROWED,
    LEGAL,
    MUTATIONS,
    REFERENCE,
    STATES,
    TABLE,
    TARGET,
    channel_matches,
    contract,
    loader,
    random_program,
    reference_state,
)

# ----------------------------------------------------------------------------- positive


def test_public_example_is_proved_and_matches_the_oracle():
    program, spec = and_uncompute_example()
    result = check_hmr_table_xor(program, spec)
    assert result.equivalent, result
    assert (result.checked_inputs, result.branches, result.hmr_events) == (24, 2, 1)
    assert spec.legal_inputs() == STATES
    assert channel_matches(program)
    assert loader().ops == program.ops


def test_example_matches_the_library_density_oracle_on_every_legal_coherence():
    program, spec = and_uncompute_example()
    for x, y in product(STATES, repeat=2):
        image = coherence_image(program, x, y)
        assert image == {(spec.ideal(x), spec.ideal(y)): Fraction(1)}


def test_reference_entanglement_is_kept_not_only_basis_behaviour():
    program, _ = and_uncompute_example()
    rho = reference_state(STATES)
    out = oracle.forgotten(program, rho)
    assert out == oracle.ideal(rho, ADDRESS, TARGET, TABLE)
    # The reduced state of the reference is untouched AND the joint state stays pure:
    # an off-diagonal between borrowed values 0 and 1 survives.
    assert any(((r >> 4) ^ (c >> 4)) & 1 and ((r >> REFERENCE) ^ (c >> REFERENCE)) & 1
               for r, c in out)


def test_outcome_dependent_global_sign_is_accepted_but_strict_o2_refuses_it():
    program = loader(extra=(HOp("neg", (), condition="b0"),))
    result = check_hmr_table_xor(program, contract())
    assert result.equivalent and channel_matches(program)
    # The strict sign/HMR theory demands one Kraus operator for all outcomes (O2), so an
    # outcome-only sign is refused there although the forgotten channel is unchanged.
    strict = PhaseProgram(2, 1).x(2)
    strict.hmr(2)
    assert any(v.startswith("O2") for v in phase_semantics(strict).violations())
    same = HybridProgram(2, 1).x(2).hmr(2, "b0")
    spec = HmrTableContract(width=3, address_wires=(0,), target_wires=(1,), clean_wires=(2,),
                            borrowed_wires=(), table=(0, 0), legal_addresses=(0, 1))
    assert check_hmr_table_xor(same, spec).equivalent
    for x, y in product(spec.legal_inputs(), repeat=2):
        assert oracle.forgotten(same, oracle.unit(x, y)) == oracle.unit(x, y)


def test_correction_valid_only_on_the_legal_support():
    program = loader(correction="linear")
    assert check_hmr_table_xor(program, contract()).equivalent
    assert channel_matches(program)
    # Including the illegal address 3, no table row makes the channel an XOR isometry.
    for row in range(4):
        table = (0, 1, 3, row)
        assert oracle.first_difference(program, ALL_STATES, ADDRESS, TARGET, table)
    # The exact CZ correction extends to address 3 with row 0b11.
    assert oracle.first_difference(loader(), ALL_STATES, ADDRESS, TARGET, TABLE) is None


# ----------------------------------------------------------------------------- mutations


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_mutation_is_refused_and_the_oracle_confirms_the_witness(name):
    options, obligation = MUTATIONS[name]
    program = loader(**options)
    clean = (5, 6) if options.get("extra_event") else (5,)
    spec = contract(clean=clean, width=program.width)
    result = check_hmr_table_xor(program, spec)
    assert result.status == "not_proved" and result.obligation == obligation, result
    x, y = result.witness["pair"]
    image = oracle.forgotten(program, oracle.unit(x, y))
    assert image != oracle.ideal(oracle.unit(x, y), ADDRESS, TARGET, TABLE)
    if obligation != "permutation":
        # All outputs are right, so the image is coefficient * W|x><y|W^T exactly.
        coefficient = Fraction(result.witness["coefficient"])
        assert coefficient != 1
        assert image == ({(spec.ideal(x), spec.ideal(y)): coefficient} if coefficient else {})
    assert not channel_matches(program)


def test_wrong_table_cell_is_refused():
    program, _ = and_uncompute_example()
    result = check_hmr_table_xor(program, contract(table=(0, 1, 0b10, None)))
    assert result.obligation == "permutation"
    x, y = result.witness["pair"]
    assert result.witness["input"]["address"] == 2
    assert oracle.forgotten(program, oracle.unit(x, y)) != oracle.ideal(
        oracle.unit(x, y), ADDRESS, TARGET, (0, 1, 0b10, 0))


def test_visible_record_is_refused_and_the_instrument_differs():
    program, spec = and_uncompute_example()
    result = check_hmr_table_xor(program, spec, observed_slots=("b0",))
    # A visible record asks for an instrument contract: unsupported, not a channel witness.
    assert result.status == "unsupported" and result.obligation == "visible_record"
    rho = reference_state(STATES)
    instrument = oracle.evolve(program, rho, observed=("b0",))
    # The record is independent of the input (each half of the ideal output), so the
    # criterion would prove a decoupled record; but the contract has no classical output.
    half = {k: v / 2 for k, v in oracle.ideal(rho, ADDRESS, TARGET, TABLE).items()}
    assert instrument == {(0,): half, (1,): half}
    leak = loader(uncompute="measure_z", correction="none")
    leaked = oracle.evolve(leak, rho, observed=("b0",))
    assert set(leaked) == {(0,), (1,)} and leaked[(0,)] != leaked[(1,)]  # reveals [a == 0]


def test_discarded_scratch_is_outside_the_contract_not_a_checker_bug():
    """Incompleteness relative to a garbage-tolerant contract (not the #144 one).

    Ancilla 6 ends in the input-independent state |1>. All quantum outputs are retained in
    the #144 contract, so the refusal is right; tracing that wire would give the ideal channel.
    """
    program = loader(extra_event=True, extra=(HOp("x", (6,)),))
    result = check_hmr_table_xor(program, contract(clean=(5, 6), width=7))
    assert result.obligation == "permutation"
    assert result.witness["output"]["clean"] != 0
    x, y = result.witness["pair"]
    assert oracle.forgotten(program, oracle.unit(x, y)) != oracle.ideal(
        oracle.unit(x, y), ADDRESS, TARGET, TABLE)
    rho = reference_state(STATES)
    traced = oracle.trace_wires(oracle.forgotten(program, rho), (6,))
    assert traced == oracle.ideal(rho, ADDRESS, TARGET, TABLE)


# ----------------------------------------------------------------- decision agreement


def test_checker_decides_exactly_what_the_dense_oracle_decides():
    """The criterion is necessary as well as sufficient for this contract.

    400 random programs x 12 contracts (4 tables, 3 legal sets): the checker proves
    exactly the cases where the oracle's channel equals the ideal one on every legal
    coherence, and each refusal's witness pair is a real difference.
    """
    rng = random.Random(144)
    data_states = range(1 << 3)
    seen: Counter[str | None] = Counter()
    for _ in range(400):
        program = random_program(rng)
        images = {(x, y): oracle.forgotten(program, oracle.unit(x, y))
                  for x, y in product(data_states, repeat=2)}
        for row0, row1 in product((0, 1), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = HmrTableContract(width=4, address_wires=(0,), target_wires=(1,),
                                        clean_wires=(3,), borrowed_wires=(2,),
                                        table=(row0, row1), legal_addresses=legal)
                states = spec.legal_inputs()
                same = all(images[x, y] == {(spec.ideal(x), spec.ideal(y)): Fraction(1)}
                           for x, y in product(states, repeat=2))
                result = check_hmr_table_xor(program, spec)
                assert result.status in {"equivalent", "not_proved"}
                assert result.equivalent == same, (program.ops, spec, result)
                if not same:
                    x, y = result.witness["pair"]
                    assert images[x, y] != {(spec.ideal(x), spec.ideal(y)): Fraction(1)}
                seen[result.obligation] += 1
    assert sum(seen.values()) == 400 * 12
    assert seen[None] >= 1000 and seen["permutation"] >= 1000, seen
    assert seen["branch_phase"] >= 100 and seen["branch_support"] >= 5, seen


# ------------------------------------------------------------------ boundaries and caps


def test_caps_give_inconclusive_never_a_proof():
    program, spec = and_uncompute_example()
    assert check_hmr_table_xor(program, spec, max_inputs=10).status == "inconclusive"
    assert check_hmr_table_xor(program, spec, max_branches=1).status == "inconclusive"
    assert check_hmr_table_xor(program, spec, max_steps=50).status == "inconclusive"
    tiny = check_hmr_table_xor(program, spec, budget=Budget(max_seconds=1e-9))
    assert tiny.status == "inconclusive"
    with pytest.raises(ValueError):
        check_hmr_table_xor(program, spec, budget=Budget(max_nodes=10))


def test_unsupported_inputs_are_refused():
    program, spec = and_uncompute_example()
    with pytest.raises(TypeError):
        check_hmr_table_xor(PhaseProgram(5, 1), spec)  # type: ignore[arg-type]
    forged = HybridProgram(5, 1)
    forged.ops.append(HOp("h", (0,)))
    assert check_hmr_table_xor(forged, spec).status == "unsupported"
    undeclared = HmrTableContract(width=6, address_wires=ADDRESS, target_wires=TARGET,
                                  clean_wires=(), borrowed_wires=(4, 5),
                                  table=(0, 1, 3, None), legal_addresses=LEGAL)
    assert check_hmr_table_xor(program, undeclared).status == "unsupported"
    wide = HybridProgram(5, 2)
    assert check_hmr_table_xor(wide, spec).status == "unsupported"


@pytest.mark.parametrize("change", [
    {"table": (0, 1, None, None)},  # a legal row left undefined
    {"table": (0, 1, 3)},  # missing row
    {"table": (0, 1, 4, None)},  # out-of-width row
    {"legal_addresses": (2, 1)},  # unordered
    {"legal_addresses": ()},
    {"clean_wires": (5, 4)},  # alias with borrowed
    {"target_values": (1, 1)},
])
def test_contract_validation(change):
    fields = {"width": 6, "address_wires": ADDRESS, "target_wires": TARGET,
              "clean_wires": (5,), "borrowed_wires": BORROWED, "table": (0, 1, 3, None),
              "legal_addresses": LEGAL}
    fields.update(change)
    with pytest.raises(ValueError):
        HmrTableContract(**fields)


def test_restricted_target_domain():
    program, _ = and_uncompute_example()
    spec = HmrTableContract(width=6, address_wires=ADDRESS, target_wires=TARGET,
                            clean_wires=(5,), borrowed_wires=BORROWED, table=(0, 1, 3, None),
                            legal_addresses=LEGAL, target_values=(0,))
    result = check_hmr_table_xor(program, spec)
    assert result.equivalent and result.checked_inputs == 6
    assert result.to_dict()["contract_sha256"] == spec.sha256 != contract().sha256


# --- Admissibility of inputs (review of #157 at c16d10e): each failed before the fix. ---


def _identity_contract():
    return HmrTableContract(2, (0,), (1,), (), (), (0, 0), (0, 1))


@pytest.mark.parametrize("field,value", [
    ("legal_addresses", ()),             # forged empty domain was certified with 0 inputs
    ("legal_addresses", (1, 0)),
    ("target_values", ()),
    ("table", (0,)),
    ("table", (0, True)),
    ("address_wires", (0, 0)),
    ("width", 3),
])
def test_mutated_frozen_contract_is_revalidated_not_certified(field, value):
    contract = _identity_contract()
    object.__setattr__(contract, field, value)
    with pytest.raises((ValueError, TypeError)):
        check_hmr_table_xor(HybridProgram(2), contract)


class _Deceptive(str):
    """Prints as 'h' but hashes and compares like 'x'."""

    def __hash__(self):
        return hash("x")

    def __eq__(self, other):
        return other == "x"


@pytest.mark.parametrize("field,value", [
    ("kind", _Deceptive("h")),           # executed as X while hashed as 'h' before the fix
    ("wires", [1]),
    ("wires", (True,)),
])
def test_forged_operation_fields_are_unsupported(field, value):
    op = HOp("x", (1,))
    object.__setattr__(op, field, value)
    program = HybridProgram(2)
    program.ops.append(op)
    contract = HmrTableContract(2, (0,), (1,), (), (), (1, 1), (0, 1))
    result = check_hmr_table_xor(program, contract)
    assert result.status == "unsupported" and not result.equivalent


def test_forged_slot_name_is_unsupported():
    spec = HmrTableContract(2, (0,), (1,), (), (), (0, 0), (0, 1))
    program = HybridProgram(2)
    program.ops.append(HOp("hmr", (1,), slot=_Deceptive("b0")))
    assert check_hmr_table_xor(program, spec).status == "unsupported"


def test_expired_deadline_never_certifies_even_an_empty_stream():
    result = check_hmr_table_xor(HybridProgram(2), _identity_contract(),
                                 budget=Budget(max_seconds=1e-12))
    assert result.status == "inconclusive" and not result.equivalent


def test_deadline_is_checked_before_every_decisive_verdict(monkeypatch):
    from symq.resources import Guard, ResourceLimitExceeded

    program, spec = and_uncompute_example()
    calls = {"n": 0}
    real = Guard.check_time
    total = {"n": 0}

    def counting(self):
        total["n"] += 1
        return real(self)

    monkeypatch.setattr(Guard, "check_time", counting)
    assert check_hmr_table_xor(program, spec).equivalent
    for stop in range(1, total["n"] + 1):
        calls["n"] = 0

        def expiring(self, stop=stop):
            calls["n"] += 1
            if calls["n"] >= stop:
                raise ResourceLimitExceeded("seconds", 0, 1)
            return real(self)

        monkeypatch.setattr(Guard, "check_time", expiring)
        result = check_hmr_table_xor(program, spec)
        assert result.status == "inconclusive", stop


@pytest.mark.parametrize("cap", [{"max_nodes": 1}, {"max_bytes": 1}])
def test_inherited_unsupported_budget_limits_fail_closed(cap):
    from symq.resources import VerificationSession

    with VerificationSession(Budget(**cap)), pytest.raises(ValueError, match="max_nodes"):
        check_hmr_table_xor(HybridProgram(2), _identity_contract())


def test_snapshot_is_used_for_hash_and_verdict():
    program, spec = and_uncompute_example()
    first = check_hmr_table_xor(program, spec)
    rebuilt = HybridProgram(program.data, program.ancillas, list(program.ops))
    assert check_hmr_table_xor(rebuilt, spec).source_sha256 == first.source_sha256
    assert first.checked_inputs == spec.input_count() > 0
