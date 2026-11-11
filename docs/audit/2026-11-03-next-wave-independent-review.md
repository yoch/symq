# Independent review of the 3 Nov 2026 next wave (#183, #184, #185)

This is the independent review of the three next-wave PRs, done against the brief
`next-wave-external-independent-review.md` proposed in Draft #181 (that brief was never merged
and is not in this tree). Nothing was merged. `main`
was not modified. No release was made and no interface was promoted.

## Status of this report

This page records the review result. **It does not authorize any merge.** Every integration
needs a separate maintainer decision.

## 1. Revalidated references

Every SHA below was revalidated with `git ls-remote` at the start of the review and again
before each push. Local checkouts were used only at those exact SHAs.

| Ref | SHA | Base | Exact-head CI (before review) |
| --- | --- | --- | --- |
| `main` | `766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc` | — | — |
| #183 | `1552cc0783e6de8341d026429f07d0582edf27de` | `766d3df` | CI run 41701394472: 14/14 |
| #184 | `11a3aeeedd4f848bffa6a83a4d46edbaccc4d754` | `766d3df` | CI run 41701691559: 14/14 |
| #185 | `332828316ab44c56a804be578e176cf351561d34` | `766d3df` | CI run 41702145418: 14/14; Qiskit pilot run 41702145314 |

The `head_sha` of every run listed was checked through the Actions API. On #184's head, the
Python 3.10 job ran 6305 tests, passed them all, and skipped 210. All 210 skips are optional
external packages: CUDD/`dd`, PolyBoRi, QCEC, hatchling, one empty parameter set, and one case
reserved for the pure job. No test of the new modules was skipped in a job that requires them.

The pure-python job requires `symq.sat.available()`, so python-sat is installed there and the
SAT tests of #184 run. The Qiskit tests of #185 are skipped in the main CI with
`importorskip("qiskit")`; this is an optional skip, covered by the dedicated workflow.

When the review started, none of the three PRs had review threads. The owner had left
"independent review notes" on #183 (comment 6613616071) and #184 (comment 6613621339). Both note
that work on the input runs before the budget is polled.

Cross-cutting checks on the three diffs (`git diff 766d3df..HEAD`):

- No mention of a private repository, no private fixture, and no local path.
- No change under `src/` outside `src/symq/labs/`. #185 changes nothing under `src/` at all.
- No change to `pyproject.toml` and no new runtime dependency. Qiskit is installed only by the
  dedicated workflow.
- Nothing outside the new files imports `reset_support`, `miter_cnf` or `miter_proof_bundle`.
  No default engine and no stable API changes.

## 2. Method

Each PR was reviewed by a separate agent that wrote none of the code. Each agent wrote its own
oracle, outside SymQ's engines. I then reproduced every critical claim with a second oracle of
my own before any fix was written.

Findings are classified as follows:

- **confirmed (reproduced by me)**: I reproduced the auditor's finding on the exact head.
- **confirmed (auditor)**: measured by the auditor and not re-measured by me. This is mostly
  timing.
- **known limitation**: by design and documented.

Fixes are on isolated branches cut from the exact PR heads. They were proposed as Draft PRs
against the PR branches, not against `main`. Each regression test was run on the original head
to show that it fails there.

## 3. B — #183: coherent affine-support clean resets

### Theorem (re-derived; sound)

The prefix grammar is X/CX/CCX/MCX/SWAP/CSWAP plus Z/CZ/CCZ/NEG, all unconditioned. Each such
gate is monomial: U|x⟩ = s(x)|π(x)⟩.

Suppose bit q of π(c ⊕ Bu) is 0 for every u, where the columns of B are independent over
GF(2). Then U maps span{|c ⊕ Bu⟩} ⊗ (any reference system) into the subspace where q = 0, and a
reset of q is the identity there. This holds for off-diagonal terms and for coherence with a
reference system.

Deleting several clean resets is sound, because each of them acts as the identity on the
states that actually reach it.

The other parts were also checked and are correct:

- The ANF update rules: x² = x, CSWAP Δ = c(a ⊕ b), and the MCX product.
- The witness. For f ≠ 0, set exactly the variables of a minimum-degree monomial m. Then m is
  the only monomial of f that is a subset of m, so f evaluates to 1.
- The pivot rank test in `AffineSupport.validate`.

### Independent oracles

