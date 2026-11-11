# Examples

Runnable scripts and command-line inputs. Every top-level script is executed by
`tests/test_examples.py`, so it stays in step with the code. Run one from a checkout with
`python examples/<name>.py`.

The *Layer* column says which part of SymQ a script relies on. Only the core is maintained;
`symq.experimental` is opt-in and `symq.labs` carries no API promise (see the
[README](../README.md#experimental-apis)).

## Scripts

| Script | Shows | Layer | Extra needed |
| --- | --- | --- | --- |
| [`classical_equivalence.py`](classical_equivalence.py) | Verdicts, replayed witnesses, exact ANFs and variable order | core | none |
| [`wide_and_blocks.py`](wide_and_blocks.py) | Affine stages of any width; block-wise checks of disconnected circuits | core | none |
| [`search_loop.py`](search_loop.py) | Checking many candidates against one reference with `ReferenceChecker` | core | none |
| [`import_circuits.py`](import_circuits.py) | Importing OpenQASM and Qualtran kickmix text, then verifying | core (`symq.kickmix`, sign-phase checker) | none |
| [`sat_contract.py`](sat_contract.py) | SAT contracts: observed outputs, restored wires, input assumptions | core (`symq.sat`) | `sat`; the script exits early without it |
| [`public_demo.py`](public_demo.py) | The [public demonstration](../docs/demo.md): classical equivalence and a coherent HMR channel | core + `symq.experimental` | none |
| [`contextual_substitution.py`](contextual_substitution.py) | Proving a rewrite at one site of a larger circuit | `symq.labs` | `sat` |
| [`hybrid_substitution.py`](hybrid_substitution.py) | A measurement-based uncompute proved at a global span | `symq.labs` + `symq.experimental` | none |
| [`gf24_rewrite.py`](gf24_rewrite.py) | Replacing a GF(2^24) schoolbook multiplier by the 99-product tower | `symq.labs` | none |

Install the `sat` extra with `python -m pip install -e ".[sat]"`.

## Command-line inputs

| Directory | Used by |
| --- | --- |
| [`experimental/`](experimental/) | `symq inspect`, `verify`, `replay` and `profile` in the [demo](../docs/demo.md) and the wheel job of the CI |
| [`locate/`](locate/), [`prepare/`](prepare/), [`rewrite/`](rewrite/) | The `locate` → `prepare-rewrite` → `rewrite` → `replay` workflow of the [rewrite guide](../docs/guide/rewrite.md) |
| [`rewrite_bricks/`](rewrite_bricks/) | The [rewrite bricks guide](../docs/guide/rewrite-bricks.md) |
| [`table_xor/`](table_xor/) | The [table-XOR contract guide](../docs/guide/table-xor-contract.md) |

The rewrite, brick and table-XOR inputs exercise research commands that live in `symq.labs`.
