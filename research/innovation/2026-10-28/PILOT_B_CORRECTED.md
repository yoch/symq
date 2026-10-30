# Pilot B, corrected: the miter is *not* the right strategy, and the mechanism says why

Replaces `PILOT_B.md`. The original measured node counts only, which cannot separate "fewer nodes,
more time" from "better on both"; and it never tested the case the mechanism was supposed to
favour. `PILOT_CORRECTIONS.md` item B1 records the defects.

## Protocol

Every arm builds a **fresh manager** (no shared caches). Construction of the composed circuit is
timed and charged to the miter. Three families, fixed before the run:

* **prefix** -- a long common gate prefix, then six gates of divergence: the case the mechanism
  predicted would favour the miter;
* **structure** -- `R` is a semantics-preserving rewrite of `L` with no textually shared prefix:
  the realistic case of a compiler optimisation;
* **arithmetic** -- adders of 12, 16 and 20 bits against their own inverse.

## Results

| family | decided pairs | miter faster | miter slower | function disagreements |
|---|---:|---:|---:|---:|
| prefix | 2 | 0 | **2** | 0 |
| structure | 2 | 0 | 0 | 0 |
| arithmetic | 3 | 0 | 0 | 0 |

`miter / separate` wall time:

| family | min | median | max |
|---|---:|---:|---:|
| prefix | 3.20 | 6.73 | 6.73 |
| structure | 0.85 | 0.98 | 0.98 |
| arithmetic | 0.84 | 0.87 | 0.90 |

## Why the prediction failed

The mechanism argument was: simulating `L ; R^{-1}` keeps the intermediate polynomials on the
*difference*, so a long common prefix cancels instead of being materialised twice. The measurement
says the opposite, and the reason is visible in the numbers: `separate` simulates two circuits of
`prefix + 6` gates and stops; the miter simulates one circuit of `2 * prefix + 12` gates. Even if
the tail cancels perfectly, the *common prefix itself* must be simulated twice -- first forward,
then inverted -- and the cancellation only happens at the very end, when the identity is reached.
The composed circuit does not avoid the common work; it repeats it.

For the mechanism to pay, the prefix would have to be cheap to replay in reverse, which it is not:
each gate of the inverse costs the same products as the forward gate.

The two other families are neutral (0.85-0.98 median): on structurally similar circuits the miter
neither helps nor hurts, and on adders it is a wash. Both arms decide the same function every
time, which is the minimum a correctness check should demand.

## Conclusion

**Negative, and the route is closed.** The composed-circuit strategy is prior art (Wille et al.
2009, ABC), and on this engine it is neutral at best and up to 6.7x slower in the regime it was
designed for. It is **not integrated**, and no follow-up experiment is justified: the only way to
make it competitive would be to simulate the inverse prefix cheaper than the forward prefix, which
the algebra does not offer.

This also corrects the original `PILOT_B.md`, which reported a -39 %/-42 % node reduction on two
QCEC instances and called it "real but unstable". In time, those same instances are a wash.

## What would still be worth doing

Nothing in this direction. If equivalence checking by composition is wanted, the prior art
(SAT sweeping on a miter, in ABC) is the right tool and is a *different* engine, not a mode of
this one.
