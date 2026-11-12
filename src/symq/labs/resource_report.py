"""What an ``inconclusive`` result of a research engine reports about the limit it hit.

Every engine that stops on a resource limit returns, next to its free-text ``reason``:

* ``resource``: the limit that was reached (``products``, ``terms``, ``seconds``, ...);
* ``limit`` and ``observed``: its value and the count when the engine stopped, when known
  (for a deadline, the seconds the call was allowed and the seconds it had run);
* ``hint``: which parameter controls it, or that the limit is fixed;
* ``limits``: the limits the call ran with, where the engine knows them. Table verifiers
  return a dict; the frozen ancilla results a tuple of ``(name, value)`` pairs, which
  ``dict()`` turns back into a dict.

A larger limit is not a promise of a verdict: the engine stopped at ``observed``, and a
complete proof may need much more. Exhaustion never yields a verdict, a witness or a
certificate.
"""
from __future__ import annotations

DEADLINE = "the deadline (max_seconds, absolute_deadline or an enclosing VerificationSession)"
"""A deadline is set by any of these; the tightest applies."""

TIME = {"seconds", "deadline", "SAT deadline", "SAT undecided or interrupted"}
"""Resources that are the deadline running out."""

PARAMETERS = {
    "products": "max_products",
    "terms": "max_terms",
    "Boolean DAG nodes": "max_graph_nodes",
    "CNF clauses": "max_clauses",
    "operations": "max_operations",
    "JSON items": "max_json_items",
    **dict.fromkeys(TIME, DEADLINE),
}
"""The parameter that controls each resource of the table verifiers, by the name they report."""

ANCILLA_PARAMETERS = {
    "terms": "Budget.max_terms",
    "gate_terms": "Budget.max_terms",
    "pauli_products": "AncillaLimits.max_products",
    "polynomial_products": "AncillaLimits.max_products",
    "width": "AncillaLimits.max_width",
    "operations": "AncillaLimits.max_operations",
    "gate_qubits": "AncillaLimits.max_gate_qubits",
    "classical_slots": "AncillaLimits.max_classical_slots",
    **dict.fromkeys(TIME, DEADLINE),
}
"""The same for the clean-ancilla checkers, whose limits come in ``Budget`` and ``AncillaLimits``."""

FIXED = {"shared table JSON bytes"}
"""Resources whose limit is part of the verifier, not a parameter."""


def resource_report(error, limits: dict | None = None, parameters: dict | None = None) -> dict:
    """The structured fields for an engine stopped by ``error``.

    ``error`` is a ``ResourceLimitExceeded`` or any exception with ``resource``, ``limit``
    and ``observed`` attributes; a bare exception reports its text as the resource.
    ``parameters`` maps resources to parameter names (default: the table verifiers').
    """
    resource = getattr(error, "resource", None) or str(error)
    limit = getattr(error, "limit", None)
    observed = getattr(error, "observed", None)
    own = getattr(error, "hint", None)
    parameter = (PARAMETERS if parameters is None else parameters).get(resource)
    if parameter is None:
        advice = "a fixed limit of this verifier" if resource in FIXED else None
    elif resource in TIME:
        advice = f"controlled by {parameter}; a later deadline may conclude, or may not"
    elif own is None and limit is not None and observed is not None:
        advice = (f"stopped at {observed} with {parameter}={limit}; a larger {parameter} "
                  "may conclude, or may not")
    else:
        advice = f"controlled by {parameter}"
    hint = "; ".join(part for part in (own, advice) if part) or None
    report = {"resource": resource, "limit": limit, "observed": observed, "hint": hint}
    if limits is not None:
        report["limits"] = dict(limits)
    return report
