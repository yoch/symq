# Public opt-in API: exact finite-table XOR contracts

This opt-in API originated in the independently audited #153 implementation,
integrated by #158 at main@91c1d3d1a4a157c8e8e5b9badb198e3d623ffc60.
The later compact-domain extension reuses the existing Boolean predicate IR
and the same phase-free theorem; it adds no new proof engine or quantum gate
semantics. Its tests and scope are documented separately below.

## Supported entry points

```python
from symq.experimental import (
    TableXorContract, TableXorResult, PredicateValues, ReceiptMismatch,
    check_table_xor, replay_table_xor,
)
```

The same names are available from `symq.experimental.table_xor`. Historical
`from symq.labs.table_xor_contract import ...` imports resolve to the same objects.
The maintained implementation imports no labs modules. No root-level default or
`verify()` dispatch changes. SymQ remains research software with no frozen stable
API promise; this is an explicit supported opt-in interface.

The contract is distinct from `VerificationContract`: it compares an actual
phase-free reversible Circuit with an independent integer table, not two quantum
programs. Do not pass it to the general channel `verify()` API.

`PredicateValues` supplies compact address or target domains with a concretely
checked nonemptiness witness. `PredicateValues.below(11, 1220)` represents the
unsigned interval without enumerating it. Generic predicates reuse
`PredicateDomain`; logical word bits are rebound to the contract's physical
wire order. New synthetic tests cover both backends, nontrivial mappings,
dirty-target widening, forged/empty domains, stale replay and 1,220 legal
addresses. They do not qualify a consumer's actual loader or prepared state.
Predicate contracts use schema 2; listed-only contracts keep schema 1 and
their canonical hashes. See [compact domain details](table-xor-contract.md#compact-domains-and-nonemptiness).

## Exact claim

For every legal address, every declared target encoding and arbitrary borrowed
workspace, all quantum outputs must equal

```math
|a,z,0_s,d\rangle \mapsto |a,z\oplus T[a],0_s,d\rangle.
```

Only X/CX/CCX/MCX are admitted. For that phase-free permutation grammar, equality
on every legal basis vector extends to the coherent span and arbitrary external
references. HMR, measurements, reset and general phase gates are **not** covered.
A restricted target encoding is never promoted to a full dirty-target guarantee.
Preparation at an actual substitution cut remains a separate obligation.

The SAT and exhaustive backends keep their existing explicit selection and caps.
`equivalent`, `different`, `inconclusive` and `unsupported` remain distinct.
A true mismatch has a concrete witness. A budget refusal is not a mismatch.
Malformed inputs raise the same exceptions as before. `ReceiptMismatch` remains
a ValueError, not a newly promised member of the SymqError hierarchy.

Replay requires independently pinned canonical source and contract hashes, checks
the untrusted record, and reruns verification. It is not a portable proof kernel.
All legal-domain/layout/table/slot/theorem fields are covered by the contract hash.
The explicit replay caps and inherited-budget refusals from the external audit
are preserved, including inconclusive results when a fresh replay cannot finish.

## Maturity decision

Promote this narrow adapter because its source/specification contract, positive
and negative paths, independent 27-case corpus, compatibility requirements and
replay behavior have been independently audited and corrected. Promotion does
not assert scale beyond those validations or performance against other systems.

Do not promote the other wave-3 labs modules merely because their CI is green:
- `phase_delta_binding` still depends on private phase-quotient/dyadic helpers;
- backward-ancilla/shift-diagonal engines need a consistent effect-proof API;
- affine-basis methods remain a comparative study;
- HMR table verification remains a bounded prototype without portable replay.

The research priority is symbolic branch elimination and nonlinear signature
certificates. This API relocation is deliberately separate from that work.

See [the full contract guide](table-xor-contract.md) for examples and boundaries.
