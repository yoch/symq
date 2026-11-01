"""Exact whole-unitary GF(2^n) bilinear block substitution, no SAT.

Narrowly admits phase-free triangular CX/CCX blocks on an injectively
mapped (A,B,Z) interface:
* CX within A, B or Z; never between registers;
* CCX with one control in A, one in B, target in Z;
* NO X, MCX, phases, resets, measures, or gates touching an outside wire.

A and B must return to their initial values, Z's linear transfer must be
identity (so the accumulator may be DIRTY), and the full quadratic
multiplication tensor must equal the declared irreducible GF(2) modulus.
This establishes an exact permutation on ALL 3n input bits, not merely
agreement on sampled states or a promised clean-cut precondition. Because
CX/CCX have no relative phases, the local permutation equality is also
unitary equality, including coherent superpositions and arbitrary
entanglement with other wires. Common surrounding reversible gates compose
soundly. This is NOT a measurement, HMR or phase-program theorem.

The proof is re-derived from *gate streams*, never from optimizer terms,
model claims, a saved JSON receipt, or a SAT solver. Unsupported grammar or
resource limits fail closed. The method cannot certify arbitrary reversible
circuits, even when they are in fact equivalent.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.circuit import Circuit, Gate
from symq.generators.bilinear_optimization import _irreducible
from symq.hashing import canonical_sha256
from symq.labs.classical_transcript import Program, digest
from symq.resources import Budget, Guard


class BilinearProofFailure(ValueError):
    """Structural requirement, interface invariant or exact tensor failed."""


@dataclass(frozen=True)
class BilinearWeights:
    """User-declared integer CCX/CX cost proxy, NOT physical quantum cost."""

    ccx: int
    cx: int

    def __post_init__(self) -> None:
        if (type(self.ccx) is not int or self.ccx < 0
                or type(self.cx) is not int or self.cx < 0
                or self.ccx + self.cx == 0):
            raise ValueError("explicit nonnegative CCX/CX weights, not both zero, are required")


@dataclass(frozen=True)
class BilinearProof:
    """Immutable pins for a proved full-output, full-unitary local replacement."""

    source_sha256: str
    replacement_sha256: str
    candidate_sha256: str
    reference_block_sha256: str
    replacement_block_sha256: str
    tensor_sha256: str
    span: tuple[int, int]
    wires: tuple[int, ...]
    n: int
    modulus: int
    reference_cx: int
    reference_ccx: int
    replacement_cx: int
    replacement_ccx: int
    weights: BilinearWeights
    weighted_delta: int
    theorem: str = "exact_total_bilinear_permutation_unitary_v1"

    @property
    def equivalent(self) -> bool:
        # Only returned after BOTH streams independently meet every invariant.
        return True


@dataclass(frozen=True)
class AppliedBilinearSubstitution:
    candidate: Program
    proof: BilinearProof

    def __post_init__(self) -> None:
        if type(self.candidate) is not Program or type(self.proof) is not BilinearProof:
            raise TypeError("a frozen Program and exact BilinearProof are required")
        if digest(self.candidate) != self.proof.candidate_sha256:
            raise ValueError("immutable candidate differs from proof pin")


def _limit(budget: Budget | None) -> Guard:
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be Budget or None")
    requested = budget if budget is not None else Budget(max_seconds=30)
    if any(getattr(requested, field) is not None
           for field in ("max_terms", "max_nodes", "max_bytes")):
        raise ValueError("this verifier only enforces time and explicit gate/width limits")
    return Guard(requested)


def _interface(
    width: int, n: int, modulus: int, wires: tuple[int, ...],
    span: tuple[int, int], length: int, max_global_width: int
) -> dict[int, int]:
    if type(max_global_width) is not int or max_global_width < 1:
        raise ValueError("max_global_width must be a positive integer")
    if width > max_global_width:
        raise ValueError("global circuit width exceeds declared verifier limit")
    if type(n) is not int or not 2 <= n <= 24:
        raise ValueError("bilinear field width must be an integer in 2..24")
    if (type(modulus) is not int or modulus.bit_length() != n + 1
            or not _irreducible(modulus)):
        raise ValueError("a monic irreducible degree-n GF(2) modulus is required")
    if (type(wires) is not tuple or len(wires) != 3 * n
            or any(type(w) is not int or not 0 <= w < width for w in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError("wires must be an injective in-range global map of 3*n integers")
    if (type(span) is not tuple or len(span) != 2
            or any(type(i) is not int for i in span)
            or not 0 <= span[0] < span[1] <= length):
        raise ValueError("span must be a nonempty valid [start,stop) gate interval")
    return {w: i for i, w in enumerate(wires)}


def _product(n: int, modulus: int, i: int, j: int) -> int:
    """Independent polynomial long division (not the factor generator)."""
    poly = 1 << (i + j)
    while poly.bit_length() > n:
        poly ^= modulus << (poly.bit_length() - n - 1)
    return poly


def _tensor(n: int, modulus: int) -> tuple[int, ...]:
    outputs = [0] * n
    for i in range(n):
        for j in range(n):
            kbits = _product(n, modulus, i, j)
            while kbits:
                low = kbits & -kbits
                k = low.bit_length() - 1
                outputs[k] |= 1 << (i * n + j)
                kbits ^= low
    return tuple(outputs)


def _extract(
    block: tuple[Gate, ...], mapping: dict[int, int],
    n: int, guard: Guard, max_block_gates: int, label: str,
) -> tuple[tuple[int, ...], tuple[int, int]]:
    """Extract each output's exact ANF degree-two A_i * B_j coefficient vector.

    All A/B CNOT frames are explicit GF(2) linear combinations of the
    original A/B bits. Z wires hold a GF(2)-linear combination of the
    original Z plus quadratic products. The triangular grammar prevents
    any higher degree or other monomial types, so this extraction is exact.
    """
    if len(block) > max_block_gates:
        raise ValueError(f"{label}: more than {max_block_gates} gates")
    left = [1 << i for i in range(n)]
    right = [1 << i for i in range(n)]
    accum = [1 << i for i in range(n)]
    quadratic = [0] * n
    cx = ccx = 0
    for number, gate in enumerate(block):
        if number % 64 == 0:
            guard.check_time()
        if gate.name not in ("cx", "ccx"):
            raise BilinearProofFailure(f"{label} gate {number}: unsupported {gate.name}")
        try:
            indices = tuple(mapping[q] for q in gate.qubits)
        except KeyError as exc:
            raise BilinearProofFailure(
                f"{label} gate {number}: operation crosses the mapped block boundary"
            ) from exc
        if gate.name == "cx":
            c, t = indices
            if c < n and t < n:
                left[t] ^= left[c]
            elif n <= c < 2 * n and n <= t < 2 * n:
                right[t - n] ^= right[c - n]
            elif 2 * n <= c < 3 * n and 2 * n <= t < 3 * n:
                accum[t - 2 * n] ^= accum[c - 2 * n]
                quadratic[t - 2 * n] ^= quadratic[c - 2 * n]
            else:
                raise BilinearProofFailure(
                    f"{label} gate {number}: cross-register CX is unsupported"
                )
            cx += 1
        else:
            first, second, target = indices
            if first < n <= second < 2 * n:
                a, b = left[first], right[second - n]
            elif second < n <= first < 2 * n:
                a, b = left[second], right[first - n]
            else:
                raise BilinearProofFailure(
                    f"{label} gate {number}: CCX needs one A and one B control"
                )
            if not 2 * n <= target < 3 * n:
                raise BilinearProofFailure(f"{label} gate {number}: CCX must target Z")
            while a:
                bit_a = a & -a
                i = bit_a.bit_length() - 1
                row_b = b
                while row_b:
                    bit_b = row_b & -row_b
                    j = bit_b.bit_length() - 1
                    quadratic[target - 2 * n] ^= 1 << (i * n + j)
                    row_b ^= bit_b
                a ^= bit_a
            ccx += 1
    for name, forms in (("A", left), ("B", right), ("dirty Z", accum)):
        if any(form != 1 << i for i, form in enumerate(forms)):
            raise BilinearProofFailure(f"{label}: {name} register linear frame not restored")
    guard.check_time()
    return tuple(quadratic), (cx, ccx)


def _frozen_check(
    source: Program, span: tuple[int, int], replacement: Program, *,
    n: int, modulus: int, wires: tuple[int, ...],
    weights: BilinearWeights, guard: Guard,
    max_block_gates: int, max_global_width: int,
) -> BilinearProof:
    if source.width != replacement.width:
        raise ValueError("replacement uses a different global width")
    if type(max_block_gates) is not int or max_block_gates < 1:
        raise ValueError("max_block_gates must be a positive integer")
    mapping = _interface(
        source.width, n, modulus, wires, span, len(source.gates), max_global_width
    )
    if type(weights) is not BilinearWeights:
        raise TypeError("explicit BilinearWeights required")
    before = source.gates[span[0]:span[1]]
    after = replacement.gates
    expected = _tensor(n, modulus)
    old, old_count = _extract(before, mapping, n, guard, max_block_gates, "original")
    if old != expected:
        raise BilinearProofFailure("original block multiplication tensor mismatch")
    new, new_count = _extract(after, mapping, n, guard, max_block_gates, "replacement")
    if new != expected:
        raise BilinearProofFailure("replacement multiplication tensor mismatch")
    candidate = Program(
        source.width,
        source.gates[:span[0]] + after + source.gates[span[1]:],
    )
    cost_before = old_count[0] * weights.cx + old_count[1] * weights.ccx
    cost_after = new_count[0] * weights.cx + new_count[1] * weights.ccx
    guard.check_time()
    return BilinearProof(
        digest(source), digest(replacement), digest(candidate),
        canonical_sha256({"gates": [[g.name, list(g.qubits)] for g in before]}),
        canonical_sha256({"gates": [[g.name, list(g.qubits)] for g in after]}),
        canonical_sha256({"schema": "tensor-GF2-AxB-v1", "n": n,
                          "modulus": modulus, "outputs": list(expected)}),
        span, wires, n, modulus, old_count[0], old_count[1],
        new_count[0], new_count[1], weights, cost_after - cost_before,
    )


def check_bilinear_substitution(
    source: Circuit, span: tuple[int, int], replacement: Circuit, *,
    n: int, modulus: int, wires: tuple[int, ...],
    weights: BilinearWeights, budget: Budget | None = None,
    max_block_gates: int = 10_000, max_global_width: int = 4096,
) -> BilinearProof:
    """Prove both gate streams implement exactly the same total GF multiplication.

    A successful proof is strictly stronger than a cut-conditional classical
    SAT proof for this narrow grammar, but it does not support an arbitrary
    classical or coherent hybrid circuit. No inconclusive result is success.
    """
    guard = _limit(budget)
    original = Program.freeze(source)
    proposed = Program.freeze(replacement)
    guard.check_time()
    return _frozen_check(
        original, span, proposed, n=n, modulus=modulus, wires=wires,
        weights=weights, guard=guard, max_block_gates=max_block_gates,
        max_global_width=max_global_width,
    )


def apply_bilinear_substitution(
    proof: BilinearProof, source: Circuit, span: tuple[int, int],
    replacement: Circuit, *, budget: Budget | None = None,
    max_block_gates: int = 10_000, max_global_width: int = 4096,
    require_saving: bool = True,
) -> AppliedBilinearSubstitution:
    """Freeze, reprove the pinned theorem, then apply to those SAME snapshots.

    A forged positive record, stale circuit, changed mapping, altered weights
    or expired budget cannot authorize a rewrite. No recorded success flag
    is ever trusted. The reproof and immutable construction share one clock.
    """
    guard = _limit(budget)
    if type(proof) is not BilinearProof:
        raise TypeError("typed BilinearProof required")
    if proof.theorem != "exact_total_bilinear_permutation_unitary_v1":
        raise ValueError("unsupported proof theorem")
    if type(require_saving) is not bool:
        raise TypeError("require_saving must be boolean")
    original = Program.freeze(source)
    proposed = Program.freeze(replacement)
    guard.check_time()
    fresh = _frozen_check(
        original, span, proposed, n=proof.n, modulus=proof.modulus,
        wires=proof.wires, weights=proof.weights, guard=guard,
        max_block_gates=max_block_gates, max_global_width=max_global_width,
    )
    if fresh != proof:
        raise ValueError("bilinear proof receipt differs from frozen source or replacement")
    if require_saving and fresh.weighted_delta >= 0:
        raise ValueError("proven substitution is not cheaper under declared gate weights")
    candidate = Program(
        original.width,
        original.gates[:span[0]] + proposed.gates + original.gates[span[1]:],
    )
    if digest(candidate) != fresh.candidate_sha256:
        raise ValueError("frozen candidate and newly verified result disagree")
    applied = AppliedBilinearSubstitution(candidate, fresh)
    guard.check_time()
    return applied

def optimize_gf24_substitution(
    source: Circuit, span: tuple[int, int], *,
    wires: tuple[int, ...], weights: BilinearWeights,
    budget: Budget | None = None, require_saving: bool = True,
    max_block_gates: int = 10_000, max_global_width: int = 4096,
) -> tuple[str, AppliedBilinearSubstitution]:
    """Select the cheapest declared GF24 method and PROVE its exact insertion.

    The whole original source is frozen BEFORE candidate generation, so a
    caller's later mutation cannot escape the pinned proof. All candidate
    methods are treated as untrusted gate streams: the exact tensor and
    restoration invariants are recomputed against the actual mapped gates,
    not taken from the optimizer. A single deadline covers selection,
    mapping, checking, replay, and application.
    """
    from symq.labs.gf24_choice import choose_gf24
    from symq.labs.gf24_tower import GF24_MODULUS

    guard = _limit(budget)
    if type(weights) is not BilinearWeights:
        raise TypeError("explicit BilinearWeights required")
    original = Program.freeze(source)
    mapping = _interface(
        original.width, 24, GF24_MODULUS, wires, span, len(original.gates),
        max_global_width,
    )
    guard.check_time()
    selection = choose_gf24(ccx_weight=weights.ccx, cx_weight=weights.cx)
    # Build the actual global gate stream from the exact chosen local circuit.
    # Do not use, accept or trust a precomputed optimization/proof flag.
    inverse = tuple(w for w, _ in sorted(mapping.items(), key=lambda item: item[1]))
    mapped = Circuit(
        original.width, [
            Gate(g.name, tuple(inverse[q] for q in g.qubits))
            for g in selection.circuit.gates
        ],
    )
    guard.check_time()
    snapshot = original.circuit()
    proof = check_bilinear_substitution(
        snapshot, span, mapped, n=24, modulus=GF24_MODULUS,
        wires=wires, weights=weights, budget=guard.inherited_budget(),
        max_block_gates=max_block_gates, max_global_width=max_global_width,
    )
    applied = apply_bilinear_substitution(
        proof, snapshot, span, mapped, budget=guard.inherited_budget(),
        max_block_gates=max_block_gates, max_global_width=max_global_width,
        require_saving=require_saving,
    )
    guard.check_time()
    return selection.method, applied
