# Resource obligations at a substitution site

`symq.labs.site_resources` is an opt-in research adapter around the existing
hybrid substitution checker. It separates a **local theorem under explicit
resource assumptions** from proof that those resources exist at the actual
source position. It supplies an inspection dossier; it never returns or
authorizes a rewritten candidate.

## Example: a valid HMR identity with an unproved resource

```python
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.channel_composition import FrozenHybridProgram, HybridFragment
from symq.labs.site_resources import (
    EvidenceNote, ResourceLease, SiteResourceRequest, assess_site_resources,
)

reference = HybridProgram(4, 0, [
    HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)), HOp("ccx", (0, 1, 3)),
])
replacement = HybridFragment(4, (
    HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
    HOp("hmr", (3,), slot="b0"), HOp("cz", (0, 1), condition="b0"),
))
request = SiteResourceRequest(
    FrozenHybridProgram.freeze(reference), (0, 3), replacement, (0, 1, 2, 3),
    resources=(ResourceLease("temporary", 3, "clean_zero", (0, 3)),),
    notes=(EvidenceNote("temporary", "observation", "zero in sampled runs"),),
)
assessment = assess_site_resources(request)
assert assessment.local_equivalence.outcome == "equivalent"
assert assessment.contextual_equivalence.outcome == "not_proved"
assert assessment.site_applicability == "conditional"
```

Here all four source inputs are arbitrary. The local identity was freshly
checked assuming wire 3 is clean; the actual source has not established that
assumption. The observation is displayed and explicitly marked unused as proof.
Changing the initial interface to three data wires and one zero-prepared ancilla
allows this source's entry obligation to be discharged. This is a change to the
source model, not something an observation or a report can authorize.

The example and tests are original small fixtures. They do not reproduce the
external 40-to-39-CCX optimization, its 217-operation lifetime, or a 56-million-
operation source. The synthetic 217-operation regression tests only the meaning
of the lifetime contract.

## Exact statements and existing checkers

- `local_equivalence` reruns `check_hybrid_substitution` on an explicitly prepared
  local instance. Its clean conditions are recorded as conditions used by the
  local proof. They are not inserted into the real source.
- `contextual_equivalence` reruns that checker on the complete immutable source,
  exact operation interval, complete wire mapping and actual suffix.
- A clean input is proved only by the transcript checker's conservative pure
  basis-state propagation over the complete source prefix. Failure to establish
  zero leaves an obligation open; an established one is reported separately.
- Clean return is a separate channel equation: the candidate must equal the
  candidate followed by a reset of that wire. Every quantum output is retained.
  This proves zero at return, including absence of residual correlations, under
  the local clean-input hypotheses. It does not demand zero inside the interval.
- Borrowed return reuses the existing identity-frame checker. It requires a
  channel of the form `F tensor identity` on the borrowed information, including
  off-diagonal correlations. Equal computational bits alone do not suffice.
- The actual suffix determines which locally written classical values remain
  live. Explicit observed slots also select an instrument comparison. Dead
  measurement records may be forgotten; live ones are not silently discarded.
- `freeze_hybrid` reconstructs classical SSA versions and immutable measurement
  identities. The dossier exposes source reads with their actual versions,
  including a previous destination read by inversion or XOR. It does not bind a
  read to a measurement that occurs later under the same mutable slot name.

These are channel or instrument decisions. They do not certify arbitrary new
coherent controls around a block: channel equality does not fix an underlying
unitary's global phase. A control already present in the checked operations is
part of the exact input; wrapping the resulting block in a new control requires
a separate theorem.

The existing phase ledger remains an algebraic debt checker, distinct from a
channel theorem. This adapter does not duplicate it or reinterpret ledger
receipts as channel proofs. The existing proof graph similarly continues to
accept concrete replayable obligations, not this dossier's verdict fields.

## Lifetimes and cache versions

Resource wire indices are local to `replacement`; `wires` maps them to the source.
Lease intervals use half-open operation positions in the original source. This
version discharges only leases covering exactly the selected contiguous window.
It includes the different replacement interval in the dossier. Wider reservations
remain open; there is no inferred hardware scheduler or resource allocator.

An ancilla reserved for 217 operations may be nonzero and entangled during those
operations. It must satisfy the declared preparation at entry and restoration at
return. `clean_zero` and `borrowed` are distinct requests, and a wire cannot carry
conflicting leases in one request.

`CacheRequirement` records a relation, its establishment and use cuts, and its
quantum/classical dependencies. Quantum dependencies are global source wires;
classical dependencies are slot names. Quantum touches conservatively change an
epoch; classical assignments change the reconstructed SSA version. The report
identifies changed dependencies, including an overwritten product or measurement
slot. A touch does not by itself refute an algebraic invariant: it requires a
fresh proof. Even unchanged versions do not establish a relation initially given
only as an assumption or observation.

Arbitrary cache relations are **not proved by this first adapter**. Their
obligations remain open, are not fed into the coherent solver as assumptions,
and prevent `site_applicability == "established"`. Future relation proving must
connect a concrete theorem to these source positions; editing metadata cannot
discharge the obligation.

## Evidence, budgets and limits

The request contains frozen, validated input objects. Its digest binds the whole
source, replacement, wire mapping, intervals, observations and requested
conditions. Changing a prefix invalidates this identity even if the window is
unchanged. Digests identify inputs; they do not prove an extraction or a theorem.

Caller evidence is restricted to `assumption` and `observation`. Recomputed proof
outcomes are produced by the checker, and the dossier distinguishes whether a
condition was used by the local theorem. `to_dict()` returns detached inspection
data with `advisory_only: true` and `candidate_authorized: false`. No API consumes
an edited report as authority or caches its positive verdict. Rechecking means
calling `assess_site_resources` on the exact typed inputs again.

`established` means the local and contextual computations and every supported
requested resource obligation passed in this call. `conditional` means the local
identity passed but the full request is not established. `not_established` is not
a claim that the complete circuit differs: a local universal condition can be
too strong for a particular reachable context. `not_applicable` distinguishes a
demonstrably unsatisfied resource condition (for example, the prefix proves the
requested clean wire is one) from an open obligation. Resource exhaustion is explicitly
`inconclusive`. Invalid typed inputs are rejected.

The evidence level is a recomputed exact engine decision, not an independently
checked certificate. The exact local oracle retains its existing default limits
(six local quantum wires, eight measurement events and 256 branches). One shared
whole-call deadline covers hashing, SSA reconstruction, every local/resource
check and the final contextual check. The source/replacement operation bound is
200,000; the global wire bound is 65,536 and the source measurement-event bound
is 1,024. These bounds may be tightened and are checked before allocating the
global propagation state or SSA event masks. Repeated classical reads retain
their SSA event mask without expanding a new event list for every read.
Each cache watch has at most 1,024 dependencies and snapshots only its own
dependencies at its two requested cuts, rather than copying all other watches.
Unsupported byte/node budgets are rejected. This module loads its complete
source and makes no streaming or large-circuit performance claim.

Cost and score are deliberately absent from this dossier. The compiler adapter
may assess cost after correction and applicability have been established.

## Validation

`tests/test_site_resources.py` includes coherent positive and negative controls,
an independent Kraus-trajectory oracle, dirty and unknown ancillas, temporary
nonzero state inside a 217-operation synthetic lease, borrowed phase errors,
missing HMR corrections, live/dead instruments, early and reused measurement
reads, overwritten caches, receipt forgery, prefix changes and inconclusive
resource exhaustion. It also accepts a semantics-preserving mutation; mutation
does not automatically mean non-equivalence.
