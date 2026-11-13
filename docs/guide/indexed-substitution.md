# Indexed classical substitution plans (research)

`symq.labs.indexed_substitution` connects the owned strict KMX/KMB index to the
existing local rewrite checkers. It never materializes the complete prefix.
This first composition accepts complete sources containing only unconditional
X/CX/CCX, and requires extraction from operation zero. Unsupported instructions
anywhere in the complete source refuse the build, including outside the window.

The result is a conditional plan for replacing one **complete window** in the
pinned source. `complete_candidate` and `global_cost` are always null. The
reduced circuit is proof support only; it is not an emitted complete candidate
and its operation count is not a global economic measurement.

## Exact composition rule

Write the complete source as `F ; B ; S`, with window `[a,b)` in global
zero-based semantic-operation coordinates. Let `P` be the supplied conjunction
of initial constants and `initial_assumption`, and let `Q` combine
`cut_assumption` with the requested zero conditions. No input variable is
implicitly zero. A predecessor `-1` means an arbitrary input under `P`.

1. Re-extract and verify **all** of `B` from the owned complete source.
2. Extract and verify the origin cone `C` observing every variable of `Q`,
   including clean-wire requirements. The extraction lemma establishes
   `C(x)|obs = F(x)|obs` for every input. It makes no claim about other outputs.
3. Form a sorted injective common support containing every wire of `C`, `B`,
   `R`, the obligations, **and every variable of P**. A variable of `P` absent
   from `C` remains an identity **initial** input in the reduced circuit. It
   is not interpreted as that wire's actual value at the global cut. No initial
   correlation is projected away. Initial constants outside the cone also stay.
4. On `C ; B`, the existing checker proves non-vacuity of `P`, `P => Q(C(x))`,
   all-output equality of `B` and `R` for **every cut state satisfying Q**, and
   the separate restoration of clean and borrowed wires by both blocks.
5. By extraction, `P => Q(F(x))`. The universal local lemma therefore applies
   to the actual state `F(x)`, even when its unobserved wires differ from the
   cone outputs. Every wire outside the common support is untouched by both
   blocks. Thus all outputs of `F ; B ; S` and `F ; R ; S` agree under `P`.

This is a classical full-output theorem under a **declared initial domain**.
It proves neither external preparation nor a quantum channel, phase correction,
measurement instrument, allocation policy or score. The trust base includes
the strict parser, versioned dependency extraction, remapping, Boolean encoding
and SAT solver. The receipt is replayable, not an independently checked UNSAT
certificate. For a contextual contract whose `Q` has no variables, one additional
window-wire observation retains the existing nonempty-observation cone grammar.
The constant predicate itself is still checked; an empty domain is refused.

### Unconditional local proof

When **every** contract field is empty or absent, complete-window equality on
all local inputs is sufficient for any prefix and suffix. The checker still
builds and validates the complete pinned source index, re-extracts and verifies
the exact window, and maps every window and replacement wire. It then proves
the local all-output equality using the existing deterministic backend advisor
without querying a prefix cone. Window, source, support, replacement and time
limits still apply. No prefix-cone limit is consumed by this path.

The symbolic engines run under `CompositionLimits.max_symbolic_terms` and
`max_symbolic_nodes` (250,000 each by default; the pure-Python ZDD measured about
350 bytes per node, so roughly 85 MiB): exceeding either is `inconclusive` and
issues no plan. A SAT local proof keeps the time limit only.

Such a receipt has `origin_cone=null`, no observed cut wires,
`reduced.scope="complete_window_only_unconditional"` and the top-level theorem
`classical_full_source_window_equality_on_every_input`. Its local proof records
the actual engine and theorem; it still authorizes only the pinned global
window and replacement map. Its dependencies say `sat: "not_used"` when a
symbolic engine proved it: python-sat is then not pinned, and changing it does
not invalidate the receipt. SAT proofs record `sat: "pinned"` with the
python-sat version and module hashes. The receipt `schema_version` stays 1:
these labs receipts carry no API promise, and replay compares them whole. Any initial constant, predicate (even a constant
true or false predicate), clean-wire requirement or restoration requirement
keeps the contextual path and all its obligations. This is a bounded local
optimization, not a performance claim for production circuits.

Requiring `prefix_start_op=0` is deliberate. Intermediate boundary facts need
their own pinned prefix proofs before this rule can accept them.

## Request and independent pins

Requests have a closed schema, version 1, using the existing circuit and
substitution-contract grammars. Pins must come from the consumer independently
of an untrusted received report. Source identity is SHA-256 of **complete file
bytes**; request identity is `canonical_sha256(request)`, independent of JSON
whitespace. Changing any coordinate, mapping, predicate, replacement or
obligation changes the request identity.

