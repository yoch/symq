# Experimental local channel composition and replayable proof graphs

`experimental` APIs are opt-in verification tools. They do not discover an
optimization or certify the intended high-level algorithm. They compare the
concrete supplied streams under the documented input and observation contracts.
There are no imports from `research` in the installed implementation.

## Local channel substitution

`verify_channel_transcript` checks an ordered sequence of `HybridCommon` and
`ChannelSlot` objects against **both complete global operation streams**. The
caller pins both streams using `hybrid_digest`; a matching fingerprint binds a
stream but establishes no semantic property. Missing, reordered or changed
operations and non-injective wire or classical-slot maps are rejected.

A `HybridFragment(width, ops, classical_inputs=())` is immutable. Every local
quantum input is arbitrary. Every declared classical input is independently
universally quantified over its classical values. A `ChannelSlot` maps all local
wires and all used classical names injectively to global names. Its optional
obligations are:

- `clean`: local input wires proved to be zero by each actual global prefix.
  Initial global ancillas, explicit reset and HMR establish zero. Conservative
  pure basis-value propagation and previously verified local output facts can
  preserve that proof. An unknown cut wire is rejected; the declaration alone
  does not establish preparation.
- `preserved`: borrowed dirty wires whose local map must factor as
  `F tensor identity`, including every off-diagonal correlation. Agreement
  between the two implementations, or unchanged diagonal bit values, does not
  discharge restoration.
- `discarded`: local output wires allowed to be traced. They must also occur in
  `discarded_global` and have no quantum use anywhere in the covered suffix on
  either side. Trace followed by reset or reuse is rejected by this rule.

All local input matrix units `|x><y|` are checked with exact rational density
matrices. Consequently a successful local equation extends to an arbitrary
external entangled reference, including a frame made from other global wires.
The global width does not enter the local enumeration. Common operations may
connect the whole global circuit.

Classical liveness is reconstructed backwards from actual suffix reads and
`observed_slots`. If a slot produces a classical value read later, equality of
its unconditional quantum channel is insufficient: the local **instrument**
conditioned on that live record is compared. Reused classical storage names are
not measurement-event identities. Incoming classical values are enumerated
without assuming independence from the quantum state: equality for every
classical block extends by linearity to their correlations.

```python
from symq.experimental.composition import (
    ChannelSlot, HybridFragment, hybrid_digest, verify_channel_transcript,
)
from symq.experimental.hybrid import HOp, HybridProgram

# Compute AND, use it, then erase the temporary qubit coherently.
compute = (HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)))
reference_ops = compute + (HOp("ccx", (0, 1, 3)),)
candidate_ops = compute + (
    HOp("hmr", (3,), slot="b0"),
    HOp("cz", (0, 1), condition="b0"),
)
reference = HybridProgram(3, 1, list(reference_ops))
candidate = HybridProgram(3, 1, list(candidate_ops))
slot = ChannelSlot(
    HybridFragment(4, reference_ops), HybridFragment(4, candidate_ops),
    (0, 1, 2, 3), (("b0", "b0"),), clean=(3,),
)
proof = verify_channel_transcript(
    reference, candidate, (slot,),
    reference_sha256=hybrid_digest(reference),
    candidate_sha256=hybrid_digest(candidate),
)
assert proof.equivalent
```

This is a complete full-output channel equation, including the returned-zero
temporary qubit. The HMR record is dead. Removing the conditional CZ fails on
coherences. If the record is observed, this particular reference emits no record
and requires a different explicit instrument specification.

The independent public bridge example in the tests implements
`CX(a,b); CX(b,t); CX(a,b); CX(b,t) = CX(a,t)` while proving `b` is returned with
all correlations. A connected 71-wire example verifies a four-wire temporary-AND
replacement between entangling common prefixes and suffixes.

## Phase debt is reconstructed, not supplied

