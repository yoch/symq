"""Table and clean-ancilla checks as importable jobs for ``run_isolated``.

``symq.experimental.execution.run_isolated`` runs an importable function in a spawned
process under hard operating-system limits (``HardLimits``: wall time, address space,
CPU time) and accepts only bounded JSON values back. The research checkers return
dataclasses with ``Fraction`` fields, or take a ``HybridProgram``; the jobs below take
JSON-like arguments and return JSON values, so that they can be passed to it as they are::

    from symq.experimental.execution import HardLimits, run_isolated
    from symq.labs.isolated_jobs import shift_diagonal_job

    outcome = run_isolated(shift_diagonal_job, program_to_dict(program), target,
                           kwargs={"budget": Budget(max_seconds=50)},
                           limits=HardLimits(wall_seconds=60, memory_bytes=2 * 1024**3))

(``memory_bytes`` is enforced on Linux; elsewhere pass ``None``, see the guide
``docs/guide/engines-and-budgets.md``.)

``outcome.status`` describes the execution (``completed``, ``inconclusive``, ``error``...)
and ``outcome.value`` is the job's result when it completed; the verification inside may
itself be ``inconclusive``. A worker killed by an operating-system limit gives no
verdict, never a semantic one.

The checkers are imported with this module, which the worker loads when it receives the
job, before the limits are set: a hard memory or CPU limit bounds the check, not the loading
of modules (loading after a tight limit fails in ways that depend on the machine).

A ``Budget`` passed to a job is a duration measured in the worker from the start of the
job, after the worker's own start: keep it below ``HardLimits.wall_seconds`` with a margin,
or the hard limit kills the worker before the check can report. An absolute deadline is a
``perf_counter`` value of the caller's process and means nothing in another one: it is
refused, and one that a check computes inside the worker is dropped from the ``limits`` of
its report. ``VerificationSession.subprocess_budget()`` turns a caller's remaining time into
a duration.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from fractions import Fraction
from typing import Any

from symq.experimental.serialization import program_from_dict
from symq.labs.affine_table import verify_affine_table
from symq.labs.backward_ancilla import check_clean_ancilla
from symq.labs.shared_table import verify_shared_table
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal
from symq.resources import Budget

__all__ = ["affine_table_job", "clean_ancilla_job", "shared_table_job", "shift_diagonal_job"]


def _relative(budget: Budget | None) -> Budget | None:
    if budget is not None and type(budget) is not Budget:
        raise TypeError("Budget or None required")
    if budget is not None and budget.absolute_deadline is not None:
        raise ValueError("an absolute deadline cannot cross into a worker process; pass "
                         "VerificationSession.subprocess_budget() or a max_seconds duration")
    return budget


def _json(value: Any) -> Any:
    """A JSON value for a result: dataclasses become objects, fractions ``"p/q"`` strings."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()
                if not (key == "absolute_deadline" and item is not None)}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def shared_table_job(source: dict, contract: dict, *, backend: str = "anf",
                     budget: Budget | None = None, **bounds: Any) -> dict:
    """``shared_table.verify_shared_table`` with a relative budget, as a JSON object."""
    return _json(verify_shared_table(source, contract, backend=backend,
                                     budget=_relative(budget), **bounds))


def affine_table_job(source: dict, contract: dict, *, backend: str = "anf",
                     budget: Budget | None = None, **bounds: Any) -> dict:
    """``affine_table.verify_affine_table`` with a relative budget, as a JSON object."""
    return _json(verify_affine_table(source, contract, backend=backend,
                                     budget=_relative(budget), **bounds))


def clean_ancilla_job(program: dict, target: int, *, budget: Budget | None = None,
                      limits: Any = None) -> dict:
    """``backward_ancilla.check_clean_ancilla`` on a serialized program, as a JSON object.

    ``program`` is ``program_to_dict(HybridProgram)``; a witness probability is a
    ``"p/q"`` string and a certificate an object, as ``AncillaCertificate.to_dict``.
    """
    return _json(check_clean_ancilla(program_from_dict(program), target,
                                     budget=_relative(budget), limits=limits))


def shift_diagonal_job(program: dict, target: int, *, budget: Budget | None = None,
                       limits: Any = None) -> dict:
    """``shift_diagonal_ancilla.check_shift_diagonal`` on a serialized program, as JSON."""
    return _json(check_shift_diagonal(program_from_dict(program), target,
                                      budget=_relative(budget), limits=limits))
