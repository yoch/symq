"""Structural features and an automatic strategy, with the features kept cheap and explainable.

Two decisions, deliberately separated because they have different evidence:

1. **Which order** for the native ZDD, among ``identity``, ``reversed`` and ``last_use``.
2. **Which engine** for an equivalence task, between the symbolic engine and SAT.

Both are made from features computable in one pass over the gate list -- no simulation, no trial
runs. The cost is timed and reported, because a selector that costs more than it saves is not a
selector.

Everything here is deterministic: no randomness, no training, no tie broken by measurement.

The rules come from the measured per-family behaviour in
``research/engineering/2026-10-28/RESULTS_ORDER_CORRECTED.json`` and
``research/symq-v2/RESULTS/sat_pilot.json``, and are stated as rules so they can be checked and
overturned rather than fitted:

* ``last_use`` wins enormously on arithmetic circuits (adders: 58x) and loses on single-cascade
  circuits (MCX chains: 1.58x slower). The discriminator is not the *name* of the circuit but the
  shape of its last-use profile: an adder has many wires whose last use is late and spread out,
  while an MCX chain has one wire used at every step.
* SAT wins when the circuit is wide and dense, because the symbolic engine's cost is driven by the
  monomial families while the SAT encoding is linear in the gate count. It ties on tiny circuits,
  where both are instantaneous.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.circuit import Circuit


@dataclass(frozen=True)
class Features:
    """One pass over the gate list; every field is O(gates) or O(wires log wires)."""

    width: int
    gates: int
    controls_total: int
    max_arity: int
    mean_arity: float
    used_wires: int
    last_use_spread: float
    """Standard deviation of the last-use positions, normalised by the gate count.

    Near 0 means "all wires finish about the same time", which is the shape of a single cascade;
    large means a staged structure like a ripple-carry adder."""
    first_use_spread: float
    distinct_controls: int
    """How many distinct wires ever act as a control; a low share suggests a cascade."""
    depth_estimate: int
    """Length of the longest chain where each gate shares a wire with the previous one."""

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def features(circuit: Circuit) -> Features:
    """Compute the structural features in one pass. ``circuit`` is validated, never modified."""
    circuit.validate()
    width = circuit.width
    first = [None] * width
    last = [0] * width
    uses = [0] * width
    controls_total = 0
    max_arity = 0
    controls_seen: set[int] = set()
    depth = 1 if circuit.gates else 0
    previous_wires: set[int] = set()
    for position, gate in enumerate(circuit.gates):
        qubits = gate.qubits
        controls_total += len(qubits) - 1
        max_arity = max(max_arity, len(qubits) - 1)
        for qubit in qubits:
            if first[qubit] is None:
                first[qubit] = position
            last[qubit] = position
            uses[qubit] += 1
        controls_seen.update(qubits[:-1])
        touched = set(qubits)
        depth = depth + 1 if touched & previous_wires else depth
        previous_wires = touched
    used = [wire for wire in range(width) if uses[wire]]
    gate_count = max(len(circuit.gates), 1)
    return Features(
        width=width,
        gates=len(circuit.gates),
        controls_total=controls_total,
        max_arity=max_arity,
        mean_arity=controls_total / gate_count,
        used_wires=len(used),
        last_use_spread=_spread([last[wire] / gate_count for wire in used]),
        first_use_spread=_spread([first[wire] / gate_count for wire in used
                                  if first[wire] is not None]),
        distinct_controls=len(controls_seen),
        depth_estimate=depth,
    )


def _spread(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5


ORDER_RULES = """order policy:
  if last_use_spread >= 0.12 and distinct_controls >= 3 and gates >= 24 -> last_use
  elif last_use_spread >= 0.12 and gates >= 24                     -> reversed
  else                                                              -> identity"""

ENGINE_RULES = """engine policy:
  if the SAT solver is unavailable                                   -> symbolic
  elif gates >= 20 or controls_total >= 40                           -> sat
  else                                                               -> symbolic

Measured justification (holdout, 12 tasks): SAT is strictly fastest on 8 of 12. On the four where
it loses, the *whole* symbolic verification takes under a millisecond, so the encoder's fixed cost
dominates; on every circuit where the symbolic run exceeds a millisecond SAT wins, by up to 65x.

Two earlier rules were tried and rejected against the same data:

* ``mean_arity <= 2.5`` excluded the adders (arity 1.33) and the MCX chains (arity 10) -- exactly
  the families where SAT wins by 3x to 75x;
* ``gates >= 20`` alone missed a 19-gate MCX chain of 20 wires, whose controls_total is 190 and
  whose symbolic run costs 135 ms against 2 ms for SAT. Counting the *controls* rather than the
  gates is what catches a short list of very wide gates."""


@dataclass(frozen=True)
class Choice:
    order: str
    engine: str
    reason: str
    features: Features


def choose_order(feature: Features) -> tuple[str, str]:
    """The order policy, as the rule above. Returns ``(policy, reason)``."""
    if feature.last_use_spread >= 0.12 and feature.distinct_controls >= 3 and feature.gates >= 24:
        return "last_use", "staged structure: wires finish at spread-out times"
    if feature.last_use_spread >= 0.12 and feature.gates >= 24:
        return "reversed", "mild staging, too few controls for last_use"
    return "identity", "homogeneous last-use profile: no staging to exploit"


def choose_engine(feature: Features, *, sat_available: bool | None = None) -> tuple[str, str]:
    """The engine policy; SAT only when the solver is actually importable.

    ``sat_available`` defaults to ``None``, meaning "ask the engine". It used to default to
    ``True``, which made a stock installation select a method it could not run -- the audit
    caught it, and a recommendation that cannot be executed is not a recommendation.
    """
    if sat_available is None:
        try:
            from .sat import available as sat_available_now

            sat_available = sat_available_now()
        except Exception:  # noqa: BLE001 - a broken optional dependency means "unavailable"
            sat_available = False
    if not sat_available:
        return "symbolic", "no SAT solver installed"
    if feature.gates >= 20 or feature.controls_total >= 40:
        return "sat", "above the crossover: the miter is linear in the gate list"
    return "symbolic", "tiny circuit: both engines are below a millisecond"


def choose(circuit: Circuit, *, sat_available: bool | None = None) -> Choice:
    feature = features(circuit)
    order, order_reason = choose_order(feature)
    engine, engine_reason = choose_engine(feature, sat_available=sat_available)
    return Choice(order, engine, f"{order_reason}; {engine_reason}", feature)