```python
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from symq import Circuit
from symq.hashing import canonical_sha256
from symq.labs.indexed_substitution import (
    prove_indexed_substitution, replay_indexed_substitution,
)
from symq.resources import Budget

# Original MIT-authored synthetic development example.
with TemporaryDirectory() as directory:
    source = Path(directory) / 'indexed-example.kmx'
    with source.open('xb') as stream:
        stream.write(b'CX q0 q2\nX q5\nX q0\nCX q2 q3\nCCX q1 q3 q5\n')
    source_pin = hashlib.sha256(source.read_bytes()).hexdigest()
    request = {
        'kind': 'symq_indexed_classical_substitution', 'schema_version': 1,
        'source_file_sha256': source_pin, 'prefix_start_op': 0, 'op_span': [3, 4],
        'replacement': Circuit(1).to_dict(), 'replacement_wires': [3],
        'contract': {
            'initial_assumption': {'kind': 'eq',
                'left': {'kind': 'var', 'name': 'x.0'},
                'right': {'kind': 'var', 'name': 'x.2'}},
            'clean_at_cut': [2],
        },
    }
    pins = dict(expected_source_sha256=source_pin,
                expected_request_sha256=canonical_sha256(request))
    report = prove_indexed_substitution(source, request, **pins, budget=Budget(max_seconds=10))
    assert report['status'] == 'equivalent'
    assert report['applicable_plan']['global_op_span'] == [3, 4]
    assert report['reduced']['local_span'] == [1, 2]
    fresh = replay_indexed_substitution(source, request, report, **pins,
                                       budget=Budget(max_seconds=10))
    assert fresh['applicable_plan'] is not None
    assert fresh['complete_candidate'] is fresh['global_cost'] is None
```

`replacement_wires` maps **every** local replacement wire into the existing
source width. No new physical ancilla is allocated. Initial and cut predicates
use canonical **global** `x.<wire>` and `u.<wire>` names, respectively. A caller
can supply JSON bytes; duplicate keys, unknown fields and nonfinite values are
rejected. The request is copied before extracting or proving anything.

## Receipts, failures and budgets

Receipts separate global source identity/coordinates, complete window,
origin cone, common support, initial hypotheses, required observations,
renamed conditions actually used, proved obligations and local proof data.
Local witnesses retain `witness_scope="reduced_obligation_only"` and
`global_counterexample=null`. A failed sufficient local lemma is `not_proved`,
not a claim of global inequivalence. `precondition_failed` includes empty
domains and unestablished cut conditions; the named obligations distinguish
them. No failed or inconclusive outcome carries an applicable plan.

`check_indexed_substitution` reuses a builder-issued in-process index. It
reverifies every required extraction receipt against the private snapshot. Deleting or
editing the original path cannot change that snapshot; the plan continues to
designate the original complete bytes. Before any later application, portable
`replay_indexed_substitution` rebuilds from the supplied complete source,
reconstructs the required extractions and remapping, and reruns **all** local proof obligations.
Serialized handles, stored flags, a hash of the reduced circuit or an old
successful site cannot authorize a new use.

A decisive replay strictly compares the whole receipt, including installed
SymQ Python-source hashes, Python/SQLite/python-sat versions and SAT module/
binary hashes. Changed dependencies require a newly generated proof receipt.
Hashes detect drift, not hostile code executing in the verifier process.
Missing SAT for a contextual proof is `unsupported`; exhausted work/time limits are `inconclusive`.
Malformed inputs, pins or decisive receipt mismatches raise errors. A replay
that cannot finish returns no plan, even if the saved receipt was successful.

Defaults: 2 MB request, 20,000 replacement operations, 256 common support wires,
4,096 nodes per predicate. The existing independent index and query limits
also apply. The default complete call is 30 seconds; explicit `Budget()` is
unlimited. Build/copy/hash, queries, verification, dependencies, SAT, remapping,
receipt comparison and cleanup share **one deadline**. No inner successful
proof survives an expired outer deadline. Generic term/node/byte budgets are
refused here; these are cooperative time/work bounds, not an RSS guarantee.

```bash
SYMQ_TEST_REQUIRE=sat python -m pytest -q tests/test_indexed_substitution.py tests/test_kmx_source_index.py tests/test_contextual_substitution.py tests/test_rewrite_initial_assumption.py
```

Tests exhaustively interpret complete before/after small circuits with a
separate scalar interpreter. Adversarial cases cover lost initial correlations
outside the cone, empty domains, a preserved precondition but changed unrelated
output, dirty entry, restoration, stale contexts/coordinates/mappings/contracts,
dependency and receipt mutants, whole-source unsupported gates and expiry after
a successful inner proof. The corpus is synthetic development data under MIT;
there is no production-size qualification or comparative performance claim.

Stage-separated synthetic development qualification (new output file):

```bash
python -m benchmarks.indexed_substitution --output /tmp/indexed-composition.json --repetitions 3
```

The harness records copy/hash/parse/index construction, cold and repeated
extraction plus fresh proof, complete rebuild/replay, CPU/wall time, cumulative
peak RSS, disk and logical source-read counters. It retains refusals/failures,
uses a seeded randomized serial schedule and does not claim real scaling.
Contextual and unconditional cases use 100 and 10,000 prefix operations; an
additional unconditional case uses 20,100. The latter exceeds the default cone
operation limit while keeping a two-operation window. Its receipt must contain
no origin cone, and its window query work remains explicitly reported. All
cases are synthetic development fixtures, not an untouched holdout corpus.
