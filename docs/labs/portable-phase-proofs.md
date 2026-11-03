# Portable LRAT phase proofs: a smaller positive-verdict trust boundary

Research milestone for #167. The existing phase APIs are unchanged. This opt-in
path separates proof generation, a standalone formula-proof kernel, and source
binding. A solver reply or stored `proved` flag is NEVER enough.

## Trust chain, not a claim of complete formal verification

1. Trusted caller supplies the real L/R dyadic programs, sign/HMR dephaser,
   explicit affine coherent support, and a factored phase candidate.
2. The source consumer freezes/validates these inputs, verifies all-output equality
   and dephaser restoration, and extracts the effective signature and phase delta.
   It compiles the aggregate candidate/actual bit mismatch into a shared Boolean
   graph and a deterministic CNF. The query is an actual input unit clause.
3. An untrusted fresh Glucose instance produces DRUP. An untrusted elaborator finds
   ordered clause-id unit-propagation hints and writes standard LRAT additions.
4. A stdlib-only Python kernel checks the pinned formula and every inference.
   A separate source consumer regenerates the CNF and checks the same proof WITHOUT
   a solver, search, or the old `check_factored_phase` replay routine.

The solver, proof logger and hint-search algorithm are removed from the logical
trusted base of a POSITIVE formula decision, conditional on the small checker.
Remaining trust: the checker code/parser/Python, the exact source semantics,
output/restoration checks, support theorem, graph simplifications, CNF encoding,
source identity inputs, runtime/compiler and hardware. Neither this Python kernel
nor those reductions are machine-certified. A formal proof of the code remains
future work. Independent C agreement is corroboration, not formal certification.

A formula proof is portable as DIMACS plus LRAT and can be checked with no SymQ
installation. A source-level proof additionally needs the independently trusted
source programs, support and candidate supplied by the consumer; these objects
are not magically authenticated by an untrusted archive. Reading a bundle's own
hashes back as expected pins is not an independent trust anchor.

## Closed subset and mathematical soundness argument

`lrat_rup.py` supports addition-only positive-hint RUP steps of LRAT. Each new
clause has a strictly increasing positive ID. Starting with the negation of its
literals, every referenced existing clause must be unit or the final conflicting
clause. An inference ending without conflict is rejected. The complete trace must
end with a checked empty clause, with no trailing instructions.

Let F_0 be the original CNF. Inductively, suppose F_0 entails all previously added
clauses. If unit propagation in F_(i-1) AND not(C_i) derives a contradiction, the
soundness of unit propagation gives F_(i-1) entails C_i. Therefore F_0 also entails
C_i. When C_i is empty, F_0 entails false and is unsatisfiable. This is the ordinary
mathematical argument; it is NOT a proof that every line of Python realizes it.

