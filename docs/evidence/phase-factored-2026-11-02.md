# Factored phase certificates: inspected executable qualification

Research PR #163; no merge/default/public-API promotion. The integrated main
baseline is 755385e1e638365282e9cfccebdba4ce41fda451. This note pins one executed
checkpoint, not the status of all future documentation or audit corrections.

## Exact-source receipt

- Executable HEAD: `034e6500d57d38943e4684234e476ff0b3b8a6eb`.
- Tree: `0d56aae9c71d61964b6c3bfa4a7e57d1c97d2b38`.
- Synthetic merge: `03a0a73fa14ada3f920c335bbed02a10486913b1`, reread from GitHub:
  expected main/HEAD parents and identical tree.
- [Installed-package qualification](https://github.com/yoch/symq/actions/runs/41516624481)
  passed Ruff, the new factored tests, the inherited nonlinear-bitplane/adversarial
  tests, and the source campaign. Actual Glucose is required by this workflow.
- Downloaded artifact13176120641 ZIP SHA-256:
  `4680508124b5bd0fb455c25f6d44b2e85a6c68bbb4711c82e0def3219acfc874`.
  Independently recomputed ZIP digest equals the API. commit.txt/tree.txt match
  the synthetic merge above; all positive, negative and paired success flags
  and all external recheck statuses were inspected.
- Engine SHA-256: `1929d101d0cb51cc387de5178e71fc8dcdf6f728e1cd86192ff1cb34f5b0e8d4`
  (Git blob4b94dd4e21c4b984b76d1a3e8f4e6b4ce6d93559).
- Harness SHA-256: `2b2f4a76924af348947afbb9afd2190de25d5db6d900c2fa0c12329dd35fe038`
  (Git blobcffc118a66844acdf043b14306e6a2f5aa20e902).
- Test SHA-256: `ed03b0588ab37cd467a7a16e43d6c09461b4249d546a7ea180985539556d95ab`
  (Git blobe31cafd1139ab92f1726b770649ef6404364c2e7).

The three new executable files were rehashed locally against published blobs.
The eight inherited source/oracle hashes match the prior inspected feature-strategy
artifact13172464650; those files are unchanged in this continuation. Eleven hashes
are retained in the JSON. General multi-platform CI and any later documentation
HEAD must be checked separately; this targeted receipt does not make them green.

## Actual source/oracle validation

Python3.12.15, Linux-7.0.0-1017-azure-x86_64-with-glibc2.43. The campaign passes:

- 192 positive source representations: eight selected Z/4 phase functions,
  six invertible two-coordinate GF(2) mixes, four affine offsets. The independent
  exact channel oracle checks every legal matrix unit and each positive has an
  external fresh certificate check in addition to discovery's internal recheck.
  This is eight functions represented24 ways, not192 unrelated functions.
- 24 extra source-phase mutants: old certificates rejected, structural discovery
  safely not_proved, and the independent channel oracle confirms difference.
- 72 paired trials: two mixing families, degrees3/5/8/12/16/32, two methods,
  three randomized-order repetitions. All claimed positives externally rechecked;
  baseline resource refusals retained instead of converted to differences.

The separate tests cover source snapshots, stale/forged certificates, exact types,
constants and empty products, overlaps, feedback changes, nonzero support offsets,
missing SAT, inherited resource limits and deadline expiry after a fresh success.
A retained example shows the structural recognizer missing valid aggregate modular
cancellation, while both supplied-candidate checkers prove it. That is an expected
incompleteness, not a channel counterexample.

## Representation and timing frontier

For q_i=a_i*b_i and an invertible XOR mixing h, the constructed phase product(q_i)
has2^(d-1) monomials in its unique ANF over h. The factored certificate stores one
product of d affine forms. The large term count is mathematically derived, not
materialized. The truth-table Moebius count is separately executed for d<=8.
The source ANFs remain compact in this fixture; arbitrary source extraction can
still expand and this is not a universal quantum verification result.

Whole-call medians (milliseconds), including discovery's fresh source check:

| Degree | Explicit-ANF CEGIS, star | Factored, star | Explicit-ANF CEGIS, chain | Factored, chain |
| --- | --- | ---: | --- | ---: |
| 3 | proved,3.928 | 0.941 | proved,4.017 | 0.900 |
| 5 | proved,27.315 | 1.146 | proved,27.236 | 1.159 |
| 8 | inconclusive,108.825 | 1.563 | inconclusive,107.223 | 1.693 |
| 12 | inconclusive,126.582 | 2.154 | inconclusive,119.867 | 2.268 |
| 16 | inconclusive,121.298 | 2.959 | inconclusive,128.593 | 3.018 |
| 32 | inconclusive,216.970 | 6.192 | inconclusive,200.597 | 7.120 |

All factored rows are proved. The adaptive baseline uses source_monomials=True,
64 samples and256 dictionary features. The factored route uses a10000-item cap
on its DIFFERENT grammar. Both retain their original10-second deadline and
inherited budgets. Caps with different units are not described as equal budgets.
No ratio of completed-proof speedup is inferred from inconclusive-versus-proved
rows. These are constructed representation tests, not an external benchmark.

At d32:64 free physical inputs,65 data/work wires and one dephaser ancilla.
Both final fresh checks use191 DAG nodes,380 clauses and one actual SAT call
(three bit obligations). The certificate has32 factors; the grammar-item statistic
is98 in star form and563 in chain form, reflecting denser affine masks. Neither
is total process memory. No exhaustive density simulation at this width is claimed.

## Evidence limits and handoff

Initial local pure-algebra execution covered16030 assignments across818 accepted
algebra cases and963 safe structural refusals. It used minimal guard/error shims,
not installed SymQ/PySAT or a full local checkout. The installed source/Glucose
claims come from the CI receipt above. A test import-format error stopped the
first targeted run before runtime; the formatting fix did not weaken tests.

No untouched holdout, real compiler/KMB loader, minimum certificate guarantee,
independently checked SAT-UNSAT proof or portable proof kernel. Affine/nonlinear
relational analysis and factored Boolean representation are prior art. This
implementation specializes them to the source-bound fibre-phase obligation.

[Algorithm and grammar](../labs/phase-factored.md).
[Full independent audit mission](../audit/phase_discovery_163.md).
The audit must cover ALL of #163, including earlier fixed/adaptive/separator paths,
and requalify exact final CI, macOS, packaging and all four relevant artifact sets.
