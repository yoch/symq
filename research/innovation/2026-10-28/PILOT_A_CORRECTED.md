# Pilot A, corrected: what the channel criterion actually decides

Replaces the conclusions of `PILOT_A.md` where they were wrong. The original file is kept as a
record; `PILOT_CORRECTIONS.md` lists the defects (A1-A6).

## The corrected comparison

`prototype/pilot_a_corrected.py` compares every program with **its own** specification, not with
the identity, and cross-checks every verdict with the exact density-matrix oracle. **17 programs**:
three AND gadgets (data correction, outcome-only correction, no correction), twelve AND chains of
lengths 1, 2, 3 and 5 in the same three variants, and two syndrome pairs.

| group | 17 programs |
|---|---|
| accepted by both the strict and the channel criterion | 4 (`and_gadget_data`, `and_chain_1_data`, `and_chain_3_data`, `and_chain_5_data`) |
| accepted **only** by the channel criterion | **1** (`syndrome_invertible_left_vs_middle`) |
| accepted only by the strict criterion | 0 |
| rejected by both | 12 |
| incompatible with the model | 0 |
| criterion disagrees with the oracle | **0** |

`and_chain_2_data` is in the "rejected by both" group, and correctly: chaining two AND gadgets on
the *same* data wire is not the same function as one `ccx`, and the oracle agrees.

## The one acceptance the strict criterion cannot make

`syndrome_invertible_left_vs_middle`: the left program measures `x0` then `x1`, the middle one
measures `x0` then `x0 xor x1`. The two syndrome vectors are related by the invertible map
`(u, v) -> (u, u + v)`, so their kernels -- the set of pairs `(x, y)` with equal syndrome -- are
identical, and by (CH) the channels agree. O2 rejects the middle program because its phase depends
on the outcomes; the channel criterion accepts it, and the oracle confirms it.

Its sibling, `syndrome_same_control_left_vs_right`, measures `x0` twice: the kernel changes, both
criteria reject it, and the oracle agrees. That pair is the positive and negative control of the
whole criterion.

## What this means for the science

The criterion is **sound** (no disagreement with the oracle in the 17 designed cases and in 550 random
pairs across the test suite) and **strictly more expressive** than the O2 obligation. It is also
**narrow**: one designed acceptance out of seventeen, and that acceptance is an artefact of how the
programs were written, not a feature a compiler would emit.

The claim that survives is:

> Equality of the channels of two programs in this fragment can be decided without enumerating
> measurement outcomes, by comparing two Boolean functions of the input pairs; the obligation it
> enforces is strictly weaker than outcome independence, and the extra programs it accepts are
> exactly those whose syndrome vectors differ by an invertible GF(2) map.

That is a correct statement about a decision procedure. It is not evidence that anyone needs it.

## The size question, measured separately

`PILOT_A.md` reported "ratio 1.00" between the factored and expanded phases and concluded that
factorisation buys nothing. That conclusion was too broad. The number of monomials is indeed
identical -- a mathematical consequence of affinity in the outcomes -- but the *representations*
differ in other dimensions, which `pilot_scale.py` measures:

| dimension | factored `(phi0, g)` | expanded `phi(x, m)` |
|---|---|---|
| monomials | `|phi0| + sum |g_j|` | `|phi0| + sum |g_j|` (identical) |
| variables | `data + M` (the `g_j` are indexed by `j`) | `data + M` |
| building `phi` | `sum_j m_j g_j`, one product per measurement | direct |
| the channel criterion | needs `phi0` and the `g_j` **separately** | needs an extra projection over `m` |

So the factorisation is not a compression, it is a **decomposition**, and its value is that it
makes (CH) a statement about functions of `x` alone. That is the honest way to state it, and it is
what `PILOT_A_CORRECTED.md` now says instead of "factorisation buys nothing".

## Limits that remain

- The comparison against Irene and phased outcome-complete simulation is still not done: neither
  tool is installed and neither accepts this fragment directly.
- No public measurement-assisted-uncomputation corpus has been imported; until one is, the
  practical value of the criterion is unmeasured rather than negative.
