"""Research-only portable RUP witness for a source-bound classical SAT miter.

A positive result means that an independently supplied pair of reversible
circuits and a *restricted* classical SAT contract yield a rebuilt UNSAT miter,
and the pinned CNF has a checked positive-hint RUP/LRAT refutation.

This is NOT machine verification of the Python source-to-CNF encoder, a
contextual cut theorem, a general quantum-channel theorem or an authorization
to apply a rewrite. The producer is untrusted and entirely optional.
"""
from __future__ import annotations

import hashlib
import re
import time

from symq.circuit import Circuit
from symq.errors import ResourceLimitExceeded
from symq.labs import lrat_rup
from symq.labs.miter_cnf import export_classical_miter_cnf
from symq.resources import Budget, Guard, intersect_budgets
from symq.sat.encoding import Contract

_KIND = "symq_classical_miter_positive_rup"
_THEOREM = "classical_sat_miter_nonidentity_v1"
_KEYS = frozenset({
    "kind", "schema_version", "theorem", "source_sha256", "cnf_sha256",
    "lrat_sha256", "cnf", "lrat",
})
_PIN = re.compile(r"[0-9a-f]{64}\Z")


def _limits(limits: lrat_rup.Limits | None) -> lrat_rup.Limits:
    bound = lrat_rup.Limits() if limits is None else limits
    if type(bound) is not lrat_rup.Limits:
        raise TypeError("exact proof Limits required")
    bound.validate()
    return bound


def _clock(budget: Budget | None, limits: lrat_rup.Limits) -> Guard:
    if budget is not None and (
        type(budget) is not Budget or budget.max_nodes is not None
        or budget.max_terms is not None or budget.max_bytes is not None
    ):
        raise ValueError("only a time Budget is supported; use LRAT Limits for proof sizes")
    return Guard(intersect_budgets(
        Budget(max_seconds=limits.max_seconds), budget or Budget(),
    ))


def _source(left: Circuit, right: Circuit, contract: Contract | None):
    # Freeze at the entry point, once. A caller cannot change the pinned
    # source or legal domain in between formula export and proof checking.
    if type(left) is not Circuit or type(right) is not Circuit:
        raise TypeError("exact Circuits are required")
    if contract is not None and type(contract) is not Contract:
        raise TypeError("exact SAT Contract required")
    a = Circuit(left.width, list(left.gates))
    b = Circuit(right.width, list(right.gates))
    c = Contract() if contract is None else Contract(
        input_constants=dict(contract.input_constants),
        observed_outputs=None if contract.observed_outputs is None
        else tuple(contract.observed_outputs),
        restored_wires=tuple(contract.restored_wires),
        output_map=dict(contract.output_map),
        assumption=contract.assumption,
    )
    return a, b, c


def check_classical_miter_proof(
    left: Circuit,
    right: Circuit,
    contract: Contract | None,
    bundle: dict,
    *,
    expected_source_sha256: str,
    budget: Budget | None = None,
    limits: lrat_rup.Limits | None = None,
) -> dict:
    """Rebuild the exact normalized formula, then check a RUP witness.

    The independent source SHA must be supplied by the consumer, not read
    from the untrusted bundle. No proof producer, PySAT or external binary is
    required. A positive is *source-relative* to the trusted Python encoder.
    """
    bounds = _limits(limits)
    guard = _clock(budget, bounds)
    started = time.perf_counter()
    result = {
        "status": "invalid", "independent_unsat_checked": False,
        "source_recomputed": False, "source_encoder_formally_verified": False,
        "controlled_use_authorized": False,
        "theorem": _THEOREM,
    }
    try:
        guard.check_time()
        if type(expected_source_sha256) is not str or _PIN.fullmatch(expected_source_sha256) is None:
            raise lrat_rup.InvalidProof("an independent lowercase SHA-256 source pin is required")
        if type(bundle) is not dict or set(bundle) != _KEYS:
            raise lrat_rup.InvalidProof("closed schema of a classical-miter RUP bundle required")
        if (type(bundle["schema_version"]) is not int or bundle["schema_version"] != 1
                or type(bundle["kind"]) is not str or bundle["kind"] != _KIND
                or type(bundle["theorem"]) is not str or bundle["theorem"] != _THEOREM):
            raise lrat_rup.InvalidProof("unsupported proof type/version/theorem")
        for name in ("source_sha256", "cnf_sha256", "lrat_sha256"):
            if type(bundle[name]) is not str or _PIN.fullmatch(bundle[name]) is None:
                raise lrat_rup.InvalidProof(f"invalid {name}")
        for name in ("cnf", "lrat"):
            if type(bundle[name]) is not str or not bundle[name].isascii():
                raise lrat_rup.InvalidProof(f"non-ASCII or missing {name}")
        if len(bundle["cnf"]) + len(bundle["lrat"]) > bounds.max_bytes:
            raise lrat_rup.ProofLimit("combined formula/proof byte limit")

        if guard.budget.max_nodes is not None or guard.budget.max_terms is not None:
            raise lrat_rup.ProofLimit(
                "inherited node/term budget is not enforceable by the CNF exporter")
        a, b, c = _source(left, right, contract)
        formula = export_classical_miter_cnf(
            a, b, c, budget=Budget(absolute_deadline=guard.deadline),
            max_variables=bounds.max_variables, max_clauses=bounds.max_clauses,
            max_bytes=bounds.max_bytes,
        )
        if (formula.source_sha256 != expected_source_sha256
                or bundle["source_sha256"] != expected_source_sha256):
            raise lrat_rup.InvalidProof("fresh source/contract differs from independently pinned source")
        if formula.cnf_sha256 != bundle["cnf_sha256"] or formula.dimacs != bundle["cnf"]:
            raise lrat_rup.InvalidProof("source-recomputed normalized CNF differs from proof")
        if hashlib.sha256(bundle["lrat"].encode("ascii")).hexdigest() != bundle["lrat_sha256"]:
            raise lrat_rup.InvalidProof("LRAT bytes do not match the claimed hash")
        result["source_recomputed"] = True
        checked = lrat_rup.check_lrat(
            formula.dimacs, bundle["lrat"], expected_cnf_sha256=formula.cnf_sha256,
            limits=bounds, absolute_deadline=guard.deadline,
        )
        if checked["status"] == "inconclusive":
            raise lrat_rup.ProofLimit(checked.get("reason", "proof checker did not finish"))
        if checked["status"] != "verified_unsat" or not checked["verified_unsat"]:
            raise lrat_rup.InvalidProof(checked.get("reason", "RUP witness rejected"))
        guard.check_time()
        result.update(
            status="proved", independent_unsat_checked=True,
            source_sha256=formula.source_sha256, cnf_sha256=formula.cnf_sha256,
            lrat_sha256=bundle["lrat_sha256"], checked_steps=checked["steps"],
        )
        guard.check_time()
    except (lrat_rup.ProofLimit, ResourceLimitExceeded) as error:
        result.update(status="inconclusive", independent_unsat_checked=False,
                      reason=str(error))
    except lrat_rup.InvalidProof as error:
        result.update(status="invalid", independent_unsat_checked=False,
                      reason=str(error))
    result["seconds"] = time.perf_counter() - started
    return result


