# Pilot B: equivalence by simulating the composed circuit

Files: `prototype/pilot_b.py` (dense random), `prototype/pilot_b2.py` (structured QCEC).
Raw numbers: `RESULTS.json`.

## 1. The mechanism, and what is prior art

`L ~ R` iff `L ; R^{-1}` is the identity permutation. That is a miter, and miters are how
combinational equivalence checking has been done since the 1990s: Wille et al. (ISMVL 2009) do
exactly this for reversible circuits, and ABC's `cec` does it with SAT sweeping on a miter. **No
novelty is claimed for the construction.**

The claim that *is* specific to the ANF/ZDD setting: the cost of the simulation is governed by
the intermediate polynomials, and on the composed circuit those polynomials track the *difference*
between the two circuits rather than each circuit separately. When `L` and `R` share a long
prefix and diverge in a few gates, the common part cancels as it is produced instead of being
materialised twice.

## 2. Where the prediction fails

Dense random circuits (`pilot_b.py`) do not separate the two methods at all: beyond 12 wires,
9 of 12 instances hit a 2 M-node budget in *both* arms. Dense random circuits are simply outside
the regime where either method works, which is consistent with the paper's finding that random
circuits defeat monomial representations under every order tried.

## 3. Where it works, and how much

Structured QCEC circuits (`pilot_b2.py`), 12 instances that both arms decide, widths up to 20:

| instance | separate nodes | miter nodes | ratio |
|---|---:|---:|---:|
| `5xp1_194` equiv | 580 | 580 | 1.00 |
| `5xp1_194` nonequiv | 432 | 471 | 1.09 |
| `add6_196` equiv | 3 624 | 3 624 | 1.00 |
| `add6_196` nonequiv | 3 908 | 2 381 | **0.61** |
| `alu1_198` equiv | 190 | 190 | 1.00 |
| `alu1_198` nonequiv | 143 | 137 | 0.96 |
| `dk27_225` equiv | 106 | 106 | 1.00 |
| `dk27_225` nonequiv | 114 | 121 | 1.06 |
| `example2_231` equiv | 2 447 | 2 447 | 1.00 |
| `example2_231` nonequiv | 2 149 | 2 045 | 0.95 |
| `mlp4_245` equiv | 1 638 | 1 638 | 1.00 |
| `mlp4_245` nonequiv | 1 516 | 880 | **0.58** |

Three observations:

1. **Equivalent pairs: identical, exactly.** This is what the mechanism predicts -- the composed
   circuit is the identity, whose simulation terminates early and allocates nothing extra -- and
   it also means the miter offers *no* advantage on the cases where the answer is "yes".
2. **Non-equivalent pairs: sometimes better, sometimes worse.** Two instances lose ~40 % of the
   nodes, two are within 5 %, two gain 6-9 %. The geometric mean over the four non-equivalent pairs is 0.79, but the
   spread is 0.58-1.09 on four points; that is not a result, it is a coin flip with a trend.
3. **The absolute numbers are tiny.** All twelve finish in milliseconds; a difference between 1 516
   and 880 nodes on a 20-wire circuit does not change what a user can verify.

Over all six non-equivalent instances the geometric mean of `miter / separate` node counts is
0.848, with the individual ratios spread from 0.58 to 1.09 (`RESULTS.json`, `summary`). Two
instances improve by ~40 %, two are within 5 %, two regress by 6-9 %.

## 4. A discarded prototype, recorded because it failed

Before the miter, I built a criterion that compares the two outputs as a single Boolean function
over the `2n` *pair* variables: `f_L(x) = f_R(y)` for all pairs, decided by one ZDD over `2n`
variables. It is elegant and it is a regression: the ZDD caps variables at 64, so the criterion
works only for circuits of width at most 32, whereas direct comparison works to 64. On the QCEC
corpus (widths 16-35) it therefore refuses half the instances the current checker accepts. No
results are reported for it; the code is not kept.

## 5. Verdict

Category II. The construction is prior art, the mechanism is real but small and unstable, and the
only regime where it is reliably *not worse* is the one where both methods are instantaneous. A
conditional integration (use the composed path only when the circuits share a long gate prefix)
is defensible engineering; it is not a publication.