| Oracle | Cases | Disagreements |
| --- | --- | --- |
| Auditor: exact-fraction density/Kraus, outside SymQ. Exhaustive width 3: 58-operation alphabet, all length-1/2 circuits × all 456/28 supports. | 503,136 checks; 350,147 matrix units | 0 |
| Auditor: random circuits up to width 5, with entangled-reference checks | 9,000 circuits; 11,109 units; 566 reference checks | 0 |
| Auditor: Bennett compute/copy/uncompute; 718 gate-deletion mutants | 3,000 circuits; 110,764 units | 0 (every mutant caught) |
| Mine: matrix-unit channel oracle comparing source and candidate on every \|x⟩⟨y\| of the span, plus witness replay | 12,000 on `1552cc0`; 7,000 on the fixed head | 0 |

No unsound `proved_clean` result was found, and no non-clean reset was accepted.

### Findings

| ID | Location (`1552cc0`) | Class | Severity | Description |
| --- | --- | --- | --- | --- |
| B-F1 | `reset_support.py:160,290-291` | confirmed (reproduced by me) | medium | If `ops` is not an exact `list` (a tuple, a generator, or a list subclass assigned after construction), the `max_operations` preflight is skipped. The input is then copied, passed through `asdict` and hashed. An over-cap source therefore receives a `source_sha256`, which the brief forbids. Reproducer: `p.ops = tuple(...)` with `max_operations=5` returns `inconclusive` with a non-null `source_sha256`. The auditor measured a 300k-element tuple at 7 s and 181 MB. **No candidate is ever emitted**, so this is not a false proof. |
| B-F2 | `:192` against `:218/222` | confirmed (reproduced by me) | medium-low | A `str` subclass used as `kind` serializes as `"x"` but compares equal to `"reset"`. `HOp(Alias("x"), (1,))` then yields `proved_clean` with candidate `[]`, and its `source_sha256` is the same as that of the genuine program `[x(1)]`. The fingerprint names a different program from the one that was analyzed. This requires hostile objects in the same process. |
| B-F3 | `:181-185` | confirmed (reproduced by me) | low | A `max_nodes` or `max_bytes` limit inherited from a `VerificationSession` is silently ignored. Passing the same limit explicitly is refused. |
| B-F4 | `:171-205` | confirmed (auditor), reproduced by me after the fix | low | This is the owner's note. Snapshot, validation, `asdict` and hashing run before the `Guard` exists. The auditor measured 23.9 s and 672 MB at the default operations cap with `max_seconds=1e-6`, and validation runs 3 to 4 times along the build → prove → candidate path. |
| B-I1 | design | known limitation | — | The support is declared by the caller; it is not a reachability claim. With a rank-0 support, `cx(0,1); reset(1)` is `proved_clean`, yet the candidate is wrong for data input \|1⟩. |
| B-I2 | `tests/test_reset_support.py` | known limitation (coverage) | — | The PR's random test uses only offset 0 with full-rank identity columns. It never samples MCX with more than 2 controls, CSWAP, CCZ or NEG. The exhaustive run above covers them. |
| B-I3 | docs | known limitation | — | The 40-wire, rank-35, 89-reset fixture is correctly labelled synthetic and not a loader. It is not new relative to `affine_table`: `tests/test_affine_table.py:49` has the same shape. Wire 39 is never touched. |

