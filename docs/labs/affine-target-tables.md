# Wide affine target domains for streaming XOR-loader verification

The version-1 reference checker caps targets at 16 physical bits and represents
restricted targets by an explicit list. Raising that cap alone does not represent
40-bit targets with 35 independent bits. The new research entry point is
`verify_affine_table`, with a closed version-2 JSON contract and explicit ANF/SAT
selection. No stable API or default verifier is changed.

## Exact domain and theorem

Declare z = offset XOR B*u, where every column of B is an integer bit mask over
ordered target positions. Strict GF(2) elimination verifies full column rank.
Thus u ranges freely over r bits and maps bijectively to the declared 2^r physical
target words. The checker substitutes these affine functions at the actual physical
input wires; it does not enumerate words or silently widen the domain.

For all legal addresses, all u, and arbitrary borrowed workspace d, the same
streaming Kraus proof establishes

```math
|a,offset\oplus Bu,0_s,d\rangle
\mapsto |a,(offset\oplus Bu)\oplus T[a],0_s,d\rangle.
```

Equality of the branch isometries on the image extends to its coherent span and
arbitrary external references. All physical outputs are retained, including
dependent target coordinates. A witness in parameter coordinates is converted
back to a physical basis state, checked for membership, and replayed on the
actual source. The symbolic anchor is a *parameter* assignment; substituting the
physical offset into parameter variables would be unsound. Nonzero-offset tests
cover that distinction.

This is a declared support, not proof that a surrounding circuit establishes it.
The target image is independent of address and borrowed inputs. Nonlinear/mixed
relations require separate contracts. Rank zero is a singleton, never an empty
domain. Empty solution sets and dependent input columns are rejected.

## Usage: five sign-extended 7-bit words

```python
from symq.labs.affine_table import (
    affine_target_from_equations, verify_affine_table,
)

# Bit numbers are positions in target_wires, NOT physical circuit wire labels.
equations = [[(1 << (8*j+6)) | (1 << (8*j+7)), 0] for j in range(5)]
space = affine_target_from_equations(40, equations)
assert len(space['columns']) == 35
```

Starting from a version-1 serialized contract, remove `target_values`, set
`kind='symq_affine_hmr_table_contract'`, `schema_version=2`, and
`target_space=space`. Keep all other fields: width, address_wires, target_wires,
clean_wires, borrowed_wires, full table shape, explicit legal_addresses,
bit_order='lsb_first', records='forgotten', outputs='all_retained'.

This complete example checks an identity loader with one proven-zero reset. It
runs without an optional SAT solver; select `backend='sat'` explicitly when
python-sat is installed. For a real loader, replace the source, table and wire map
with independently authenticated inputs, not with this illustrative identity.

```python
# q0 is address, q1..40 are target bits, and q41 is zero-prepared scratch.
source_document = {
    'kind': 'hybrid', 'schema_version': 1, 'data': 41, 'ancillas': 1,
    'ops': [{'kind': 'reset', 'wires': [41], 'slot': None,
             'condition': None, 'source': None, 'value': None}],
}
contract_document = {
    'kind': 'symq_affine_hmr_table_contract', 'schema_version': 2,
    'width': 42, 'address_wires': [0], 'target_wires': list(range(1, 41)),
    'clean_wires': [41], 'borrowed_wires': [],
    'table': [0, 0], 'legal_addresses': [0, 1], 'target_space': space,
    'bit_order': 'lsb_first', 'records': 'forgotten', 'outputs': 'all_retained',
}
result = verify_affine_table(source_document, contract_document, backend='anf')
assert result['status'] == 'equivalent'
assert result['target_dimension'] == 35
assert result['eliminated_events'] == 1
```

The source is the strict hybrid JSON supported by the streaming engine. No importer
may silently discard phase, reset or conditional instructions. A `None` table row
is allowed only at an explicitly illegal address. Legal rows must be complete
in-range integers, including bit39. No certification of padding addresses follows.
The contract hash includes the complete coordinate image, table, layout and domain.

## Resets and independent table construction

The current streaming route in #160 already checks an input-independent measured
value before eliminating a reset. In particular, an actual zero needs no support
branch. The old `anchored_kraus` reference still builds that product. A dedicated
89-zero-reset regression distinguishes the two: original reference becomes
inconclusive at 5000 terms; streaming proves equivalence with peak4 terms.
Never remove a reset just because a caller calls it clean. Input-dependent resets
must be rejected when they leak coherence; deterministic nonzero resets can be
valid if the overall retained-output contract is restored.

The new table-only Shannon construction uses the independently supplied words,
not the emitted candidate. It shares cofactors through the underlying Boolean
algebra. The original row-minterm reference remains selectable for comparison;
neither construction enumerates target states. Address tables remain explicit,
with up to 16 address bits (`affine_table.MAX_ADDRESS_BITS`; a wider well-formed table
is `unsupported`, with `obligation="capacity"`; version-1 contracts keep 12); physical
circuit width remains capped at 256.

The indicator of the admitted addresses is built the same way since 0.3.0: by Shannon
decomposition on the address bits, a half whose words are all admitted or all refused
being a constant. The previous construction, one selector per admitted word, remains
selectable as `domain_style="minterms"` and is the reference of the differential tests
(`tests/test_wide_address_tables.py`). `benchmarks/table_domain.py` measures both on a
synthetic loader family at 6 to 12 address bits, in paired isolated runs; on that family
the reference exhausts the default product budget at 12 bits on ANF where the Shannon
construction concludes. The record is a CI artifact of the affine-target-table workflow,
and says nothing about other loaders.

## Qualification scope

The public synthetic large fixture has 128 physical wires, 40 target bits, rank35,
1363 legal addresses, 89 HMR and 89 proved-zero resets. It is designed to *require*
the target correlation: widening it to 40 arbitrary bits must refute the phase
contract. Its table is generated from a separate integer formula. No private
fixture, external compiler data, actual application loader or score is claimed.

Small cases compare every density matrix unit with an independent rational oracle.
They include affine offsets, singleton targets, scrambled wire maps, borrowed
workspace, contradictory relations, forged types, source mutations, illegal
padding, and both table representations. Large-state claims are symbolic proofs
under the implemented theorem, not exhaustive density simulation of 2^35 states.

```bash
python -m pytest -q tests/test_affine_table.py
python -m benchmarks.affine_table --programs 100 --output evidence/affine-target-table.json
```

The workflow records exact Git commit/tree and source digests. Resource exhaustion
is inconclusive, with the limit reached and the limits of the call
(`resource`, `limit`, `observed`, `hint`, `limits`), missing SAT is unsupported, and malformed contracts raise. Shared
session limits remain in force; node/byte limits that cannot be measured are
refused. Hashes and successful verdicts are not portable proof certificates.
`tests/test_affine_table_independent.py` (audit #164) adds a different generator:
random consistent parity systems (dependent rows, rank-zero images), scrambled roles,
relation-dependent resets/HMR/measurements and mutations, with legal inputs enumerated by
brute force and truth from the explicit-matrix oracle of #157, for both backends and both
table styles. On the wide fixture it proves a reset of a relation constant on the image,
refuses one that crosses words as an irreversible record, and refuses dropping any of the
five sign copies. The audit ran the cohort on 1,000 sources (478 positive) with no
disagreement. These remain synthetic development data.

Independent review and validation of real serialized loaders remain necessary.
