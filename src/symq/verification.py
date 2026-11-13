"""Explicit, fail-closed verification contracts. No automatic engine selection.

The theorem being established is a required input, not inferred from a Circuit's
shape or an unrelated solver result. SAT, ANF, optional QCEC and strict sign-phase
prove DIFFERENT obligations: a partial-output claim is never a full-state proof;
a strict branch check is never a full-channel theorem. Experimental research
engines do not become stable dependencies by importing this module.

Standalone SymQ module: zero imports from any other repository.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .backends import BACKENDS
from .circuit import Circuit
from .equivalence import check_equivalence
from .errors import InternalInconsistency
from .hashing import canonical_sha256
from .phase import PhaseProgram, check_phase_equivalence
from .resources import Budget, Guard, ResourceLimitExceeded
from .sat import Contract, SatUnavailable, check_sat_equivalence

THEOREMS = frozenset({
    "classical_full", "classical_contract",
    "sign_phase_exact", "sign_phase_up_to_global",
    "full_channel",
})


@dataclass(frozen=True)
class VerificationRecord:
    """The result of :func:`verify_explicit`: one named theorem, one engine, one outcome.

    ``outcome`` is ``equivalent``, ``different``, ``inconclusive``, ``unsupported`` or
    ``precondition_failed``; only the first two are proofs. ``reason`` says in words how the
    outcome was reached. ``witness`` is an input assignment replayed on both programs
    (``witness_kind == "input"``) when a difference has one. The three SHA-256 fields identify
    detached snapshots of the two programs and contract that were compared. If the budget expires
    before the inputs are captured and hashed, the digests are empty strings (also the contract's,
    when one was given; ``None`` means no contract) and the outcome is inconclusive. ``global_phase_exponent`` is set by the sign-phase theorems
    (0 for exact equality, 4 for a global minus sign).
    """

    theorem: str
    engine: str
    outcome: str  # equivalent | different | inconclusive | unsupported | precondition_failed
    reason: str
    left_sha256: str
    right_sha256: str
    contract_sha256: str | None = None
    witness: int | None = None
    witness_kind: str | None = None
    global_phase_exponent: int | None = None

    @property
    def equivalent(self) -> bool:
        """``True`` only for a proved equivalence; ``False`` is not a proof of difference."""
        return self.outcome == "equivalent"

    @property
    def different(self) -> bool:
        """``True`` only for a proved difference (with a replayed witness when one exists)."""
        return self.outcome == "different"

    @property
    def certified(self) -> bool:
        """Only an actual 'equivalent' verdict establishes the requested theorem."""
        return self.outcome == "equivalent"


def _hash(data: dict) -> str:
    return canonical_sha256(data)


def _program_hash(value: Circuit | PhaseProgram) -> str:
    value.validate()
    if isinstance(value, Circuit):
        return _hash({
            "kind": "classical_reversible", "width": value.width,
            "gates": [[g.name, list(g.qubits)] for g in value.gates],
        })
    if isinstance(value, PhaseProgram):
        return _hash({
            "kind": "sign_phase_hmr", "data": value.data, "ancillas": value.ancillas,
            "ops": [[op.kind, list(op.qubits), op.outcome] for op in value.ops],
        })
    raise TypeError("Circuit or PhaseProgram required")


def _contract_hash(contract: Contract, width: int) -> str:
    contract.validate(width)
    body: dict[str, object] = {
        "input_constants": sorted(contract.input_constants.items()),
        "observed_outputs": contract.observed_outputs,
        "restored_wires": contract.restored_wires,
        "output_map": sorted(contract.output_map.items()),
    }
    if contract.assumption is not None:  # absent key keeps earlier digests unchanged
        body["assumption"] = repr(contract.assumption)
    return _hash(body)


def verify_explicit(
    left: Circuit | PhaseProgram, right: Circuit | PhaseProgram, *,
    theorem: str, engine: str, contract: Contract | None = None,
    budget: Budget | None = None, order: str | None = None,
) -> VerificationRecord:
    """Verify a specifically requested semantic theorem with an explicit engine.

    Unknown theorems, mismatched IRs and unsupported engine/contract combinations
    raise rather than guess. A missing optional dependency is 'unsupported', and
    an exhausted resource is 'inconclusive'. Internal inconsistencies propagate.
    ``order`` (``"auto"`` or a policy name) sets the variable order of a ZDD engine for
    ``classical_full``; it changes the cost, never the verdict.
    Programs and contracts are detached before hashing; the engine and witness replay use
    exactly those snapshots, so later caller mutations cannot change the recorded theorem.
    """
    if type(theorem) is not str or theorem not in THEOREMS:
        raise ValueError(f"unknown theorem {theorem!r}")
    if type(engine) is not str or not engine:
        raise ValueError("an explicit engine name is required")
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be a Budget")
    # The whole-call deadline starts here, so validation and hashing count against it; it also
    # honours a deadline inherited from an enclosing VerificationSession.
    guard = Guard(budget)
    deadline = guard.deadline
    is_classical = theorem.startswith("classical_")
    if is_classical:
        if not isinstance(left, Circuit) or not isinstance(right, Circuit):
            raise TypeError(f"{theorem} requires two Circuit objects")
        if left.width != right.width:
            raise ValueError("classical circuits have different widths")
        allowed = (set(BACKENDS) | {"sat", "qcec", "zdd-native"}
                   if theorem == "classical_full" else {"sat"})
    else:
        if not isinstance(left, PhaseProgram) or not isinstance(right, PhaseProgram):
            raise TypeError(f"{theorem} requires two PhaseProgram objects")
        if left.data != right.data:
            raise ValueError("phase programs have different data widths")
        allowed = {"phase-reference"} if theorem != "full_channel" else {"channel-sat"}
    if engine not in allowed:
        raise ValueError(f"engine {engine!r} cannot establish {theorem!r}")
    if order is not None and (theorem != "classical_full" or engine in {"sat", "qcec"}):
        raise ValueError("order= applies only to classical_full with a ZDD engine")
    if theorem == "classical_contract" and not isinstance(contract, Contract):
        raise ValueError("classical_contract requires an explicit Contract")
    if theorem != "classical_contract" and contract is not None:
        raise ValueError(f"{theorem} does not accept a classical output Contract")

    # Until the inputs are hashed, the digests are empty strings (also for a supplied contract):
    # a record that stops before hashing is inconclusive and identifies nothing.
    lhash = rhash = ""
    chash = None if contract is None else ""

    def deadline_exceeded() -> bool:
        return deadline is not None and time.perf_counter() >= deadline

    def result(outcome: str, reason: str, *, witness: int | None = None,
               global_phase_exponent: int | None = None) -> VerificationRecord:
        # All decisive claims must fit the *whole* public-call deadline, including
        # validation, hash construction, compilation, solver setup and witness replay.
        # A backend returning a late YES/NO cannot silently certify a timed-out call.
        if outcome in {"equivalent", "different"} and deadline_exceeded():
            outcome = "inconclusive"
            reason = "whole-call wall-clock budget exhausted"
            witness = None
            global_phase_exponent = None
        return VerificationRecord(
            theorem, engine, outcome, reason, lhash, rhash, chash,
            witness, "input" if witness is not None else None, global_phase_exponent,
        )

    try:
        guard.check_time()
        left = (Circuit.snapshot(left, check=guard.check_time) if isinstance(left, Circuit)
                else PhaseProgram.snapshot(left, check=guard.check_time))
        right = (Circuit.snapshot(right, check=guard.check_time) if isinstance(right, Circuit)
                 else PhaseProgram.snapshot(right, check=guard.check_time))
        if contract is not None:
            contract = Contract.snapshot(contract, check=guard.check_time)
        guard.check_time()
        lhash = _program_hash(left)
        guard.check_time()
        rhash = _program_hash(right)
        guard.check_time()
        chash = _contract_hash(contract, left.width) if contract is not None else None
        # Preserve the original deadline through engine setup and witness replay.
        budget = guard.inherited_budget()
    except ResourceLimitExceeded as error:
        return result("inconclusive", f"whole-call wall-clock budget exhausted: {error}")

    if is_classical and engine == "zdd-native" and engine not in BACKENDS:
        return result("unsupported", "optional native ZDD extension is not installed")

    if theorem == "full_channel":
        # Channel theorems have their own contract (domains, retained outputs, backends);
        # this facade does not reinterpret them as branch results.
        return result(
            "unsupported",
            "full-channel equality is decided by symq.experimental.verify with a "
            "VerificationContract, not by this classical/strict-branch facade",
        )

    if theorem.startswith("sign_phase_"):
        if budget is not None and (budget.max_nodes is not None or budget.max_bytes is not None):
            raise ValueError("phase-reference builds no diagram; refusing to ignore "
                             "max_nodes/max_bytes")
        if not isinstance(left, PhaseProgram) or not isinstance(right, PhaseProgram):
            raise TypeError(f"{theorem} requires two PhaseProgram objects")
        try:
            checked = check_phase_equivalence(left, right, budget=budget)
        except ResourceLimitExceeded as error:
            return result("inconclusive", str(error))
        if checked.violations:
            return result("precondition_failed", "; ".join(checked.violations))
        if checked.equivalent:
            return result("equivalent", "exact sign-phase equality",
                          global_phase_exponent=0)
        if checked.up_to_global_phase:
            status = ("equivalent" if theorem == "sign_phase_up_to_global" else "different")
            return result(status, "difference is a global minus sign",
                          global_phase_exponent=4)
        return result("different", "data outputs or relative sign phases differ",
                      witness=checked.witness)

    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError(f"theorem {theorem!r} requires two Circuit objects")
    if engine in {"sat", "qcec"} and budget is not None and (
        budget.max_nodes is not None or budget.max_terms is not None
        or budget.max_bytes is not None
    ):
        raise ValueError(f"{engine} cannot enforce symbolic term/node budgets")
    if engine == "sat":
        try:
            sat_verdict = check_sat_equivalence(left, right, contract, budget=budget)
        except SatUnavailable as exc:
            return result("unsupported", str(exc))
        if sat_verdict.outcome == "different":
            if sat_verdict.witness is None or sat_verdict.witness_checked is not True:
                raise InternalInconsistency("SAT did not provide a sat_verdict concrete witness")
            return result("different", sat_verdict.detail or "SAT witness sat_verdict",
                          witness=sat_verdict.witness)
        if sat_verdict.outcome == "equivalent":
            return result("equivalent", "UNSAT miter (no external LRAT certificate)")
        return result("inconclusive", sat_verdict.detail or "SAT decision unavailable")
    if engine == "qcec":
        # MQT is an *optional* library. The pure permutation fragment is fully
        # unitary, but QCEC does not supply concrete non-equivalence witnesses.
        from . import external

        if external.qcec_check is None:
            return result("unsupported", "optional mqt.qcec is not installed")
        if deadline_exceeded():
            return result("inconclusive", "whole-call wall-clock budget exhausted")
        timeout = (max(deadline - time.perf_counter(), 1e-9) if deadline is not None else 0.0)
        qcec_result = external.qcec_check(left, right, timeout=timeout)
        if qcec_result.equivalent is True:
            return result("equivalent", f"QCEC conclusive {qcec_result.verdict}")
        if qcec_result.equivalent is False:
            return result("different", f"QCEC conclusive {qcec_result.verdict}; no witness")
        return result("inconclusive", f"QCEC returned {qcec_result.verdict}")

    if deadline_exceeded():
        return result("inconclusive", "whole-call wall-clock budget exhausted")
    try:
        symbolic = check_equivalence(left, right, backend=engine, budget=budget, order=order)
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))
    if symbolic.equivalent:
        return result("equivalent", "all output ANFs equal")
    if symbolic.witness is None:
        raise InternalInconsistency("symbolic non-equivalence without a concrete witness")
    return result("different", f"output wire {symbolic.output} differs",
                  witness=symbolic.witness)
