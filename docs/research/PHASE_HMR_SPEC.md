# Sign-phase reversible programs with X-basis measure-and-reset (specification)

Status: specification and reference implementation (`symq.phase`), issue #6. This is a
deliberately small fragment of quantum circuits. It is **not** a universal quantum
equivalence checker, and nothing outside the fragment is approximated: it is rejected.

## 1. Programs

A program has `d` data wires (indices `0..d-1`) and `a` ancilla wires (`d..d+a-1`).
Instructions:

| instruction | effect on a computational basis state |
|---|---|
| `mcx(c₁..c_k, t)` (`x`, `cx`, `ccx`) | `t ← t ⊕ c₁⋯c_k` |
| `mcz(q₁..q_k)` (`z`, `cz`, `ccz`) | amplitude × `(−1)^{q₁⋯q_k}` |
| `hmr(q)` → outcome `m_j` | measure `q` in the X basis (outcome `m_j ∈ {0,1}`), then reset `q` to `|0⟩` |
| `mcz_if(j, q₁..q_k)` | apply `mcz(q₁..q_k)` iff `m_j = 1` (classical feed-forward) |

Every other operation is rejected with `UnsupportedOperation`, in particular `h` outside
`hmr`, `s`, `t`, `y`, rotations, Z-basis measurement, classically controlled X-type gates
and conditions on more than one outcome bit. Phases are restricted to ±1.

Inputs are computational basis states `|x⟩` on data wires; ancillas start in `|0⟩`.
Linearity extends every statement below to arbitrary input superpositions.

## 2. Symbolic semantics

Let `R = GF(2)[x₀..x_{d−1}, m₀..m_{M−1}]/(v² − v)` with canonical ANF. The semantics of a
program is a tuple `S(P) = (f₀..f_{d+a−1}, φ)` of elements of `R`, computed by:

- initially `f_w = x_w` for data wires, `f_w = 0` for ancillas, `φ = 0`;
- `mcx(c, t)`: `f_t ← f_t ⊕ ∏ f_c`;
- `mcz(q)`: `φ ← φ ⊕ ∏ f_q`;
- `hmr(q)` producing the fresh variable `m_j`: `φ ← φ ⊕ m_j·f_q`, then `f_q ← 0`;
- `mcz_if(j, q)`: `φ ← φ ⊕ m_j·∏ f_q`.

**Theorem 1 (soundness of the semantics).** For every input `x` and outcome vector `m`,
the (unnormalized) Kraus operator of the outcome sequence `m` maps `|x⟩|0⟩_anc` to
`(−1)^{φ(x,m)} |f(x,m)⟩`, with norm `2^{−M/2}` after normalization; every outcome
sequence has probability `2^{−M}`.

*Proof sketch.* X, CX, MCX permute basis states and MCZ multiplies by the sign of the
product of its wires, which matches the update rules by induction. For `hmr(q)` on a basis
state with `q = b`: `H|b⟩ = (|0⟩ + (−1)^b|1⟩)/√2`; projecting on outcome `m` leaves
amplitude `(−1)^{m·b}/√2` on `q = m`, and the reset maps it to `q = 0`. Since `b = f_q(x,m)`
on that branch, the phase gains `m·f_q` and the wire becomes 0. Classically controlled
`mcz` is `mcz` raised to the power `m_j`. ∎

Note that `f` never depends on outcome variables: only `φ` can.

## 3. Obligations

- **O1 (clean ancillas).** `f_w = 0` in `R` for every ancilla wire `w`.
- **O2 (outcome independence).** `φ` does not depend on any `m_j` (no outcome variable in
  the support of its ANF). This states that every measurement's phase kickback is
  corrected.

**Theorem 2.** If O1 and O2 hold, then for every outcome sequence the program applies the
same map `U_P : |x⟩ ↦ (−1)^{φ(x)} |f_D(x)⟩` on the data wires, returns ancillas to `|0⟩`,
and `x ↦ f_D(x)` is a bijection, so `U_P` is unitary.

*Proof.* By O2 and Theorem 1 all Kraus operators are equal: `K_m = K`. Measure-and-reset
instruments composed with unitaries are trace preserving, so `Σ_m K_m†K_m = I`, hence
`K†K = 2^{−M} I`. With O1, `K = 2^{−M/2} U_P ⊗ |0⟩_anc`, and `U_P†U_P = I` forces
`f_D` to be injective on `{0,1}^d`, hence bijective. ∎

O1 and O2 are checked exactly, because ANFs are canonical: a polynomial is zero iff its
ANF is empty, and it depends on a variable iff that variable occurs in a monomial.

## 4. Equivalence

Programs `P` and `Q` with the same number of data wires (ancilla and measurement counts may
differ) are **equivalent** when both satisfy O1 and O2, `f_D^P = f_D^Q` and `φ^P = φ^Q`.
They are **equivalent up to global phase** when instead `φ^P ⊕ φ^Q = 1`. Other global
phases cannot arise in this fragment. By Theorem 2 and canonicity this decides `U_P = U_Q`
(respectively `U_P = −U_Q`) exactly. When the check fails, a witness input is produced
(minimum-degree monomial of a differing polynomial) and re-validated by the oracle.

## 5. Independent oracle

`symq.phase_oracle` simulates programs on sparse state vectors with integer amplitudes:
gates act on basis states directly, `hmr` applies an unnormalized Hadamard
`[[1, 1], [1, −1]]`, projects on the outcome and flips the wire back to 0. It shares no
code with the ANF semantics. Tests compare both on **all** inputs and **all** outcome
sequences of small programs (exhaustive), including random programs, the logical-AND
uncomputation pattern and deliberately wrong corrections.

## 6. Limits and assumptions

- Only ±1 phases. `S`, `T` and rotations need phases in `Z/4`, `Z/8` or `ℝ` and are out of
  scope. Extending to `Z/8` phase polynomials is a separate design (weighted phase ANF).
- Only X-basis measurement followed by reset of the measured wire. Z-basis measurement,
  measurement without reset and reuse of measured wires without reset are rejected.
- Feed-forward is limited to Z-type gates conditioned on one outcome bit.
- No claim is made about circuits that leave the fragment (for example Hadamard layers in
  QFT-like circuits, or `c2_182`'s controlled-V gates). Equivalence of such circuits
  requires path sums or decision diagrams over complex amplitudes.
- Real 2026 corpora with X-basis erasure and phase corrections (for example
  `andigu/uncompute`, see `CORPORA_RECENTS.md` of the handoff) still need an importer that
  maps their operation format into this fragment or rejects it. No such import is claimed.