**Fixes:** [yoch/symq#188](https://github.com/yoch/symq/pull/188), base `1552cc0`, head
`9c57ad4ca275521c4f1aa9f96568ccd9fa62dd56`.

- B-F1: both entry points require an exact `list` before any copy.
- B-F2: `HybridProgram.validate` (in `symq.experimental.hybrid`) now requires `kind` to be an
  exact built-in `str`, so every consumer of the shared contract is protected, not only this
  module. This is the only change outside `symq.labs`, and it only refuses `str` subclasses.
- B-F3: a node or byte limit on the effective guard budget is refused.
- B-F4: parameters and budgets are validated and the guard is created before the input is
  touched. An already expired deadline returns `inconclusive` with null fingerprints in about
  0.1 ms. Both entry points share one frozen snapshot, so validation runs once.

There are four regression tests. Each one fails on `1552cc0`; all 15 tests in the file pass on
the fixed head. The full pure-Python suite on the first fixed head, `345e226`, gave 5293 passed
and 231 skipped.

**Remaining limits:**

- The snapshot itself cannot be interrupted. With 100,000 MCX operations on 40 wires and a 50 ms
  budget, the call takes about 1.5 s and then returns `inconclusive`.
- There is no memory bound on the process.
- `source_sha256` identifies serialized values, not authenticated objects.
- The result is not a portable certificate.

## 4. C — #184: source-bound SAT miter, CNF and positive-hint LRAT

### Obligations

| # | Obligation | Result |
| --- | --- | --- |
| 1 | The miter translation is exact. | The auditor checked 29,000 random miters: widths 1–7, every combination of contract features, 467,430 per-input checks. Normalized and raw CNF were each run through MiniSat22 with unit assumptions and compared against brute-force evaluation: **0 mismatches**. My own check (own DPLL and own evaluator) did 600 miters on all inputs, with exact projection. |
| 2 | Normalization preserves satisfiability. | Normalization changed the clause list in 15,585 miters (duplicate literals and tautologies) with 0 mismatches. The proof is therefore made against the normalized formula, not the solver's internal one. |
| 3 | A proof is accepted only on the rebuilt formula that the source pins. | 45 tampering cases. Only the following were accepted: the baselines; a dropped first step that no later hint cites (still a valid proof); a CRLF variant with its own recomputed hash; and a non-`str` label object (C-F2, now refused). Swapped circuits, a different equivalent source, a changed contract or domain, a reordered `observed_outputs`, encoder drift, another formula's proof, and hint or step edits were all refused. |
| 4 | Every kind of tampering fails. | See obligation 3. |
| 5 | Timeouts, limits or an unavailable solver never give a positive. | Step, visit and time limits give `inconclusive`. The producer returns `unsupported` when python-sat is missing. Glucose overruns its deadline (C-F4) but still returns `inconclusive`. |

**Second checker.** All 216 producer proofs in my random cohort were also accepted by a
positive-hint RUP checker I wrote separately from `lrat_rup`. The auditor ran the Lean 4.19
`lratCheckerSound` path, which accepted 6 of 6 exported proofs and rejected one proof with a
hint removed.

**Consumer without PySAT.** The auditor produced 103 bundles in Python 3.10 with python-sat,
then replayed them in Python 3.13 without python-sat. All replayed as `proved`, and neither
`pysat` nor `lrat_export` was imported.

### Trust base

| Role | Components |
| --- | --- |
| Trusted | `Circuit`/`Gate` validation; `symq.sat.encoding` (Encoder, `encode_circuit`); `build_miter`; the normalization loop (`miter_cnf.py:136-152`); canonical JSON and hashlib; the `lrat_rup` kernel, which is reviewed and tested but not formally verified; CPython |
| Checked by the consumer | the closed bundle schema; the source SHA against the externally supplied pin; the rebuilt CNF bytes and their SHA; the LRAT bytes and their SHA; every RUP step and the empty clause; byte, step, visit and time limits |
| Untrusted | Glucose4; the DRUP→LRAT elaborator; the content of the bundle; where the caller's pin comes from |

UNSAT of the CNF does not prove that the encoder is correct. Global equivalence under a contract
is neither the local cut theorem nor a channel theorem, and the PR's docs say so.

### Findings

| ID | Location (`11a3aee`) | Class | Severity | Description |
| --- | --- | --- | --- | --- |
| C-F1 | `tests/test_miter_proof_bundle.py:190-196`, `miter-proof-c1.md:73-75` | confirmed (reproduced by me) | medium (test evidence) | The "mutated prefix" negative adds `x(1)` to the left circuit only. That pair is `not_proved` with or without the CCX, so the test does not exercise the contextual gate. The code was correct; the evidence was vacuous. Reproducer, under domain `q1=0`: `x(1)` on the left only, with no CCX, still gives `not_proved`. `x(1)` on both sides gives `not_proved` with the CCX and `proved` without it. |
| C-F2 | `miter_proof_bundle.py:104` | confirmed (reproduced by me; the regression fails on the head) | low | `kind` and `theorem` were compared with `!=` only. An object whose `__ne__` returns False was accepted and the bundle came back `proved`. JSON cannot produce such an object, and the CNF, proof and SHA pins were still checked in full. |
| C-F3 | `miter_cnf.py:120-128` | confirmed (auditor); expired-deadline path reproduced by me | low | This is the owner's note. An expired deadline is refused *before* `build_miter`, but a deadline that expires during encoding, and the size caps, are only checked afterwards. The auditor measured a 400k-gate CCX circuit with `max_variables=10` and a 0.05 s budget at 0.95 s and 175 MB. It is never positive. |
| C-F4 | `lrat_export` (main code exercised by the PR) | confirmed (auditor) | low | The Glucose interrupt arrives late when proof logging is on: 10 s → 23.2 s, 2 s → 3.9 s. The result is `inconclusive`. |
| C-F5 | entry points | confirmed (auditor) | low | Some bad contracts raise exceptions instead of returning a status: an empty observation, a width mismatch, a `Budget` with `max_bytes`, or an `assumption`. None of them gives a positive. |
| C-I1 | source document | known limitation | — | The source pin includes no encoder version. A change of encoder makes old bundles fail closed, but the same `source_sha256` would then name a different CNF. The "independent" pin can only be computed by the same trusted exporter. |
| C-I2 | evidence | known limitation | — | The elaborator's 20M visit limit runs out at about 1.5k clauses (width 10, 128 gates). The largest proof is 706 clauses, 169 KB of LRAT, 395 steps; it took 1.8 s to produce and 0.047 s to consume. |

**Fixes:** [yoch/symq#190](https://github.com/yoch/symq/pull/190), base `11a3aee`, head
`f4e014af1bb438223136593ea8c7bd67a66038fd`.

- C-F1: the X is placed on the common prefix of both sides, so the pair differs from the proved
  pair only by that shared X. The one-sided case is kept and labelled as vacuous.
- C-F2: `kind` and `theorem` must be exact `str`. The regression test fails on `11a3aee`.
- The owner's requested qualification for C-F3 is added: `build_miter` is trapped under an
  expired deadline; the formula is exported exactly at the variable and clause caps and refused
  one below; the solver-free consumer then reports `inconclusive`.
- Naming and the C0/C1 evidence pages are corrected.

**C-F3 and C-F4 are documented and quantified, not fixed.** Enforcing the caps during encoding
would mean threading limits through `Encoder`, which does not belong in an audit fix.

### Formalization recommendations

1. Put an encoder and normalization version string in the source document.
2. Add a standalone fingerprint function, so that a consumer can pin from a trusted record
   without rebuilding the CNF.
3. C2: define the Tseitin miter in Lean from the canonical source JSON, and prove that UNSAT
   implies equivalence on the restricted domain. The checker side is already covered by the
   Lean path.
4. Enforce the caps and the deadline during encoding, and run the producer in a process that
   can be killed.

## 5. A — #185: Qiskit 2.6.1 transpiler pilot

### Provenance and licences

- **Qiskit 2.6.1.** The PyPI wheel was uploaded on 22 Oct 2026. Apache-2.0, "Copyright 2017 IBM
  and its contributors".
- **Veri-Q `adder.py`** at `9be1083`: MIT, "Copyright (c) 2026 Veri-Q". The auditor transcribed
  it independently and the transcription matches the generator byte for byte for n = 1–4.
- **qsyn `ab+ac.qasm`** at `b77187c`: Apache-2.0. The raw SHA and the git blob match the
  evidence page. Upstream has no NOTICE file.

### Reproduction

- I ran a fresh `transpile` at `optimization_level=0` with basis `x,cx,ccx`. It reproduces both
  digests, `312b1320…5849` and `3269ab93…2e4b`. Each case has 7 gates, global phase 0 and no
  layout.
- The qubit order is the same in `find_bit`, in the exported QASM and in `parse_qasm`.
- The candidate that is actually emitted, `report["candidate"]`, equals the expected splice and
  is basis-equal on all inputs. Qiskit `Operator` matrices are exactly equal, including global
  phase.
- Bad substitutions are refused, including the qubit-order mistakes `cx(0,2)`, `cx(2,1)` and
  `ccx(0,2,1)`; brute force confirms that each one really differs.
- Bad domains are refused six different ways.
- Eleven kinds of report forgery are refused with `ReceiptMismatch` or `ValueError`.
- A fuzz of 4,200 random 5-wire trials gave 254 `equivalent` results and 0 unsound ones.
- The wheel contains no Qiskit, `benchmarks/` or `tests/`; Qiskit is not in `Requires-Dist`.
- The sdist and wheel tests pass both with and without Qiskit.

### Timing (15 repetitions × 2 cases; medians)

| ms | CI run 41701010947 (`b01ab4d`) | CI run 41702145314 (head) | Auditor's local run |
| --- | --- | --- | --- |
| Wall time including Python startup | 536.9 / 538.0 | 549.4 / 555.4 | 377.9 / 390.1 |
| In-process total | 335.2 / 336.2 | 342.0 / 344.6 | 215.0 / 218.4 |
| Qiskit import + transpile + QASM export/parse | 324.3 / 324.9 | 331.0 / 333.1 | 206.3 / 209.2 |
| SAT proof | 8.76 / 8.90 | 8.81 / 9.09 | 7.10 / 7.29 |
| Replay | 1.63 / 1.67 | 1.64 / 1.68 | 1.31 / 1.30 |
| Peak RSS (KiB, whole process) | 114,640 / 114,760 | 114,580 / 114,776 | 109,472 / 109,440 |

- The doc's table matches the raw rows to the digit. The digest of artifact 13263531451 was
  checked.
- Interpreter startup plus imports plus spawn adds about 200 ms on top of the in-process time.
  The import-and-transpile row is dominated by `import qiskit`, about 200 ms locally.
- No speedup claim is made, and none could be.

### Findings

| ID | Location (`3328283`) | Class | Severity | Description |
| --- | --- | --- | --- | --- |
| A-F1 | `tests/test_qiskit_transpiler_pilot.py:78-82`, workflow `:30-33` | confirmed (reproduced by me) | medium | The digests `312b1320…` and `3269ab93…` appear nowhere in the tree. The "deterministic" test compares two runs of the same process, so a changed lowering still passes; the auditor showed this with a pytest plugin. |
| A-F2 | `tests/test_public_compiler_rewrite.py:47-58` | confirmed (reproduced by me) | medium — **provenance** | Apache-2.0 qsyn material ships in the sdist with only a URL to the licence. Apache §4(a) requires a copy of the licence. Under the brief this is a provenance error that **blocks integration until it is fixed**. |
| A-F3 | workflow | confirmed (auditor) | low | `SYMQ_TEST_REQUIRE=sat` is not set: without python-sat the pytest step goes green with 2 skips, and only the benchmark step then fails. |
| A-F4 | workflow `paths:` | confirmed (reproduced by me) | low | The path filter leaves out `benchmarks/qiskit_rewrite_benchmark.py`, `qasm.py`, `sat/**`, `rewrite*.py` and `pyproject.toml`. |
| A-F5 | `tests/test_public_compiler_rewrite.py:7` | confirmed (reproduced by me) | low | A docstring points to a missing page, `compiler-handoff-pilot.md`. |
| A-F6/F7/F8 | timing doc | confirmed (auditor) | low | The "Compiler + parser" row is mostly `import qiskit`. The "randomized paired" order is not counterbalanced (11 of 15) and has no baseline arm. The raw rows record no CPU or SymQ SHA. |
| A-F9 | `benchmarks/qiskit_transpiler_pilot.py:42-45` | confirmed (reproduced by me) | info — **utility** | A fresh `transpile` already finds both rewrites: `cx(1,2)` at `optimization_level=2` and `ccx(0,1,2)` at level 1. They are not optimizations that the compiler misses. |
| A-F12 | design | known limitation | — | Replay re-proves the request embedded in a report; it does not tie it back to the pinned QASM. A report built over another source with the same block replays as `reverified`. |
| A-F11 | `rewrite_prepare.py:150` (main) | confirmed (auditor), pre-existing | info | Unsorted `initial_constants` make `prepare` raise a misleading "did not round-trip" error. It fails closed. |

**Fixes:** [yoch/symq#189](https://github.com/yoch/symq/pull/189), base `3328283`, head
`c31f8ac5a35165d9d3b5c02039936077a0208cc9`.

- The QASM digests and gate streams are pinned in the test (checked even without python-sat)
  and again in the workflow.
- The emitted candidate is checked, a forged-candidate replay is added, and the qubit-order
  mistakes are added as negatives.
- The workflow sets `SYMQ_TEST_REQUIRE=sat`, and its path filter is widened.
- `benchmarks/corpus/qsyn/{LICENSE-APACHE-2.0, NOTICE.txt}` are added, with the upstream
  copyright line verbatim.
- The docstring pointer, the timing-doc wording, the "its contributors" attribution and the
  stale "not yet verified" claims are corrected.
- The pilot page now says that Qiskit already finds both rewrites.

With the auditor's alternative-lowering plugin, the head's tests pass and the fixed tests fail on
the digest.

### Usefulness of the pilot

The handoff and proof path works end to end on real compiler output. But the corpus is two
closely related development cases, plus two public seeds. Both one-gate rewrites are already
within Qiskit's own optimizer. There is no holdout, no baseline arm on the same theorem, and no
binding between a report and the QASM at the point of consumption.

#180's stopping rule therefore applies. This is a reproducible, mostly negative utility study,
and does not justify an API.

**Conditions before any maintained API:**

1. An untouched holdout family.
2. Rewrites that Qiskit does not find at level ≥ 1 or 2.
3. A baseline arm on the same theorem, for example QCEC or SAT/AIG.
4. Binding between a report and the source digest at the point of consumption.
5. Machine identity and a SymQ SHA in the raw rows, and a counterbalanced order.
6. CLI checks against the installed wheel and the extracted sdist.

## 6. Coverage and performance

- **#183.** The PR's tests cover refusals, mutation, the cap and the 40/35/89 fixture. The random
  test is narrow (B-I2); the exhaustive and Bennett cohorts above close that gap. The reported
  performance is microseconds on the fixture. The worst case at the cap is set by the snapshot,
  about 1.5–24 s and up to hundreds of MB, and is documented.
- **#184.** 18 tests, 20 after the fix. Performance comes from the auditor's measurements: on
  random cases the producer took 2 ms and the consumer 0.3 ms (medians). The consumer stays
  under 50 ms on the largest proof. The producer is limited in practice by elaboration visits.
- **#185.** There are 29 tests with Qiskit and 26 without. The timing doc above stays
  descriptive, with no comparative claim.

## 7. Integration matrix

| PR | Verdict on the reviewed head | After its fix PR is folded in | Conditions |
| --- | --- | --- | --- |
| #183 | **NEEDS_FIX** (B-F1–F4) | **MERGE_LABS_ONLY** | Fold #188 in, with green exact-head CI. Limits: the restricted monomial grammar; the caller-declared span only; width ≤ 256; rank ≤ 64; no HMR or measurement; not a portable certificate; no API or engine promotion. |
| #184 | **NEEDS_FIX** (C-F1 evidence, C-F2) | **MERGE_LABS_ONLY, conditional** | Fold #190 in, with green exact-head CI. **The owner must also accept the quantified encoding-time gap (C-F3/C-F4)**, since their note asked to keep the PR in research until a resource audit was done. That audit is delivered here; the gap is documented, not fixed. Not an encoder proof, a cut theorem or a channel theorem. |
| #185 | **NEEDS_FIX** (A-F2 provenance, A-F1 pins) | **KEEP_RESEARCH** | Fold #189 in. Utility is not demonstrated (A-F9). If the owner wants the evidence on `main`, it can land as research evidence only (tests, benchmarks and docs; no `src` change). There is no API or handoff claim. |

No condition of the stop rule held for a positive result. There was no false proof, no wrong
binding between source and CNF, no non-clean reset deleted, and no contract change accepted as
equivalent. The one provenance error, A-F2, blocks #185 until #189 or an equivalent fix is
folded in.

## 8. Recommended integration order

1. **#183 with #188.** It is self-contained and its files are disjoint from #184's.
2. **#184 with #190**, after the owner's decision on C-F3 and C-F4.
3. **#185 with #189** stays in Draft as research evidence.

The mission's condition for an assembly, "all three favorable", is **not met**, so no
integration assembly branch was published.

As a local check only, I merged `main@766d3df` with #188 (`4bf0ef5`, before the code-review
cleanups) and #190 (`60deccb`). The
merge was conflict-free (9 files, +1753). On that tree, ruff is clean, and the full pure-Python
suite with `SYMQ_TEST_REQUIRE=sat` gave 5319 passed and 230 skipped; all skips are optional
dependencies or native-only cases.

## 9. Reproduction material

The audit scripts are kept outside the repository; this report quotes their commands and
results. Each fix PR carries its own regression tests. These are the reproducers that matter
for a maintainer. They are excerpts, not a standalone script:

```text
# B-F1 (fails on 1552cc0, refused after #188)
p = HybridProgram(1, 1, [HOp("x", (0,))] * 10 + [HOp("reset", (1,))])
p.ops = tuple(p.ops)
prove_clean_resets(p, AffineSupport(2, 0, (1,)), max_operations=5)["source_sha256"]  # not None

# C-F1 (domain q1=0, right = cx(0,2).cx(2,3))
export_classical_miter_proof(Circuit(4).x(1).cx(0,2).cx(2,3), right, Contract(input_constants={1: 0}))
# -> not_proved even without the CCX: the original one-sided negative is vacuous

# A-F9
transpile(swap01 + cx02 + swap01, basis_gates=["x","cx","ccx"], optimization_level=2)  # -> cx(1,2)
```
