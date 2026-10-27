# Agent rules for symq

- Treat the connected GitHub repository and exact commit SHA as the source of truth. Never assume a local checkout reflects a branch.
- For changes, branch from the revalidated base SHA. Use conditional writes, read back HEAD and final diff, and associate every test claim with exact content.
- Keep symq self-contained: no reference to, import from or dependency on another private repository. Needed code or resources may be copied in; the copy is then maintained here.
- Keep the accepted semantic domain narrow and explicit. Reject unsupported gates, measurements and quantum semantics instead of silently approximating.
- New symbolic optimizations require differential tests against a simple reference, mutation tests, resource guards and independently reproducible benchmarks.
- Keep development and untouched holdout corpora disjoint. Record provenance, tool versions, machine, times, memory, repetitions and failure cases.
- Avoid performance claims from a single pathological circuit; report paired distributions and conversion overhead.
- Never publish private fixtures, secret paths, personally identifying information or uncleared third-party assets.
- CI passing, semantic correctness, reproducibility, and external comparative performance are separate claims.
- Work through reviewable PRs; do not merge without a separate authorization.