def export_classical_miter_proof(
    left: Circuit,
    right: Circuit,
    contract: Contract | None = None,
    *,
    budget: Budget | None = None,
    limits: lrat_rup.Limits | None = None,
) -> dict:
    """Optional untrusted SAT producer; success needs independent rechecking.

    'not_proved' from a satisfiable miter never grants an actionable
    counterexample or candidate. This function does not mutate sources.
    """
    from symq.labs.lrat_export import prove_cnf

    bounds = _limits(limits)
    guard = _clock(budget, bounds)
    started = time.perf_counter()
    result = {
        "status": "inconclusive", "independent_unsat_checked": False,
        "bundle": None, "controlled_use_authorized": False,
    }
    try:
        if guard.budget.max_nodes is not None or guard.budget.max_terms is not None:
            raise lrat_rup.ProofLimit(
                "inherited node/term budget is not enforceable by the CNF exporter")
        a, b, c = _source(left, right, contract)
        formula = export_classical_miter_cnf(
            a, b, c, budget=Budget(absolute_deadline=guard.deadline),
            max_variables=bounds.max_variables, max_clauses=bounds.max_clauses,
            max_bytes=bounds.max_bytes,
        )
        generated = prove_cnf(
            formula.dimacs, budget=Budget(absolute_deadline=guard.deadline),
            limits=bounds,
        )
        if generated["status"] == "proof_checked":
            proof = generated.get("lrat")
            if type(proof) is not str or not proof.isascii():
                raise lrat_rup.InvalidProof("producer did not return ASCII LRAT")
            bundle = {
                "kind": _KIND, "schema_version": 1, "theorem": _THEOREM,
                "source_sha256": formula.source_sha256,
                "cnf_sha256": formula.cnf_sha256, "cnf": formula.dimacs,
                "lrat": proof,
                "lrat_sha256": hashlib.sha256(proof.encode("ascii")).hexdigest(),
            }
            fresh = check_classical_miter_proof(
                a, b, c, bundle, expected_source_sha256=formula.source_sha256,
                budget=Budget(absolute_deadline=guard.deadline), limits=bounds,
            )
            if fresh["status"] == "proved" and fresh["independent_unsat_checked"]:
                result.update(status="proved", independent_unsat_checked=True,
                              bundle=bundle, source_sha256=formula.source_sha256,
                              cnf_sha256=formula.cnf_sha256)
            else:
                result.update(status=fresh["status"],
                              reason=fresh.get("reason", "fresh proof refused"))
        else:
            result.update(status="not_proved" if generated["status"] == "satisfiable"
                          else generated["status"],
                          reason=generated.get("reason", generated["status"]))
        guard.check_time()
    except (lrat_rup.ProofLimit, ResourceLimitExceeded) as error:
        result.update(status="inconclusive", independent_unsat_checked=False,
                      bundle=None, reason=str(error))
    except lrat_rup.InvalidProof as error:
        result.update(status="invalid", independent_unsat_checked=False,
                      bundle=None, reason=str(error))
    result["seconds"] = time.perf_counter() - started
    return result
