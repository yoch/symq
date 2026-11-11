# Stability policy

What SymQ promises to keep working from one release to the next, what it does not, and how the
promise is checked. The policy applies from the first release, 0.2.0.

It is a promise about **interfaces**. It says nothing about speed, and it is not a claim that the
implementation is formally verified.

## Three tiers

| Tier | What is in it | Promise |
| --- | --- | --- |
| **stable** | The classical core: every name exported by `symq`, `symq.sat`, `symq.backends` and `symq.generators` that is not listed as provisional below; the commands `symq check`, `symq anf` and `symq doctor` | Kept compatible, as described under [What a release may change](#what-a-release-may-change) |
| **provisional** | Exported names listed in the table below | May change in any minor release, with a changelog entry; never silently |
| **no promise** | `symq.experimental`, `symq.labs`, `symq.external`, every other command of the CLI, and anything whose name starts with an underscore | May change or disappear in any release |

A name is **public** when a core package lists it in its `__all__`. Importing a name from the
module that happens to define it (`symq.circuit.Circuit`, `symq.sat.miter.check_sat_equivalence`)
works, but only the exported path (`symq.Circuit`, `symq.sat.check_sat_equivalence`) is promised.

The full list, with the tier, signature and members of each name, is the generated
[core API reference](reference/api-core.md).

### Provisional names

| Name | Why it is not frozen |
| --- | --- |
| `symq.PhaseProgram`, `symq.check_phase_equivalence`, `symq.phase_semantics` | Sign-phase programs with measure-and-reset are outside the classical core |
| `symq.Choice`, `symq.choose`, `symq.features` | Heuristic selector: its rules are meant to be overturned by new measurements |
| `symq.sat.Encoder`, `symq.sat.Miter`, `symq.sat.build_miter` | Building blocks of the SAT encoding, which changes with the encoding |
| `symq.backends.SparseCopyAlgebra`, `symq.backends.PackedFallbackAlgebra`, `symq.backends.WireAdaptiveAlgebra`, `symq.backends.AutoZDDAlgebra` | Comparison variants of a stable backend, kept for measurements |
| `symq.backends.MixedSparseZDD` | Value type of the two adaptive variants |

Three finer points follow the same split:

- **Backend names.** `reference`, `sparse`, `packed`, `linear`, `truthtable` and `zdd` are stable
  keys of `BACKENDS`; `zdd-native` and `zdd-native-wide` are stable and present when the optional
  C core is built. `sparse-copy`, `packed-fallback`, `adaptive-wire` and `auto-zdd` are
  provisional.
- **Backend classes.** A concrete backend promises the `Algebra` interface, its `name` and, for
  the native ones, its `max_width`. Its other public methods (`node_count`, `cache_info`,
  `simulate_pair`, ...) are provisional; the reference lists them per class.
- **Theorems.** `verify` and `verify_explicit` accept `classical_full` and `classical_contract`
  as stable theorem names. `sign_phase_exact` and `sign_phase_up_to_global` are provisional; the
  channel theorems belong to `symq.experimental` and carry no promise.

## What a release may change

SymQ is at version 0.x. The rules are stricter than "anything goes before 1.0":

- A **patch release** (0.2.0 → 0.2.1) never removes or changes a stable interface.
- A **minor release** (0.2 → 0.3) may remove or change a stable interface only if an earlier
  minor release already emitted a `DeprecationWarning` for it and named the replacement.
- **Additions** are allowed in any release: a new name, a new optional parameter with a default,
  a new key in a JSON output, a new backend.
- **Correctness fixes are exempt.** If a stable function returns a wrong verdict, or accepts an
  input it cannot handle exactly, it is fixed in the next release without a deprecation period,
  even when the fix turns an answer into a refusal. The changelog says so under "Fixed".

Supported Python versions are those CPython itself supports. 0.2 runs on CPython 3.10 to 3.14;
3.10 reached its end of life in October 2026, is kept for the 0.2 line, and goes in 0.3.

## The command line

For `symq check`, `symq anf` and `symq doctor`, the stable parts are the arguments, the exit
codes and the keys of the `--json` output.

| Exit code | Meaning |
| --- | --- |
| 0 | `check`: the circuits are equivalent for the requested theorem. `anf`, `doctor`: success |
| 1 | `check`: the circuits differ. `doctor --require-native`: the native core cannot be loaded |
| 2 | Inconclusive: a budget ran out, or the engine cannot hold the instance. Not a verdict |
| 3 | Usage or input error: bad command line, missing or malformed file, unsupported gate, unknown engine |

A script may rely on "0 means proved equivalent" and "1 means proved different". It must not
read 2 or 3 as "different".

JSON outputs carry `schema_version` and `kind`. Within one `schema_version`:

- keys may be **added**; a consumer should ignore keys it does not know;
- a key is never removed, renamed, or given another JSON type. Such a change increments
  `schema_version` and follows the deprecation rule above.

## What is not part of the interface

These can change in any release, and tests or scripts should not depend on them:

- the text of `reason` and of error messages (the exception *class* is stable);
- which engine `--engine auto` or `choose` selects for a given input;
- the variable order `order="auto"` picks, node counts, term counts, `Stats` values and timings;
- the circuits `symq.generators` produces for a given seed (the function signatures are stable);
- the SHA-256 digests in verification records: they identify an input within one SymQ version,
  and a change of canonical form is announced in the changelog;
- the layout of `symq doctor`'s text report (use `--json`), and the contents of its `sources`,
  `external`, `platform` and `executable` fields;
- the native module `symq.backends._zdd`, its ABI number and its functions;
- performance.

## How the promise is checked

`tests/data/api_snapshot.json` records the public surface: exported names, tiers, signatures,
dataclass fields, public members, backend names, theorem names, the arguments of the stable
commands, the exit code of a fixed list of scenarios and the keys and types of each JSON output.
`tests/test_api_snapshot.py` rebuilds that record from the installed package on every CI run and
fails on any difference. The comparison is exact on CPython 3.12 and by name on the other
versions, where the text of a signature may be rendered differently.

To change the public surface on purpose:

1. make the change, following the rules above;
2. run `python tools/api_snapshot.py --write` (CPython 3.12, native core and `python-sat`
   installed), which rewrites the snapshot and the [core API reference](reference/api-core.md);
3. add a `CHANGELOG.md` line that names what changed for users.

The snapshot guards interfaces, not behaviour. Behaviour is covered by the test suite, in
particular the cross-engine differential tests; neither is a proof of correctness.
