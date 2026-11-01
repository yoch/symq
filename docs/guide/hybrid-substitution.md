# Hybrid contextual substitution (experimental)

This thin adapter to the existing [exact local channel transcript
checker](experimental-composition.md) takes a real HybridProgram,
a [start, stop) span of global operations, a local replacement fragment and
a local-to-global wire map. It assembles both complete programs, verifies
exact coverage, and calls the existing coherent channel/instrument theorem.

The adapter lives in symq.labs and carries **no stable API promise**.

## Example

```python
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.channel_composition import HybridFragment
from symq.labs.hybrid_substitution import check_hybrid_substitution

reference = HybridProgram(3, 1, [
    HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
    HOp("ccx", (0, 1, 3)),
])
replacement = HybridFragment(4, (
    HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
    HOp("hmr", (3,), slot="b0"),
    HOp("cz", (0, 1), condition="b0"),
))
proof = check_hybrid_substitution(
    reference, (0, 3), replacement, wires=(0, 1, 2, 3),
    clean=(3,),
)
assert proof.equivalent
```

Run the full [standalone demo](../../examples/hybrid_substitution.py) to
also observe rejection of the missing conditional phase-correction mutant.
The actual proof includes every off-diagonal |x><y| matrix unit, rather than
a classical truth-table comparison. It checks the full channel with all
global quantum wires retained by default; live classical reads in the suffix
induce an instrument comparison. A declaration of clean preparation is not
enough: the verifier requires it from the actual prefix.

The wire map is injective and uses local indices on the candidate. Existing
classical slots must use the same names on both sides; an incoming slot must
be declared in the fragment's classical_inputs and is universally quantified.
Dirty preserved wires use the full identity-frame criterion, including
correlations, not only equality of final basis values.

A successful report includes the hashes of the two *complete frozen* global
streams and the contract, plus operation counts and local coherence pairs
checked. These are receipts for rechecking, not a standalone certified
proof artifact. A failed local channel equation may involve a cut state
unreachable from the global prefix: the adapter reports not_proved, not
a falsely claimed global difference.

The existing local exact oracle is deliberately limited (six quantum wires,
eight measurement events and 256 branches by default); a connected global
circuit can be wider because common prefix and suffix operations are handled
compositionally. Input consists of arbitrary coherent data plus declared
zero-prepared ancillas; no classical input-domain predicate is silently
upgraded to quantum coherent support.

Operation counts compare heterogeneous resources (HMR versus CCX etc.) and
do **not** constitute an official cost model or speedup claim. Phase-debt
analysis via symq.labs.ledger is complementary and cannot substitute for the
coherent channel proof. This is a bounded implementation milestone, not
arbitrary QASM3/H/S/T/rotation verification or an automatic optimizer.
