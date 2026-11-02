# Table loaders with measurement-based uncomputation (research; issue #144)

`symq.labs.hmr_table_contract` checks a finite-table XOR oracle whose implementation uses
X-basis measure-and-reset (HMR), phase corrections and classical control. It is a bounded,
exact prototype in `symq.labs`, with no API promise. The phase-free reversible case is a
separate adapter (PR #153). This module does not depend on it, and only its contract format
is reused.

## 1. The contract

The source is a `symq.experimental.hybrid.HybridProgram` with `n` data wires and `k` ancilla
wires, all of which are physical wires `0..n+k-1`. A contract partitions them into address
wires `A`, target wires `Z`, clean wires `S` and borrowed wires `D`, each listed LSB first.
The program's own ancilla wires must be declared clean. The table `T` has one row per address
word. A row may be `None` (do not care) only when its address is illegal.

- **Input support.** `P` is the span of the legal basis inputs `|a, z, 0_S, d>`: `a` in the
  explicit legal address set, `z` in the target domain (the full cube or an explicit list),
  clean wires zero, and any borrowed value `d`.
- **Ideal map.** `W |a, z, 0_S, d> = |a, z XOR T[a], 0_S, d>`. `W` is an isometry on `P`.
- **Outputs.** Every quantum wire is retained and compared: address, target, clean wires
  (which must be zero again) and borrowed wires (which must be restored).
- **Records.** Every classical slot, including every measurement record, is forgotten at
  the end. No record may be declared visible (see section 5).
- **Theorem.** For every reference system `R` and every density operator `rho` supported
  on `P ⊗ R`, `(E ⊗ id_R)(rho) = (W ⊗ I) rho (W ⊗ I)†`, where `E` is the program's channel
  with the records forgotten. This covers all coherences `|x><y|` and any entanglement
  between the borrowed wires (or any other wire) and an external reference.

Nothing is claimed outside `P`. In particular, nothing is claimed about illegal addresses,
targets outside the domain or dirty clean wires.

## 2. Kraus branches of a hybrid program

A **branch** `m` is a full outcome sequence: the outcome of every `hmr` and `measure_z` event
in program order, plus the hidden pre-reset bit of every `reset` (the Kraus index of
`|0><0|` and `|0><1|`). Each classical slot is a function of the outcomes so far, because
`store`, `invert` and `oxor` only combine them. So each conditional gate is fixed once `m`
is fixed, and the branch is one linear operator `K_m`. With `V|v> = |v>|0_anc>`,

`E(rho) = sum_m K_m V rho V† K_m†`.

Forgetting the record is this sum. A record is a function of `m`, so a coarser grouping by
record values gives the same channel.

## 3. Criterion and proof

**Criterion (C).** For every branch `m` there is a scalar `c_m` such that
`K_m V |psi> = c_m W |psi>` for every `|psi>` in `P`.

**Theorem.** (C) holds if and only if the contract theorem of section 1 holds. When it
holds, `sum_m |c_m|^2 = 1`.

*Sufficiency.* Take `|psi>` in `P ⊗ R`. Then `(K_m V ⊗ I)|psi> = c_m (W ⊗ I)|psi>`, because
the operator identity holds on `P` and extends to `P ⊗ R`. Summing the projectors over `m`
gives `(sum_m |c_m|^2) (W ⊗ I)|psi><psi|(W ⊗ I)†`. Every instruction is trace preserving
(unitaries, measure-and-forget, reset), so `sum_m V†K_m†K_m V = I`. Restricted to `P` this
gives `(sum_m |c_m|^2) W†W = I_P`, so `sum_m |c_m|^2 = 1`. Mixed states follow by linearity.

*Necessity.* This step is stronger than the issue asked for. Suppose the channels agree on
`P`, and take a unit vector `psi` in `P`. Then `sum_m A_m|psi><psi|A_m† = |W psi><W psi|`,
where `A_m = K_m V`. Every term is positive, so for any `phi` orthogonal to `W psi` we have
`sum_m |<phi|A_m psi>|^2 = 0`. Hence `A_m psi = c_m(psi) W psi`. Now consider the linear map
`A_m W^{-1}` on the subspace `W(P)`. Every vector of that subspace is an eigenvector, so the
map is a scalar. Write `c_m(psi1) W psi1 + c_m(psi2) W psi2 = c_m(psi1+psi2) W(psi1+psi2)`.
Because `W psi1` and `W psi2` are independent, the coefficients are equal. ∎

This is the usual statement that a channel of Kraus rank one (an isometry) has only
proportional Kraus representations. A consequence is that an input-dependent branch phase
can **never** "cancel in the mixture". Such a branch always damps some legal coherence:
`E(|x><y|)` has coefficient `2^-H sum_m s_m(x) s_m(y) < 1` on `W|x><y|W†`.

### Reduction to obligations for the hybrid grammar

On a basis ket, every instruction maps one ket to at most one ket. Permutations move the
ket, sign gates multiply it by ±1, and `measure_z` and reset keep or kill it. An `hmr` gives
both outcomes, each with amplitude `±1/√2`. Measurements and resets cannot be guarded by a
condition, so every branch passes through all `H` HMR events, and `K_m V |v> = s_m(v) 2^(-H/2) |out_m(v)>` with `s_m(v)` in `{+1, -1, 0}`.
`K_m V` is linear, so (C) on `P` is equivalent to the following checks over the legal basis
inputs `v`:

| obligation | statement |
| --- | --- |
| `permutation` | every nonzero branch maps `v` to the basis state `W v` (table cell, address, borrowed and clean wires, ancillas zero) |
| `branch_support` | the set of nonzero branches is the same for every legal `v` (Z measurements and resets have input-independent outcomes on `P`) |
| `branch_phase` | the sign `s_m(v)` of each branch is the same for every legal `v` |
| magnitude | automatic: every nonzero amplitude is `2^(-H/2)` |
| normalization | automatic: each basis input has exactly `2^H` nonzero branches; checked as an internal consistency assertion |

The arithmetic is exact: integer signs on the common scale `2^(-H/2)`. The phase may
differ between branches. An outcome-dependent **global** sign is accepted.

## 4. Where the criterion is and is not complete

For the contract above the checker is a decision procedure. Within its caps, `equivalent`
is a proof. A `not_proved` carries a legal pair `(x, y)` such that `E(|x><y|)` provably
differs from `W|x><y|W†`:

- `x = y` for a `permutation` failure: a diagonal entry lands on a wrong basis state, and
  positive diagonal terms cannot cancel;
- `x ≠ y` for `branch_support` and `branch_phase` failures, with the exact coefficient,
  which is not 1.

The test suite checks this agreement against an independent oracle on 4,800 random cases.

The criterion is **not** complete for nearby contracts. Any refusal there is a property of
the contract, not a checker bug:

- **Strict O1/O2 sign/HMR theory** (`symq.phase`). That theory demands one Kraus operator
  for all outcomes. It refuses `x(anc); hmr(anc)`, whose outcome-only sign leaves the
  forgotten channel unchanged. Criterion (C) accepts it.
- **Garbage-tolerant scratch** (traced, not retained). Suppose an ancilla ends in an
  input-independent state, such as `|1>` or `|m>`. Then the traced channel is ideal, but (C)
  refuses because the retained wire is not clean. The right criterion for that contract is
  `K_m V = (W ⊗ |j_m>)` on `P`, with input-independent junk `|j_m>`. That contract is not
  implemented.
- **Legal support only.** A correction valid only on `P` is accepted. The cheaper phase
  `(-1)^(1+a0+a1)` equals `(-1)^[a=0]` on `a ∈ {0,1,2}` but not on `a = 3`. No claim is made
  on the full address space, and the oracle shows that no row `T[3]` makes the full-space
  channel an XOR isometry.

## 5. Visible records and classical slots

A slot passed in `observed_slots` is refused as `unsupported` (obligation
`visible_record`): the XOR contract has no classical output, and a visible record asks for
an instrument contract, which is not checked here. This status says nothing about the
forgotten channel; only `not_proved` (obligations `permutation`, `branch_support`,
`branch_phase`) carries a coherence witness on which the channels differ. Under
(C) the record is in fact decoupled: `E_r(rho) = p_r W rho W†` with
`p_r = sum_{m: r(m)=r} |c_m|^2`, independent of the input. A future instrument contract
("`W` and an independent coin") could therefore reuse the same check, but this prototype
does not state that theorem.

Measuring the AND ancilla in the Z basis and flipping it back by feed-forward does leak.
The record equals `[a = 0]`. Even when the record is forgotten, the measurement dephases
the address, and the check refuses it as `branch_support`.

Classical slots (`store`, `invert`, `oxor`, `!`-negated conditions) are allowed anywhere.
They are functions of the branch and are discarded at the end.

## 6. Public example and API

`and_uncompute_example()` returns the loader and its contract. It uses address wires 0 and
1, target wires 2 and 3, borrowed wire 4 and clean ancilla 5. The legal addresses are
`{0, 1, 2}` and the table is `T = [0b00, 0b01, 0b11, *]`. The program works as follows:

1. It computes `anc = [a = 0]` with a Toffoli on the negated address bits.
2. It XORs `NOT anc` into target bit 0.
3. It XORs `a1` into target bit 1 through the borrowed wire, with the toggle trick
   `t ^= d; d ^= a1; t ^= d; d ^= a1`.
4. It uncomputes `anc` with `hmr`.
5. It applies the CZ phase correction (sandwiched by X on both address bits) conditioned on
   the outcome.

```python
from symq.labs.hmr_table_contract import and_uncompute_example, check_hmr_table_xor

program, contract = and_uncompute_example()
result = check_hmr_table_xor(program, contract)
assert result.equivalent and result.branches == 2 and result.checked_inputs == 24

program.ops.pop(-3)  # drop the classically controlled CZ correction
refused = check_hmr_table_xor(program, contract)
assert refused.obligation == "branch_phase"
print(refused.witness["pair"], refused.witness["coefficient"])  # a damped |x><y|: 0
```

Statuses and what they mean:

| status | meaning |
| --- | --- |
| `equivalent` | criterion (C) holds on every legal input (a proof; at least one legal input) |
| `not_proved` | a channel obligation fails (`permutation`, `branch_support`, `branch_phase`); the witness is a legal coherence on which the channels differ |
| `unsupported` | the request is outside this contract: a visible record (`visible_record`, an instrument contract), a forged or out-of-grammar operation, a width mismatch or undeclared ancillas. It says nothing about the channel |
| `inconclusive` | a cap or the budget: `max_inputs`, `max_branches` (`2^H`), `max_steps`, `Budget.max_seconds` / `max_terms`, own or inherited from a `VerificationSession` |

Invalid arguments raise `TypeError`/`ValueError`. In particular `max_nodes` and
`max_bytes`, passed directly or inherited from a session, are refused because they do not
apply to this enumeration.

**Admissibility.** The contract and the program are detached snapshots rebuilt from exact
primitives before anything is checked, interpreted or hashed: a frozen contract mutated
after construction (for example an emptied legal set) is revalidated and refused, and an
operation whose name, wires or slot names are not exact `str`/`tuple`/`int` values (for
example a `str` subclass whose hash and equality imitate `"x"`) is `unsupported`. The same
snapshot gives the verdict and the source SHA-256. The deadline is checked on entry, after
the snapshot, for every legal input and before every decisive verdict. A positive verdict
requires every legal input to have been checked, and at least one. The result carries the
SHA-256 of the program and of the contract. There is no receipt replay format.

### Qualification (tests and `python -m benchmarks.hmr_table_contract`)

`benchmarks/hmr_table_contract.py` reruns the example, every mutation, the admissibility
attacks (forged empty domain, deceptive operation name, expired or inherited budget) and a
seeded random differential (400 programs × 12 contracts) against the oracle, writes a JSON
report with source hashes and the environment, and exits 1 on any disagreement. The
dedicated workflow uploads it as the `hmr-table-contract-evidence` artifact. The cohort is
synthetic and public: no holdout or speed claim.

The dense oracle (`tests/testkit/table_channel_oracle.py`) is independent of the checker. It
applies every instruction as an explicit local integer matrix `M rho M^T` to a sparse density
operator, with the HMR Kraus matrices scaled by `√2`. It compares all legal `|x><y|`, and a
state whose borrowed wire is maximally entangled with a reference qubit. The example is also
compared with the library's `coherence_image` on all 576 legal coherences.

| program | checker | oracle |
| --- | --- | --- |
| example | `equivalent` | equal on all 576 coherences and on the reference state |
| outcome-dependent global sign added | `equivalent` | equal (strict O2 refuses) |
| correction valid on legal addresses only | `equivalent` | equal on `P`, unequal with `a = 3` |
| correction omitted / doubled | `branch_phase` | coherence `a=0` vs `a≠0` lost (coefficient 0) |
| correction on another event / on `!b0` / on `[a=3]` | `branch_phase` | unequal at the witness |
| borrowed wire not restored | `permutation` | unequal |
| ancilla never uncomputed | `permutation` | unequal |
| Z-measurement or reset uncomputation | `branch_support` | unequal (dephased address) |
| wrong table cell (`T[2] = 0b10`) | `permutation` | unequal |
| visible record `b0` | `unsupported` (`visible_record`) | the instrument differs (each record carries half the output) |
| junk ancilla left in `\|1>` | `permutation` (out of contract) | unequal; ideal once that wire is traced |

## 7. Limits and next steps

- **Exponential cost.** The check runs over `|legal inputs| × 2^H` trajectories. There is
  no symbolic engine and no receipt or replay.
- **Grammar.** Signs are ±1 only. Dyadic or cyclotomic phases (S, T, rotations) would make
  `c_m` complex. The criterion still applies, but the arithmetic must move to `Z[ω]`.
- **Symbolic route** (not implemented). For the sign/HMR grammar, `symq.phase` gives outputs
  `f(x)` and a phase `φ(x,m) = φ0(x) ⊕ Σ_j m_j g_j(x)`. Then (C) is the following list of
  SAT queries under the legal-address predicate:
  - `f = W` on `P`;
  - `φ0` and every `g_j` are constant on `P` (instead of zero, as in O2).

  Z measurements and resets add the condition that each measured function is constant on
  `P`. Classically controlled X makes `f` depend on `m`. The query then becomes the miter
  `∃ x, x' ∈ P, m: f(x,m) ≠ W(x) ∨ φ(x,m) ≠ φ(x',m) ∨ measured(x,m) ≠ measured(x',m)`,
  which needs an encoding of the hybrid semantics with outcome variables.
- **Other contracts.** Garbage-tolerant scratch and visible-record (instrument) contracts
  need their own criteria (section 4) and are refused today.