`ledger.verify_phase_ledger(program, discharges)` replays sign/permutation/HMR
operations as ANFs. Every HMR gets an immutable `MeasurementEvent` with its actual
operation index, measured expression and fresh outcome variable. Classical
stores, XORs, inversion and overwrite are replayed separately.

`PhaseDischarge(event, after_operation)` demands the reconstructed coefficient
of that exact event is zero immediately after that exact operation. Claims
before the event, invented event IDs, a missing correction, a wrong reused
classical bit, or a debt reintroduced after discharge are rejected. By default
every event needs a discharge point and no event debt may remain at the final
boundary. `PhaseLedgerProof.assert_fresh` detects changed source streams.

The ledger is an algebraic obligation checker, **not** a channel proof by itself.
It rejects Z measurements and resets of values not proved constant. The channel
transcript checker remains responsible for the complete quantum equation.

## Proof proposals and a separate checking kernel

`proof_graph.ProofGraph` is a versioned immutable obligation DAG. Leaves contain
complete immutable `ClassicalObligation`, `ChannelObligation`, `TranscriptObligation`, or
`LedgerObligation` inputs. Internal nodes mean conjunction only; they cannot
invent a semantic equivalence from unrelated leaves. A composition conclusion
must contain a `TranscriptObligation`, which rechecks coverage and every local
lemma. There is currently no automatic decomposition/discovery optimizer.

`ProofKernel.verify` recomputes every uncached reachable leaf using exact engine
entry points. A live kernel may reuse its own successfully verified immutable
content. Its content addresses include the kernel version, full query and
recursive dependency addresses, so a leaf change invalidates every ancestor.
The cache is local to that kernel instance. Optional cache-directory JSON files
are inspection receipts and are **never read as certification authority**.
Exported graphs are proposals: importing JSON and finding an `accepted` field
never certifies anything. Unknown graph versions, object types, extra verdict
fields, missing dependencies, cycles and excessive serialized size are refused.

With `independent=True`, each leaf runs twice in fresh spawned subprocesses via
`experimental.execution.run_isolated`. No algebra manager or native node ID is
shared. Classical obligations use sparse and truth-table backends. Hybrid
obligations repeat the exact oracle in independent processes; this provides
process isolation, not a second semantic implementation. Every run reports its
status, wall/CPU time, peak RSS and exit code. `parallel_workers=2` admits two
independent leaves concurrently in bounded batches; the default is one. The
configured worker memory envelope is divided among admitted workers. No more
than eight workers may be requested. Failure, crash or limit expiry
cannot become a successful proof. A single parent verification deadline covers
all leaves, both runs and process cleanup. The whole-graph duration is bounded
by the tighter of `Budget.max_seconds` and `HardLimits.wall_seconds`.
`HardLimits.memory_bytes` is the total simultaneously admitted worker envelope;
each worker also receives the optional CPU limit.

## Boundaries and validation

The default local oracle limits are six quantum wires, eight measurement events,
256 branches and six incoming classical bits. Enumeration is exponential in
these local sizes. Limits are explicit arguments and fail with
`ResourceLimitExceeded`; no fallback approximation is attempted. The ledger has
separate operation, variable and explicit-term limits. All budgeted entry points
join the common `VerificationSession` deadline.

The supported quantum grammar is precisely the installed hybrid oracle's basis
permutations, sign phases, X-basis HMR, Z measurement, real reset and its classical
feedback operations. H/S/T and other unrecognized operations are rejected. The
prefix clean proof is intentionally incomplete: some valid preparations require
a larger explicit local lemma or are refused. Nonterminal local trace is also
intentionally unsupported.

`tests/test_quantum_composition.py` covers temporary-AND, the borrowed bridge,
coherent/frame obligations, a connected wide circuit, live instruments,
classical cut values, exact stream coverage, mapping aliases, invented clean
facts, overwritten event names, phase discharge points, JSON verdict forgery,
transitive cache invalidation and subprocess replay. The existing temporal
classical transcript tests continue through their research compatibility shim;
the maintained implementation is `experimental.classical_transcript`.
