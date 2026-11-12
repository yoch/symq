# Shared wide tables, predicate addresses and actual preparation (research)

`symq.labs.shared_table` compiles a closed version-3 transport to the existing
version-2 affine/HMR proof. The maintained `TableXorContract` retains its
16-bit address and 16-bit target limits. This research path allows up to 256
physical bits/target coordinates, subject to the existing symbolic budgets.

The address domain uses the existing `PredicateValues` closed grammar and its
checked witness. A `SharedTable` describes up to 16 address bits, and
`verify_shared_table` verifies tables of up to **16** address bits since 0.3.0 (0.2.0
raised a `ValueError` above 12, and 0.2.1 returned `unsupported`). The predicate is
evaluated on every address word at once (as bit sets), and the verifier builds the
indicator of the admitted addresses by Shannon decomposition on the address bits instead
of one selector per admitted word. An interval stays a small polynomial; other domains
need not (in ANF, the indicator of "address is not 0" has 2^16 - 1 monomials at 16
bits), and their cost is bounded by the usual budgets. A version-2 contract wider than 16 address bits returns
`status="unsupported"` with `obligation="capacity"`: no verdict, no error.
Targets remain an injective affine image and are **not enumerated**. A witness
proves non-vacuity only. Every admitted address, every affine target parameter,
all borrowed information and every HMR branch must satisfy the existing
all-output anchored Kraus theorem. Records are forgotten; instrument equality
is not claimed. Reset/measurement admissibility and phases remain checked by
the existing engine, with no fallback or weakened theorem.

`SharedTable` encodes each unique truth column once, plus a complete map from
physical target coordinates to columns. Row zero is the least significant bit
of each column integer. Serialized columns are fixed-width lowercase hexadecimal
strings, with exactly `ceil(2**address_bits/4)` digits. Aliases, missing/unknown
fields, duplicate columns, unused columns, invalid mappings and out-of-width
bits are refused. All rows are supplied, including outside-domain values;
those values never widen the admitted domain.

Five eight-bit sign-extended words are represented by 40 physical target bits
with the five equations `bit7=bit6`, giving 35 independent parameters. Rank 40
explicitly requests arbitrary targets; rank zero with offset zero explicitly
requests clean targets. These are different contracts, not interchangeable
optimizations. An image with nonzero offset is also explicit and nonempty.

```python
from symq import Circuit
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs.classical_transcript import Program, digest
from symq.labs.shared_table import (
    SharedTable, prove_shared_table_preparation, verify_shared_table,
)

loader = HybridProgram(3, 1).cx(0, 1).cx(0, 2)
table = SharedTable.from_rows([0, 3], address_bits=1, target_bits=2)
contract = {
    'kind': 'symq_shared_affine_table_contract', 'schema_version': 3,
    'width': 4, 'address_wires': [0], 'target_wires': [1, 2],
    'clean_wires': [3], 'borrowed_wires': [], 'table': table.to_dict(),
    'address_domain': PredicateValues.below(1, 2).to_dict(),
    'target_space': {'kind': 'affine_image', 'offset': 0, 'columns': [3]},
    'bit_order': 'lsb_first', 'records': 'forgotten', 'outputs': 'all_retained',
}
conditional = verify_shared_table(program_to_dict(loader), contract)
assert conditional['status'] == 'equivalent'
assert conditional['shared_columns'] == 1
assert conditional['actual_context_preparation_proved'] is False

# Actual classical preparation, separately pinned and checked at its output cut.
prefix = Circuit(4).cx(1, 2)
prepared = prove_shared_table_preparation(
    prefix, contract, expected_source_sha256=digest(Program.freeze(prefix)),
    initial_constants=((2, 0), (3, 0)),
)
assert prepared['status'] == 'equivalent'
assert prepared['shared_contract_sha256'] == conditional['shared_contract_sha256']
```

The loader and preparation results intentionally remain separate. The latter
proves cut support from the **exact provided classical prefix under its declared
initial domain**, checking the complete address predicate, affine target-image
membership and all clean workspace. It uses GF(2) elimination to generate parity
constraints without enumerating target states. All other inputs remain arbitrary.
It does not prove preparation before that prefix, infer a connection to an
unprovided full file, or accept an old result as proof. Both computations must
run freshly with matching contract identities before a consumer composes them.
No saved receipt is consumed by these entry points.

Proof budgets share an outer deadline through domain compilation, existing
engine execution and cleanup. The default outer deadline is 30 seconds; the
existing affine engine also keeps its default 10-second cap. Pass an explicit
`Budget(max_seconds=...)` for one tighter total bound. Transport JSON is capped
at 2 MB, address width at 16, targets at 256; these simultaneous bounds can
refuse a maximally wide dense encoding. Preparation accepts at most 200,000
materialized classical gates and 256 wires. Symbolic term/product/DAG/clause
limits are those of `verify_affine_table`; there is no claimed process RSS cap.
Exhaustion is inconclusive and never supplies preparation authority. Generic
unsupported budgets are refused by the underlying checker.

An `inconclusive` result names the limit it reached: `resource` (`products`,
`terms`, `seconds`, `Boolean DAG nodes`, `CNF clauses`, ...), `limit`, `observed`,
a `hint` naming the parameter to change, and `limits`, the limits of the call.
For example, a call stopped by `max_products=1000000` reports `resource="products"`,
`limit=1000000` and in `observed` the count when it stopped, which exceeds the limit
by at most one polynomial product (products are counted term pair by term pair), with
the products and peak terms counted so far. Passing a larger `max_products` may let it
conclude, or may not: the count is where the call stopped, not the size of a proof.
A deadline names no single parameter: `max_seconds`, `absolute_deadline` and an
enclosing `VerificationSession` all set one, and the tightest applies.
The fields are described in `symq.labs.resource_report`.

```bash
SYMQ_TEST_REQUIRE=sat python -m pytest -q tests/test_shared_table.py tests/test_affine_table.py tests/test_affine_table_independent.py tests/test_table_xor_predicates.py
```

Original MIT synthetic tests include independent off-diagonal Kraus checks,
40 targets/35 parameters, sign-copy-dependent resets, missing HMR corrections,
incorrectly widened domains, detached shared encodings, explicit preparation
and an unprepared context. Third-party/private loader data are not distributed.
This is a fresh engine decision, not an independent proof certificate or a
claim that a real surrounding application prepares the requested support.
