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

The cooperative verification deadline starts **before freezing the source,
reconstructing the candidate, generating the contract and hashing the streams**.
It is not a hard process timeout, and unusually expensive Python operations
can overshoot before the next cooperative check, but cannot turn into a valid
positive result after expiry.

To materialize a proven rewrite, use
`apply_verified_hybrid_substitution(receipt, source, span, replacement,
wires=..., clean=..., ...)`. It **freezes the mutable input stream before
reverification**, uses a single entry-time deadline, and returns an
`AppliedHybridSubstitution` containing the immutable
`FrozenHybridProgram` candidate and the fresh proof, plus explicit
clean/preserved/discard/observation frame metadata. The constructed candidate
uses the very same frozen source that was checked; neither later mutation nor
a forged success flag can authorize a different program. Applying this
candidate outside its original declared input frame is not justified.

A typed result can be replayed via
`replay_hybrid_substitution(receipt, source, span, replacement, wires=...,
clean=..., ...)`: it **recomputes** the complete coherent-channel or
instrument check, refuses any changed full stream, local frame, declared
cost model or obligation limits and returns the fresh result. JSON with a
forged success field can never authorize a rewrite; this replay requires a
typed result and the original inputs, not an untrusted result dictionary.

A successful report includes the hashes of the two *complete frozen* global
streams and the contract, plus operation counts and local coherence pairs
checked. These are receipts for rechecking, not a standalone certified
proof artifact. A failed local channel equation may involve a cut state
unreachable from the global prefix: the adapter reports not_proved, not
a falsely claimed global difference.

The tests also embed the already-published, source-pinned Qualtran GF2MulMBUC
m=1 Apache-2.0 decomposition in a concrete prefix/suffix and check a missing
phase-correction mutant. This is genuine public compiler output, but an
already-explored qualification fixture, **not a fresh holdout**.

The existing local exact oracle is deliberately limited (six quantum wires,
eight measurement events and 256 branches by default); a connected global
circuit can be wider because common prefix and suffix operations are handled
compositionally. Input consists of arbitrary coherent data plus declared
zero-prepared ancillas; no classical input-domain predicate is silently
upgraded to quantum coherent support.

Operation counts compare heterogeneous resources (HMR versus CCX etc.) and
do **not** constitute an official cost model or speedup claim. For an
explicit user-defined operation-weight proxy, supply immutable
`HybridWeights((("ccx", 10), ("hmr", 0), ("cz", 2)),
unit="illustrative_compiler_units")` to `check_hybrid_substitution(weights=...)`.
Unspecified kinds default to weight 1. The resulting `weighted_delta` is
purely in those declared units; this does not compute fault-tolerant T-count,
logical depth or a Kaggle benchmark's official score. Phase-debt
analysis via symq.labs.ledger is complementary and cannot substitute for the
coherent channel proof. This is a bounded implementation milestone, not
arbitrary QASM3/H/S/T/rotation verification or an automatic optimizer.

## P0 file-based coherent HMR pathway and Qualtran evidence

The [complete coherent P0 workflow](hmr-p0-workflow.md) reuses this
exact local theorem and fresh frozen application without introducing
a duplicate oracle. It parses strict versioned `HybridProgram` and
`HybridFragment` JSON, an explicit quantum/input/record/cost
contract, then produces a self-contained SHA-256-backed report which
must be **reproved before application**, even after input files are
removed. A fresh, hard-limited subprocess is the CLI default.

The public m=1 and m=2 Qualtran GF2MulMBUC fragments exercise the
prepared-zero ancilla channel theorem on all 16/256 coherent matrix
units. Missing CZ corrections are rejected by independent Kraus
oracles despite agreement on classical diagonals; observed classical
records require the separate instrument obligation. These are
already-explored public qualification fixtures, **not a holdout**.
