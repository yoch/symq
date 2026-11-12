"""One receipt format for table and clean-ancilla obligations, and its replay (research).

Each research checker returns its own result shape, and none of them records, in one
place, what was asked, of which inputs, under which settings, and what came out. A
downstream user had to assemble that by hand to keep track of hundreds of checks. This
module runs one check and returns a receipt that does:

* ``obligation``: which theorem was asked (``affine_table``, ``shared_table``,
  ``clean_ancilla``) and with which ``engine``;
* ``source_sha256`` and ``statement_sha256``: canonical SHA-256 of the source document and
  of the statement (the contract, or the target and the program's frame);
* ``statement``: a readable summary of the statement (widths, legal domain size, dirty and
  scratch wires, how measurements are treated);
* ``settings``: the budget and limits of the call, so that a replay runs the same check;
* ``verdict``: the status, the failed obligation and the witness, as the checker gave them;
* ``resources``: the counters the checker reports, and its resource report if it stopped;
* ``symq_version`` and ``receipt_sha256``, a digest of everything else.

**A receipt is not a certificate.** It proves nothing by itself, and its digest only
detects accidental edits: anyone can recompute it. ``replay_obligation`` is the only way
to rely on a receipt: it checks that the source and the statement it is given are those
the receipt names, runs the same check again, and compares the verdict.

    receipt = prove_obligation("shared_table", source, contract, engine="anf")
    replay = replay_obligation(receipt, source, contract)
    assert replay["status"] == "confirmed"

Integration with ``symq.labs.proof_graph`` (obligations as graph nodes, composition) is
not part of this first version.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from fractions import Fraction
from typing import Any

from symq.hashing import canonical_sha256
from symq.resources import Budget

__all__ = ["OBLIGATIONS", "prove_obligation", "replay_obligation"]

KIND = "symq_obligation_receipt"
SCHEMA_VERSION = 1
AUTHORITY = "none: a receipt proves nothing by itself; replay_obligation recomputes the check"

OBLIGATIONS = {
    "affine_table": ("anf", "sat"),
    "shared_table": ("anf", "sat"),
    "clean_ancilla": ("pauli", "shift_diagonal"),
}
"""The obligations a receipt can name, with the engines each one runs on."""

_BUDGET_FIELDS = ("max_terms", "max_nodes", "max_seconds", "max_bytes")
_DECISIVE = {"equivalent", "not_proved", "clean", "not_clean"}


def _json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _budget(budget: Budget | None) -> dict | None:
    if budget is None:
        return None
    if type(budget) is not Budget:
        raise TypeError("Budget or None required")
    if budget.absolute_deadline is not None:
        raise ValueError("a receipt records durations only: an absolute deadline cannot be "
                         "replayed; pass max_seconds")
    return {name: getattr(budget, name) for name in _BUDGET_FIELDS}


def _settings(obligation, engine, budget, limits, bounds) -> dict:
    if obligation not in OBLIGATIONS:
        raise ValueError(f"unknown obligation; expected one of {sorted(OBLIGATIONS)}")
    if engine not in OBLIGATIONS[obligation]:
        raise ValueError(f"{obligation} runs on {list(OBLIGATIONS[obligation])}, not {engine!r}")
    if obligation == "clean_ancilla":
        if bounds:
            raise ValueError("clean_ancilla takes budget and limits, no other bound")
        from symq.labs.backward_ancilla import AncillaLimits

        if limits is not None and type(limits) is not AncillaLimits:
            raise TypeError("AncillaLimits or None required")
        limit_values = None if limits is None else {
            f.name: getattr(limits, f.name) for f in fields(AncillaLimits)}
        return {"budget": _budget(budget), "limits": limit_values}
    if limits is not None:
        raise ValueError("limits apply to clean_ancilla only; table bounds are keywords")
    for name, value in bounds.items():
        if type(name) is not str or type(value) not in (int, float, str):
            raise TypeError("table bounds are keyword integers, floats or strings")
    return {"budget": _budget(budget), "bounds": dict(sorted(bounds.items()))}


def _run(obligation: str, engine: str, source: Any, statement: Any, settings: dict) -> dict:
    """Run the check once; return its result as JSON and the statement summary."""
    budget = None if settings["budget"] is None else Budget(**settings["budget"])
    if obligation == "clean_ancilla":
        from symq.experimental.serialization import program_from_dict
        from symq.labs.backward_ancilla import AncillaLimits

        if type(statement) is not dict or set(statement) != {"target"}:
            raise ValueError("a clean_ancilla statement is {'target': <ancilla wire>}")
        program = program_from_dict(source)
        limits = None if settings["limits"] is None else AncillaLimits(**settings["limits"])
        if engine == "pauli":
            from symq.labs.backward_ancilla import check_clean_ancilla as check
        else:
            from symq.labs.shift_diagonal_ancilla import check_shift_diagonal as check
        result = _json(check(program, statement["target"], budget=budget, limits=limits))
        summary = {"data": program.data, "ancillas": program.ancillas,
                   "target": statement["target"], "operations": len(program.ops),
                   "theorem": "the target ancilla ends in |0> for every data state, "
                              "entangled references included; not channel equality",
                   "measurements": "every branch, records kept by the program"}
        return {"result": result, "summary": summary}
    if obligation == "affine_table":
        from symq.labs.affine_table import verify_affine_table as check
    else:
        from symq.labs.shared_table import verify_shared_table as check
    result = _json(check(source, statement, backend=engine, budget=budget, **settings["bounds"]))
    summary = {key: statement.get(key) for key in ("width", "bit_order", "records", "outputs")}
    summary.update(
        address_bits=len(statement.get("address_wires", ())),
        target_bits=len(statement.get("target_wires", ())),
        clean_wires=len(statement.get("clean_wires", ())),
        dirty_wires=len(statement.get("borrowed_wires", ())),
        legal_addresses=(result.get("address_domain_size") if obligation == "shared_table"
                         else len(statement.get("legal_addresses", ()))),
        theorem="every legal address, target parameter and borrowed state is mapped as the "
                "table says, records forgotten, all outputs checked; conditional on the "
                "declared domain, which is not proved to be prepared")
    return {"result": result, "summary": summary}


def _verdict(result: dict) -> dict:
    witness = result.get("witness")
    if witness is None and isinstance(result.get("assignment"), int):
        witness = {"assignment": result["assignment"], "probability": result.get("probability")}
    return {"status": result["status"], "obligation": result.get("obligation"),
            "witness": witness, "reason": result.get("reason")}


_COUNTERS = ("products", "peak_terms", "graph_nodes", "cnf_clauses", "queries", "sat_calls",
             "pauli_products", "checked_operations", "peak_shifts", "promotions", "seconds",
             "resource", "limit", "observed", "hint", "limits")


def _body_digest(receipt: dict) -> str:
    return canonical_sha256({k: v for k, v in receipt.items() if k != "receipt_sha256"})


def prove_obligation(obligation: str, source: Any, statement: Any, *, engine: str,
                     budget: Budget | None = None, limits: Any = None, **bounds: Any) -> dict:
    """Run one check and return its receipt (a JSON object).

    ``obligation`` and ``engine``: see ``OBLIGATIONS``. ``source`` is the source document
    (a serialized program, ``program_to_dict``); ``statement`` the contract for a table, or
    ``{"target": wire}`` for a clean ancilla. ``budget`` must give durations
    (``max_seconds``), not an absolute deadline; ``limits`` is an ``AncillaLimits`` for a
    clean ancilla; other keywords are the table verifiers' bounds. Malformed input raises
    as the checker does.
    """
    settings = _settings(obligation, engine, budget, limits, bounds)
    ran = _run(obligation, engine, source, statement, settings)
    result = ran["result"]
    from symq import __version__

    receipt = {
        "kind": KIND, "schema_version": SCHEMA_VERSION, "authority": AUTHORITY,
        "portable_certificate": False, "obligation": obligation, "engine": engine,
        "source_sha256": canonical_sha256(source),
        "statement_sha256": canonical_sha256(statement),
        "statement": ran["summary"], "settings": settings, "verdict": _verdict(result),
        "resources": {key: result[key] for key in _COUNTERS if result.get(key) is not None},
        "symq_version": __version__,
    }
    receipt["receipt_sha256"] = _body_digest(receipt)
    return receipt


def _receipt_fields(receipt: Any) -> str | None:
    """Why a receipt is malformed, or None."""
    expected = {"kind", "schema_version", "authority", "portable_certificate", "obligation",
                "engine", "source_sha256", "statement_sha256", "statement", "settings",
                "verdict", "resources", "symq_version", "receipt_sha256"}
    if type(receipt) is not dict or set(receipt) != expected:
        return "not a version-1 obligation receipt"
    if receipt["kind"] != KIND or receipt["schema_version"] != SCHEMA_VERSION:
        return "not a version-1 obligation receipt"
    if receipt["receipt_sha256"] != _body_digest(receipt):
        return "the receipt was edited after it was made (its digest differs)"
    return None


def replay_obligation(receipt: Any, source: Any, statement: Any) -> dict:
    """Check that ``source`` and ``statement`` are those of ``receipt``, rerun, compare.

    Returns ``{"status": ..., "reason": ..., "verdict": ..., "receipt_verdict": ...}`` with
    status:

    * ``confirmed``: same inputs, and the replay reached the receipt's status (a decisive
      one, or ``inconclusive`` again);
    * ``concluded``: the receipt was inconclusive and the replay decided (``verdict``);
    * ``inconclusive``: the receipt was decisive and the replay ran out of resources;
    * ``mismatch``: the inputs are not those of the receipt, the receipt is malformed or
      edited, or the replay decided otherwise (``reason`` says which).

    Only ``confirmed`` with a decisive verdict supports the receipt's claim, and only for
    the inputs given here. A replay under another SymQ version says so (``same_version``).
    """
    problem = _receipt_fields(receipt)
    if problem is not None:
        return {"status": "mismatch", "reason": problem, "verdict": None,
                "receipt_verdict": None}
    claimed = receipt["verdict"]
    if canonical_sha256(source) != receipt["source_sha256"]:
        return {"status": "mismatch", "reason": "source differs from the receipt's",
                "verdict": None, "receipt_verdict": claimed}
    if canonical_sha256(statement) != receipt["statement_sha256"]:
        return {"status": "mismatch", "reason": "statement differs from the receipt's",
                "verdict": None, "receipt_verdict": claimed}
    settings = receipt["settings"]
    bounds = settings.get("bounds") or {}
    budget = None if settings["budget"] is None else Budget(**settings["budget"])
    limits = None
    if receipt["obligation"] == "clean_ancilla" and settings.get("limits") is not None:
        from symq.labs.backward_ancilla import AncillaLimits

        limits = AncillaLimits(**settings["limits"])
    fresh = prove_obligation(receipt["obligation"], source, statement,
                             engine=receipt["engine"], budget=budget, limits=limits, **bounds)
    verdict = fresh["verdict"]
    from symq import __version__

    same = {"same_version": receipt["symq_version"] == __version__,
            "verdict": verdict, "receipt_verdict": claimed}
    old, new = claimed["status"], verdict["status"]
    if old == new and (old not in _DECISIVE or claimed["obligation"] == verdict["obligation"]):
        return {"status": "confirmed", "reason": None, **same}
    if old == "inconclusive" and new in _DECISIVE:
        return {"status": "concluded", "reason": "the receipt was inconclusive", **same}
    if new == "inconclusive" and old in _DECISIVE:
        return {"status": "inconclusive", "reason": "the replay ran out of resources", **same}
    return {"status": "mismatch", "reason": f"the replay found {new} "
            f"({verdict['obligation']}), the receipt says {old} ({claimed['obligation']})",
            **same}
