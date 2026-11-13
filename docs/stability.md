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

### Names inside the stable names

The same split applies one level down.

| What | Stable | Stable, present with the native C core | Provisional | No promise |
| --- | --- | --- | --- | --- |
| Backend names (keys of `BACKENDS`) | `reference`, `sparse`, `packed`, `linear`, `truthtable`, `zdd` | `zdd-native`, `zdd-native-wide` | `sparse-copy`, `packed-fallback`, `adaptive-wire`, `auto-zdd` | |
| Theorem names of `verify` and `verify_explicit` | `classical_full`, `classical_contract` | | `sign_phase_exact`, `sign_phase_up_to_global` | `full_channel`, `reduced_channel`, `instrument` |

- **Backend classes.** A concrete backend promises the `Algebra` interface, its `name` and, for
  the native ones, its `max_width`. Its other public methods (`node_count`, `cache_info`,
  `simulate_pair`, ...) are provisional; the reference lists them per class.
- **`Contract.assumption`** is provisional: it takes expressions of `symq.sat.assumptions`,
  which is not exported. The other fields of `Contract` are stable.
- **Types that are not exported but appear in stable signatures** (`Guard`, returned by
  `Budget.start` and taken by the `Algebra` constructor) can be passed around as received;
  their own attributes and methods are provisional.
- **Modules the guides use but no package exports** (`symq.sat.composition`,
  `symq.generators.arithmetic`, `symq.generators.gf2n`, `symq.verification`, ...) work and are
  tested, and are provisional like every unexported path.
- **Engines from `symq.external`** (`--engine qcec`, the PolyBoRi and CUDD adapters) carry no
  promise, even when a stable function or command is the way to reach them.

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

Supported Python versions are those CPython itself supports. 0.3 and 0.4 run on
CPython 3.11 to 3.14.
3.10 reached its end of life in October 2026: the 0.2 line, which runs on 3.10 to 3.14, keeps it,
and it was dropped in 0.3.

## The command line

For `symq check`, `symq anf` and `symq doctor`, the stable parts are the arguments, the exit
codes and the keys of the `--json` output.

| Exit code | Meaning |
| --- | --- |
| 0 | `check`: the circuits are equivalent for the requested theorem. `anf`, `doctor`: success |
| 1 | `check`: the circuits differ. `doctor --require-native`: the native core cannot be loaded |
| 2 | No verdict: a budget or the memory ran out, the engine cannot hold the instance, or it is not installed (`inconclusive`, `unsupported`) |
| 3 | Usage or input error: bad command line, missing or malformed file, unsupported gate, unknown engine |
| 4 | Internal error: an exception nothing anticipated. A defect to report; no verdict was reached |

A script may rely on "0 means proved equivalent" and "1 means proved different". It must not
read 2, 3 or 4 as "different". Code 1 is never the result of a crash: Python's own exit status
for an uncaught exception is 1, so every command catches what it did not anticipate and exits
with 4 instead.

The JSON outputs of the three commands carry `schema_version` and `kind`, including the object
`check` and `anf` print with `--json` when they stop without a result
(`"outcome": "inconclusive"` and a `reason`). A usage or input error (exit 3) prints nothing on
standard output, with or without `--json`: its message is on standard error (for example
`--engine sat` with `--max-nodes` or `--max-terms`). Within one `schema_version`:

- keys may be **added**; a consumer should ignore keys it does not know;
- in a `check --json` record that stopped before its inputs were hashed (the deadline expired
  first; the outcome is then `inconclusive`), `left_sha256` and `right_sha256` are empty
  strings, and so is `contract_sha256` when a contract was given (`null` means no contract);
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
dataclass fields with their defaults, declared attributes and public members, backend names,
theorem names, the arguments of the stable commands, the exit code and outcome of a fixed list
of command lines and the keys and types of each JSON output.
`tests/test_api_snapshot.py` rebuilds that record from the installed package on every CI run and
fails on any difference, on every supported Python version.

To change the public surface on purpose:

1. make the change, following the rules above;
2. run `python tools/api_snapshot.py --write` (CPython 3.12, native core and `python-sat`
   installed), which rewrites the snapshot and the [core API reference](reference/api-core.md);
3. add a `CHANGELOG.md` line that names what changed for users.

The snapshot guards interfaces, not behaviour, and it sees what a class declares: an attribute
that only a constructor assigns, without a declaration on the class, is not recorded. Behaviour
is covered by the test suite, in particular the cross-engine differential tests; neither is a
proof of correctness.
