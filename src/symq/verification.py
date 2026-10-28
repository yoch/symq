"""Explicit, fail-closed verification contracts. No automatic engine selection.

The theorem being established is a required input, not inferred from a Circuit's
shape or an unrelated solver result. SAT, ANF, optional QCEC and strict sign-phase
prove DIFFERENT obligations: a partial-output claim is never a full-state proof;
a strict branch check is never a full-channel theorem. Experimental research
engines do not become stable dependencies by importing this module.

Standalone SymQ module: zero imports from any other repository.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .backends import BACKENDS
from .circuit import Circuit
from .equivalence import check_equivalence
from .phase import PhaseProgram, check_phase_equivalence
from .resources import Budget, ResourceLimitExceeded
from .sat import Contract, SatUnavailable, check_sat_equivalence

THEOREMS = frozenset({
    "classical_full", "classical_contract",
    "sign_phase_exact", "sign_phase_up_to_global",
    "full_channel",
})


@dataclass(frozen=True)
class VerificationRecord:
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
    def certified(self) -> bool:
        """Only an actual 'equivalent' verdict establishes the requested theorem."""
        return self.outcome == "equivalent"


def _hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
    return _hash({
        "input_constants": sorted(contract.input_constants.items()),
        "observed_outputs": contract.observed_outputs,
        "restored_wires": contract.restored_wires,
        "output_map": sorted(contract.output_map.items()),
    })


def verify_explicit(
    left: Circuit | PhaseProgram, right: Circuit | PhaseProgram, *,
    theorem: str, engine: str, contract: Contract | None = None,
    budget: Budget | None = None,
) -> VerificationRecord:
    """Verify a specifically requested semantic theorem with an explicit engine.

    Unknown theorems, mismatched IRs and unsupported engine/contract combinations
    raise rather than guess. A missing optional dependency is 'unsupported', and
    an exhausted resource is 'inconclusive'. Internal inconsistencies propagate.
    """
    if type(theorem) is not str or theorem not in THEOREMS:
        raise ValueError(f"unknown theorem {theorem!r}")
    if type(engine) is not str or not engine:
        raise ValueError("an explicit engine name is required")
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be a Budget")
    is_classical = theorem.startswith("classical_")
    if is_classical:
        if not isinstance(left, Circuit) or not isinstance(right, Circuit):
            raise TypeError(f"{theorem} requires two Circuit objects")
        if left.width != right.width:
            raise ValueError("classical circuits have different widths")
        allowed = set(BACKENDS) | {"sat", "qcec"} if theorem == "classical_full" else {"sat"}
    else:
        if not isinstance(left, PhaseProgram) or not isinstance(right, PhaseProgram):
            raise TypeError(f"{theorem} requires two PhaseProgram objects")
        if left.data != right.data:
            raise ValueError("phase programs have different data widths")
        allowed = {"phase-reference"} if theorem != "full_channel" else {"channel-sat"}
    if engine not in allowed:
        raise ValueError(f"engine {engine!r} cannot establish {theorem!r}")
    if theorem == "classical_contract" and not isinstance(contract, Contract):
        raise ValueError("classical_contract requires an explicit Contract")
    if theorem != "classical_contract" and contract is not None:
        raise ValueError(f"{theorem} does not accept a classical output Contract")

    lhash, rhash = _program_hash(left), _program_hash(right)
    chash = _contract_hash(contract, left.width) if contract is not None else None

    def result(outcome: str, reason: str, *, witness: int | None = None,
               global_phase_exponent: int | None = None) -> VerificationRecord:
        return VerificationRecord(
            theorem, engine, outcome, reason, lhash, rhash, chash,
            witness, "input" if witness is not None else None, global_phase_exponent,
        )

    if theorem == "full_channel":
        # The factored-channel SAT/ZDD work lives in research PRs; do not
        # imply its experimental contract is part of the installed library.
        return result(
            "unsupported",
            "full-channel decision is a separate experimental research API, not shipped here",
        )

    if theorem.startswith("sign_phase_"):
        if budget is not None:
            raise ValueError("phase-reference has no resource budget; refusing to ignore one")
        checked = check_phase_equivalence(left, right)
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

    assert isinstance(left, Circuit) and isinstance(right, Circuit)
    if engine in {"sat", "qcec"} and budget is not None and (
        budget.max_nodes is not None or budget.max_terms is not None
    ):
        raise ValueError(f"{engine} cannot enforce symbolic term/node budgets")
    if engine == "sat":
        try:
            checked = check_sat_equivalence(left, right, contract, budget=budget)
        except SatUnavailable as exc:
            return result("unsupported", str(exc))
        if checked.outcome == "different":
            if checked.witness is None or checked.witness_checked is not True:
                raise RuntimeError("SAT did not provide a checked concrete witness")
            return result("different", checked.detail or "SAT witness checked",
                          witness=checked.witness)
        if checked.outcome == "equivalent":
            return result("equivalent", "UNSAT miter (no external LRAT certificate)")
        return result("inconclusive", checked.detail or "SAT decision unavailable")
    if engine == "qcec":
        # MQT is an *optional* library. The pure permutation fragment is fully
        # unitary, but QCEC does not supply concrete non-equivalence witnesses.
        from . import external

        if external.qcec_check is None:
            return result("unsupported", "optional mqt.qcec is not installed")
        timeout = budget.max_seconds if budget and budget.max_seconds else 0.0
        checked = external.qcec_check(left, right, timeout=timeout)
        if checked.equivalent is True:
            return result("equivalent", f"QCEC conclusive {checked.verdict}")
        if checked.equivalent is False:
            return result("different", f"QCEC conclusive {checked.verdict}; no witness")
        return result("inconclusive", f"QCEC returned {checked.verdict}")

    try:
        checked = check_equivalence(left, right, backend=engine, budget=budget)
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))
    if checked.equivalent:
        return result("equivalent", "all output ANFs equal")
    if checked.witness is None:
        raise RuntimeError("symbolic non-equivalence without a concrete witness")
    return result("different", f"output wire {checked.output} differs",
                  witness=checked.witness)