References: [LRAT paper, Cruz-Filipe et al.](https://arxiv.org/abs/1612.02353),
[official PySAT proof API](https://pysathq.github.io/docs/html/api/solvers.html),
[DRAT-trim reference checker](https://github.com/marijnheule/drat-trim).
The LRAT literature already includes Coq/ACL2-certified checkers; adopting an
independently validated build of such a checker is a follow-on, not a reinvention
or a guarantee delivered by this Python prototype.

The grammar rejects RAT-only additions, deletions, extensions, tautological or
duplicate-literal clauses, forward/missing hints, noncanonical integer tokens and
truncated traces. It accepts a stricter subset than general LRAT. RUP can express
resolution refutations, but a producer's arbitrary DRAT trace need not be RUP;
unsupported traces fail closed. The elaborator ignores validated DRUP deletion
lines, retaining a stronger database of already implied clauses. Its output still
must pass the independent checker. No hidden incremental assumptions are used.

## Source-level theorem and API

The intended source claim is exactly the already documented factored-phase theorem:
L and R have equal retained-output channels AFTER the actual dephaser on the
explicit support, with classical records forgotten. Effective signature feedback
is included. This does not prove preparation of that support in a larger circuit,
coherently controlled substitution, observed instruments, general interference
or floating-point approximation. A wrong candidate is not channel inequivalence.

Public RESEARCH functions in `symq.labs.phase_proof_bundle`:
- `describe_factored_obligation`: creates independent source/candidate/CNF identities;
  `ready` and `proved=False` mean only that preparation succeeded.
- `export_factored_proof`: generates an LRAT witness, then independently consumes
  it on detached real sources; emits a bundle only after final time checks.
- `check_factored_proof`: accepts expected source/candidate hashes separately,
  rebuilds all obligations and byte-identical CNF, and validates LRAT without SAT.

The closed version1 bundle contains source/candidate/CNF/LRAT SHA-256 values,
DIMACS/LRAT text, theorem and encoder identity. A correct proof of an unrelated
trivial contradiction is explicitly tested and refused. Hashes identify bytes;
the inference trace proves UNSAT. No `status` field in a producer's record is
accepted as proof authority.

`proved` requires both the fresh semantic reduction and the trace check;
`invalid` rejects a malformed/stale source-bound bundle; `not_proved` means the
candidate/export could not establish the claim; `inconclusive` means budget/size
exhaustion; `unsupported` means the generation solver is unavailable. A source
consumer needs no solver. Invalid API types may raise immediately. Revoked runs
retain neither a successful bundle nor successful proof hashes/counters.

## Resource and serialization boundaries

All source calls share the original Guard/VerificationSession deadline, including
preparation, extraction, proof conversion, independent checking and cleanup. The
standalone kernel enforces explicit bytes, clauses, steps, variables, visited
literals/tokens and wall time. Source `max_terms` also caps tokenized proof input.
Unsupported inherited node/byte limits are refused; explicit text bounds are not
an OS RSS or hard preemption guarantee. PySAT may allocate its proof before the
Python conversion cap is checked. No unlimited hostile-input service is claimed.

Transport the bundle as JSON data, never pickle. If accepting raw JSON bytes,
apply a bounded parser with duplicate-key rejection before supplying the exact
dict; this prototype's public consumer receives an already parsed object. The
proof kernel itself receives bounded exact ASCII strings.

## Reproduction and qualification

From an installed checkout with dev dependencies:

```bash
python -m pytest -q tests/test_lrat_rup.py tests/test_lrat_export.py tests/test_phase_proof_bundle.py
python -m benchmarks.portable_phase_proofs --output-dir evidence
python -I -S evidence/lrat_rup.py evidence/php.cnf evidence/php.lrat --expected-cnf-sha256 SHA256_FROM_TRUSTED_FORMULA
```

The placeholder above must be replaced by the hash of a trusted formula, not a
value taken from an adversarial proof. The workflow runs the actual completed
command, not this placeholder. It also checks standard emitted files with the
independent C `lrat-check` pinned at drat-trim commit
2e3b2dc0ecf938addbd779d42877b6ed69d9a985, then uninstalls python-sat and verifies an
actual source bundle again. That dependency is CI-only; no external code is copied
into this package or trusted as the runtime kernel.

The development campaign covers all256 h=(ab,bc)->Z/4 source functions with exact
small-channel oracles, retains every emitted proof bundle, and checks a nontrivial
pigeonhole refutation separately. The kernel's tiny-CNF test covers all522 clause
subsets through2 variables against brute force and independent binary resolution.
Mutations include false UNSAT/model/proof, altered sources and contracts, mismatched
CNF/pins, invalid syntax, missing hints and expiration after an inner success.
No untouched holdout, real compiled KMB loader, universal speedup, general full-LRAT
compatibility or complete formal verification is claimed. Final results must be
read from the exact published-head CI and artifacts, not inferred from this guide.

## Next proof obligations before promotion

Independently audit the new kernel and source binding. Check against a pinned
formally verified LRAT implementation, formalize the parser/inference kernel or
adopt its verified replacement, then formalize the source reduction and phase
fibre theorem. Reuse the same interface for other SAT obligations only after
case-specific source binding is designed. This first export route is explicit
and additive; it does not silently change any existing `proved` label.
