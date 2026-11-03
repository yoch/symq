# Agent A mission — independent source-bound compiler rewrite handoff

**Repository:** `yoch/symq`.
**Owner:** [#180](https://github.com/yoch/symq/issues/180); coordination [#179](https://github.com/yoch/symq/issues/179).
**Starting reference (historical):** `main@766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc`.
**Role:** create one self-contained source-cleared, reproducible *real compiler workflow* pilot and determine whether a narrow user-facing handoff is warranted.

## Read and pin

Read `AGENTS.md`, `README.md`, `docs/architecture.md`, `docs/guide/rewrite.md`,
`docs/guide/table-xor-public-api.md`, `docs/guide/experimental-composition.md` and
`docs/evidence/comparative-pilot-2026-11-01.md`, together with live #100/#144/#46.

Inspect the actual code for `src/symq/labs/rewrite_prepare.py`,
`rewrite_request.py`, `rewrite_locator.py`, `contextual_substitution.py`,
`src/symq/experimental/table_xor.py` and the relevant SAT contracts.
Don't assume an on-disk checkout is current. Freeze the actual GitHub HEAD,
diff/reviews/checks before any write.

## Exact problem

A compiler has a source circuit `S`, a genuinely alternative implementation `R`,
a particular original local pattern `L` and an explicit input/ancilla/observation
contract `K`. SymQ must identify **one complete structural occurrence** of `L`
and give an opt-in proof of `S` versus `S[L↦R]` *at that exact site*.

For a restricted Boolean basis-domain contract, do **not** silently infer a coherent
quantum channel theorem. For any high-level correctness claim (e.g. a lookup table),
the independent specification-to-source obligation must be established separately.
A preparation manifest and its source hashes do **not** independently authenticate
the source program or authorize application.

The sequence is:
`locate` → `prepare-rewrite` → independently prove `rewrite` →
fresh `replay` → only then expose an application candidate if the existing cost
policy allows it. Prefer a small integration harness over a new solver.

## Work packages

1. **Corpus search and provenance.** Obtain legally redistributable code-generated pairs,
   ideally from a pinned public Qualtran/Cirq/Qiskit/other compiler and a separately
   derived optimized implementation. Pin upstream commit, license, generator invocation,
   input dimensions, source SHA, mapping, basis order and normalization. An already used
   public development corpus is not a blind holdout. Construct a second nontrivial
   independent family and specify which tests are source-generated, independently built,
   or synthetic. Do not use private qant sources/fixtures as published evidence.
2. **Adapter.** Design an optional typed `symq.labs` or CLI-only bundle binding source,
   local original/candidate, map, legal input domain, clean/dirty/restored inputs,
   optional table oracle, declared integer gate weights and budget. If no new code
   is needed, provide a versioned documented recipe plus deterministic tests.
   Be explicit about the no-replace-but-nonatomic filesystem contract.
3. **Proof and refusal semantics.** Test unique/nonunique/missing span, unmapped wire,
   multiple valid maps, wrong candidate, stale source, forged manifest, edited report,
   deadline after apparent success, cost-equal refusal, dirty ancillas and unsatisfied
   cut assumptions. For an HMR fragment, explicitly use a coherent channel/instrument
   checker or return unsupported. Do not hand-wave entanglement.
4. **Independent oracle.** For small reversible cases independently enumerate all
   allowed initial states and compare full output vectors. If the theorem concerns
   a quantum channel, compare all legal matrix units with a separately implemented
   density/Kraus oracle and test phase mutants. A local cut-state witness is not
   necessarily reachable from the global source; identify witness type honestly.
5. **Packaging, CI, evidence.** Test the workflow in an installed wheel and extracted
   sdist outside the checkout. At least 12 positive and 12 adverse fully labelled
   cases across >=2 distinct families, one genuine third-party compiler family if
   source-cleared. Use >=15 paired full-call timing/RSS repetitions for selected
   comparable cases, randomizing order and including conversion and replay.
   An external QCEC or SAT/AIG comparison must use the same theorem class.

## Required delivery

An isolated Draft PR with source/fixture generator + license/manifest, runtime-only
adapter *if justified*, tests including mutants, full-call reproducible results,
honest unsupported and timeout rows, and an agent handoff report under `docs/evidence/`.
Write an issue #180 summary linking exact files/HEAD/tree/CI and negative evidence.
An independent agent must audit the actual diff and rerun adversarial tests.

**No stable root API change, no new default engine, no merge or release.**
Stop with a negative report if no useful source-cleared compiler task can be shown.
