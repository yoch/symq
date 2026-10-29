"""Transcript-bound, exact local channel substitution with quantum frame soundness.

This verifier never simulates the whole global state. Each leaf is checked on a
complete matrix-unit basis, so equality extends to an arbitrary entangled frame.
The exponential leaf oracle is deliberately small and explicitly bounded.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from symq.circuit import UnsupportedOperation
from symq.experimental.classical_transcript import TranscriptMismatch, UnprovedSubstitution
from symq.experimental.hybrid import (
    HOp,
    HybridProgram,
    Matrix,
    coherence_image,
    coherence_instrument,
)
from symq.resources import Budget, Guard, ResourceLimitExceeded, session_scoped

_SLOT = re.compile(r"b(0|[1-9][0-9]*)\Z")
_VERSION = "symq-local-channel-transcript-v1"


def _names(ops: tuple[HOp, ...]) -> set[str]:
    return {s for op in ops for s in (op.slot, op.source,
            op.condition.removeprefix("!") if op.condition else None) if s is not None}


def _writes(ops: tuple[HOp, ...]) -> set[str]:
    return {op.slot for op in ops if op.kind in {"store", "invert", "oxor", "hmr", "measure_z"}}


def _tuple_wires(value: tuple[int, ...], width: int, name: str) -> None:
    if (type(value) is not tuple or len(set(value)) != len(value)
            or any(type(q) is not int or q < 0 or q >= width for q in value)):
        raise ValueError(f"{name} must be unique in-range wires")


@dataclass(frozen=True)
class FrozenHybridProgram:
    data: int
    ancillas: int
    ops: tuple[HOp, ...]

    def __post_init__(self) -> None:
        if type(self.ops) is not tuple:
            raise TypeError("immutable operation tuple required")
        self.to_program().validate()

    @property
    def width(self) -> int:
        return self.data + self.ancillas

    @classmethod
    def freeze(cls, program: HybridProgram) -> FrozenHybridProgram:
        if type(program) is not HybridProgram:
            raise TypeError("HybridProgram required")
        program.validate()
        return cls(program.data, program.ancillas, tuple(program.ops))

    def to_program(self) -> HybridProgram:
        return HybridProgram(self.data, self.ancillas, list(self.ops))


def hybrid_digest(program: FrozenHybridProgram | HybridProgram) -> str:
    if type(program) is HybridProgram:
        program = FrozenHybridProgram.freeze(program)
    if type(program) is not FrozenHybridProgram:
        raise TypeError("frozen hybrid program required")
    obj = [_VERSION, program.data, program.ancillas,
           [[o.kind, o.wires, o.slot, o.condition, o.source, o.value] for o in program.ops]]
    return hashlib.sha256(json.dumps(obj, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class HybridFragment:
    """All quantum inputs are arbitrary unless a slot proves clean preparation.

    Classical inputs denote arbitrary *classical* values at the cut. They are
    universally enumerated; they are never invented zero assumptions.
    """
    width: int
    ops: tuple[HOp, ...]
    classical_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.width) is not int or self.width < 1 or type(self.ops) is not tuple:
            raise ValueError("positive width and immutable operations required")
        if (type(self.classical_inputs) is not tuple
                or len(set(self.classical_inputs)) != len(self.classical_inputs)
                or any(type(s) is not str or not _SLOT.fullmatch(s)
                       for s in self.classical_inputs)):
            raise ValueError("unique classical input slots required")
        prefix = [HOp("store", slot=s, value=0) for s in self.classical_inputs]
        HybridProgram(self.width, 0, prefix + list(self.ops)).validate()

    @classmethod
    def freeze(cls, program: HybridProgram) -> HybridFragment:
        if type(program) is not HybridProgram:
            raise TypeError("HybridProgram required")
        program.validate()
        if program.ancillas:
            raise ValueError("fragment ancillas require an explicit slot clean obligation")
        return cls(program.width, tuple(program.ops))


@dataclass(frozen=True)
class HybridCommon:
    ops: tuple[HOp, ...]

    def __post_init__(self) -> None:
        if type(self.ops) is not tuple or any(type(o) is not HOp for o in self.ops):
            raise TypeError("immutable common HOp tuple required")


@dataclass(frozen=True)
class ChannelSlot:
    reference: HybridFragment
    candidate: HybridFragment
    wires: tuple[int, ...]
    classical_map: tuple[tuple[str, str], ...] = ()
    clean: tuple[int, ...] = ()
    preserved: tuple[int, ...] = ()
    discarded: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.reference) is not HybridFragment or type(self.candidate) is not HybridFragment:
            raise TypeError("frozen hybrid fragments required")
        width = self.reference.width
        if width != self.candidate.width:
            raise ValueError("fragment widths differ")
        if (type(self.wires) is not tuple or len(self.wires) != width
                or any(type(q) is not int or q < 0 for q in self.wires)
                or len(set(self.wires)) != width):
            raise ValueError("complete injective local-to-global wire mapping required")
        if self.reference.classical_inputs != self.candidate.classical_inputs:
            raise ValueError("matching arbitrary classical input interfaces required")
        for name in ("clean", "preserved", "discarded"):
            _tuple_wires(getattr(self, name), width, name)
        if len(self.clean) == width:
            raise UnsupportedOperation("at least one arbitrary quantum input required")
        if set(self.preserved) & (set(self.clean) | set(self.discarded)):
            raise ValueError("borrowed dirty wires cannot be clean or discarded")
        if (type(self.classical_map) is not tuple
                or any(type(pair) is not tuple or len(pair) != 2
                       or any(type(s) is not str or not _SLOT.fullmatch(s) for s in pair)
                       for pair in self.classical_map)):
            raise ValueError("classical mapping must contain slot-name pairs")
        keys, values = zip(*self.classical_map) if self.classical_map else ((), ())
        needed = _names(self.reference.ops) | _names(self.candidate.ops)
        needed |= set(self.reference.classical_inputs)
        if len(set(keys)) != len(keys) or len(set(values)) != len(values):
            raise ValueError("injective classical mapping required")
        if set(keys) != needed:
            raise ValueError("classical mapping must cover exactly every local slot")


@dataclass(frozen=True)
class ChannelTranscriptProof:
    reference_sha256: str
    candidate_sha256: str
    global_width: int
    slots: int
    unique_lemmas: int
    checked_pairs: int
    discarded_global: tuple[int, ...]
    observed_slots: tuple[str, ...]
    theorem: str = _VERSION

    @property
    def equivalent(self) -> bool:
        return True


def _map_ops(ops: tuple[HOp, ...], wires: tuple[int, ...], table: dict[str, str]) -> tuple[HOp, ...]:
    def condition(s: str | None) -> str | None:
        if s is None:
            return None
        return ("!" if s.startswith("!") else "") + table[s.removeprefix("!")]
    return tuple(HOp(o.kind, tuple(wires[q] for q in o.wires),
                     table[o.slot] if o.slot is not None else None, condition(o.condition),
                     table[o.source] if o.source is not None else None, o.value) for o in ops)


def _live_before(ops: tuple[HOp, ...], live: set[str]) -> set[str]:
    live = set(live)
    for op in reversed(ops):
        if op.kind in {"hmr", "measure_z", "store"}:
            live.discard(op.slot)
        if op.kind in {"invert", "oxor"}:
            live.add(op.slot)
        if op.source is not None:
            live.add(op.source)
        if op.condition is not None:
            live.add(op.condition.removeprefix("!"))
    return live


def _advance_known(known: list[int | None], ops: tuple[HOp, ...]) -> None:
    """A conservative proof of pure basis values, never a guess from liveness."""
    for op in ops:
        qs = op.wires
        if op.kind in {"hmr", "reset"}:
            known[qs[0]] = 0
        elif op.kind in {"x", "cx", "ccx", "mcx"}:
            *controls, target = qs
            if any(known[q] == 0 for q in controls):
                continue
            if op.condition is None and all(known[q] == 1 for q in controls):
                known[target] = None if known[target] is None else known[target] ^ 1
            else:
                known[target] = None
        elif op.kind in {"swap", "cswap"}:
            a, b = qs[-2:]
            control = 1 if op.kind == "swap" else known[qs[0]]
            if control == 0:
                continue
            if control == 1 and op.condition is None:
                known[a], known[b] = known[b], known[a]
            elif known[a] != known[b]:
                known[a] = known[b] = None


def _compress(value: int, keep: tuple[int, ...]) -> int:
    return sum(((value >> q) & 1) << i for i, q in enumerate(keep))


def _reduce(matrix: Matrix, width: int, discarded: tuple[int, ...]) -> Matrix:
    if not discarded:
        return matrix
    keep = tuple(q for q in range(width) if q not in discarded)
    mask = sum(1 << q for q in discarded)
    out: Matrix = {}
    for (row, col), coeff in matrix.items():
        if (row ^ col) & mask:
            continue
        pair = (_compress(row, keep), _compress(col, keep))
        out[pair] = out.get(pair, Fraction(0)) + coeff
        if not out[pair]:
            del out[pair]
    return out


def _leaf_program(fragment: HybridFragment, clean: tuple[int, ...], bits: tuple[int, ...]):
    order = tuple(q for q in range(fragment.width) if q not in clean) + clean
    inverse = tuple(order.index(q) for q in range(fragment.width))
    slots = {s: s for s in _names(fragment.ops) | set(fragment.classical_inputs)}
    prefix = [HOp("store", slot=s, value=v) for s, v in zip(fragment.classical_inputs, bits)]
    return (HybridProgram(fragment.width-len(clean), len(clean),
                          prefix + list(_map_ops(fragment.ops, inverse, slots))), order)


def _local_images(fragment, clean, bits, observed, discarded, guard, max_width,
                  max_events, max_branches):
    program, order = _leaf_program(fragment, clean, bits)
    def restore(value):
        return sum(((value >> i) & 1) << q for i, q in enumerate(order))
    outputs = {}
    for x in range(1 << program.data):
        for y in range(1 << program.data):
            guard.check_time()
            kwargs = {"_guard": guard, "max_width": max_width, "max_events": max_events,
                      "max_branches": max_branches}
            if observed:
                image = coherence_instrument(program, x, y, observed_slots=observed, **kwargs)
            else:
                image = {(): coherence_image(program, x, y, **kwargs)}
            guard.check_time()
            original = {}
            for record, matrix in image.items():
                restored = {(restore(r), restore(c)): v for (r, c), v in matrix.items()}
                reduced = _reduce(restored, fragment.width, discarded)
                if reduced:
                    original[record] = reduced
            outputs[(restore(x), restore(y))] = original
            guard.check_terms(sum(len(m) for image in outputs.values() for m in image.values()))
    return outputs


def _identity_frame(images, width, clean, preserved, discarded):
    """Check E = F tensor identity on borrowed wires, including off-diagonals."""
    if not preserved:
        return True
    mask = sum(1 << q for q in preserved)
    output_keep = tuple(q for q in range(width) if q not in discarded)
    dirty_output = tuple(output_keep.index(q) for q in preserved)
    main_output = tuple(q for q in range(len(output_keep)) if q not in dirty_output)
    for (x, y), image in images.items():
        base = images[(x & ~mask, y & ~mask)]
        expected = {}
        for record, matrix in base.items():
            target = {}
            for (r, c), coeff in matrix.items():
                if any((r >> q & 1) or (c >> q & 1) for q in dirty_output):
                    return False
                rr = _compress(r, main_output)
                cc = _compress(c, main_output)
                out_r = sum((rr >> i & 1) << q for i, q in enumerate(main_output))
                out_c = sum((cc >> i & 1) << q for i, q in enumerate(main_output))
                out_r |= sum((x >> orig & 1) << q for orig, q in zip(preserved, dirty_output))
                out_c |= sum((y >> orig & 1) << q for orig, q in zip(preserved, dirty_output))
                target[(out_r, out_c)] = coeff
            if target:
                expected[record] = target
        if image != expected:
            return False
    return True


@session_scoped
def verify_channel_transcript(
    reference: HybridProgram, candidate: HybridProgram,
    steps: Sequence[HybridCommon | ChannelSlot], *,
    reference_sha256: str, candidate_sha256: str,
    observed_slots: tuple[str, ...] = (), discarded_global: tuple[int, ...] = (),
    budget: Budget | None = None, max_expanded_ops: int = 200_000,
    max_local_width: int = 6, max_classical_inputs: int = 6,
    max_events: int = 8, max_branches: int = 256,
) -> ChannelTranscriptProof:
    """Verify full-stream coverage, cut preparation, local instruments and frame.

    Pins bind caller-selected streams; a matching digest is never a proof.
    Channels are compared on all coherences and arbitrary classical cut values.
    Only terminal declared outputs may be traced. Clean cut facts are derived
    conservatively from each complete prefix, rather than accepted as hypotheses.
    """
    guard = Guard(budget)
    guard.check_time()
    for name, val in (("max_expanded_ops", max_expanded_ops),
                      ("max_local_width", max_local_width),
                      ("max_classical_inputs", max_classical_inputs),
                      ("max_events", max_events), ("max_branches", max_branches)):
        if type(val) is not int or val < 1:
            raise ValueError(f"{name} must be positive")
    if type(steps) not in (tuple, list) or not steps:
        raise TranscriptMismatch("nonempty ordered transcript required")
    a, b = FrozenHybridProgram.freeze(reference), FrozenHybridProgram.freeze(candidate)
    if (a.data, a.ancillas) != (b.data, b.ancillas):
        raise TranscriptMismatch("matching global input interfaces required")
    if hybrid_digest(a) != reference_sha256 or hybrid_digest(b) != candidate_sha256:
        raise TranscriptMismatch("pinned global source hash mismatch")
    _tuple_wires(discarded_global, a.width, "discarded_global")
    if (type(observed_slots) is not tuple or len(set(observed_slots)) != len(observed_slots)
            or any(type(s) is not str or not _SLOT.fullmatch(s) for s in observed_slots)):
        raise ValueError("unique observed slot names required")
    for program in (a, b):
        initialized = {op.slot for op in program.ops if op.kind in {"store", "hmr", "measure_z"}}
        if not set(observed_slots) <= initialized:
            raise TranscriptMismatch("observed classical output not initialized")
    expanded = []
    aa, bb = [], []
    for index, step in enumerate(steps):
        guard.check_time()
        if type(step) is HybridCommon:
            left = right = step.ops
        elif type(step) is ChannelSlot:
            if any(q >= a.width for q in step.wires):
                raise TranscriptMismatch(f"step {index}: wire mapping outside global width")
            table = dict(step.classical_map)
            left = _map_ops(step.reference.ops, step.wires, table)
            right = _map_ops(step.candidate.ops, step.wires, table)
        else:
            raise UnsupportedOperation("only frozen HybridCommon or ChannelSlot accepted")
        if max(len(aa) + len(left), len(bb) + len(right)) > max_expanded_ops:
            raise ResourceLimitExceeded("transcript operations", max_expanded_ops,
                                        max(len(aa)+len(left), len(bb)+len(right)))
        aa.extend(left)
        bb.extend(right)
        expanded.append((left, right))
    if tuple(aa) != a.ops or tuple(bb) != b.ops:
        raise TranscriptMismatch("ordered transcript does not cover both complete streams")
    # Derive future reads independently from both covered streams.
    future = []
    live = set(observed_slots)
    touched: set[int] = set()
    for left, right in reversed(expanded):
        future.append((set(live), set(touched)))
        live = _live_before(left, live) | _live_before(right, live)
        touched |= {q for op in left + right for q in op.wires}
    future.reverse()
    known_a = [None] * a.data + [0] * a.ancillas
    known_b = list(known_a)
    initialized_a: set[str] = set()
    initialized_b: set[str] = set()
    checked = {}
    pairs = slots = 0
    for index, (step, (left, right), (live, touched)) in enumerate(zip(steps, expanded, future)):
        guard.check_time()
        if type(step) is ChannelSlot:
            slots += 1
            table = dict(step.classical_map)
            inputs = {table[s] for s in step.reference.classical_inputs}
            if not inputs <= initialized_a & initialized_b:
                raise TranscriptMismatch(f"step {index}: classical cut input not initialized")
            if any(known_a[step.wires[q]] != 0 or known_b[step.wires[q]] != 0 for q in step.clean):
                raise UnprovedSubstitution(index, "clean cut wire preparation not proved by prefix")
            if any(step.wires[q] not in discarded_global or step.wires[q] in touched
                   for q in step.discarded):
                raise UnprovedSubstitution(index, "local trace requires terminal globally discarded wires")
            written = _writes(step.reference.ops) | _writes(step.candidate.ops)
            observed = tuple(sorted(s for s in written if table[s] in live))
            key = (step.reference, step.candidate, step.clean, step.preserved,
                   step.discarded, observed)
            if key not in checked:
                n = len(step.reference.classical_inputs)
                if n > max_classical_inputs:
                    raise ResourceLimitExceeded("classical inputs", max_classical_inputs, n)
                zero_outputs = [set(range(step.reference.width)) - set(step.discarded)
                                for _ in range(2)]
                for bits in product((0, 1), repeat=n):
                    images = [_local_images(f, step.clean, bits, observed, step.discarded,
                                            guard, max_local_width, max_events, max_branches)
                              for f in (step.reference, step.candidate)]
                    guard.check_terms(sum(len(matrix) for side in images for image in side.values()
                                          for matrix in image.values()))
                    output_keep = tuple(q for q in range(step.reference.width) if q not in step.discarded)
                    for side_index, side in enumerate(images):
                        for image in side.values():
                            for matrix in image.values():
                                for row, col in matrix:
                                    zero_outputs[side_index] -= {
                                        q for bit, q in enumerate(output_keep) if (row | col) >> bit & 1
                                    }
                    pairs += len(images[0])
                    guard.check_time()
                    if images[0] != images[1]:
                        raise UnprovedSubstitution(index, "local coherent channel/instrument differs")
                    preserved = all(_identity_frame(im, step.reference.width, step.clean,
                                                    step.preserved, step.discarded) for im in images)
                    guard.check_time()
                    if not preserved:
                        raise UnprovedSubstitution(index, "borrowed dirty wire identity correlation fails")
                checked[key] = tuple(tuple(sorted(z)) for z in zero_outputs)
        _advance_known(known_a, left)
        _advance_known(known_b, right)
        guard.check_time()
        if type(step) is ChannelSlot:
            for known, zeros in zip((known_a, known_b), checked[key]):
                for q in zeros:
                    known[step.wires[q]] = 0
        initialized_a |= _writes(left)
        initialized_b |= _writes(right)
    guard.check_time()
    return ChannelTranscriptProof(reference_sha256, candidate_sha256, a.width, slots,
                                  len(checked), pairs, discarded_global, observed_slots)
