# Security policy

SymQ is **experimental research software**, not a hardened security product
or a certified general quantum-circuit verifier. There is no security
response-time SLA.

## Supported versions

Fixes go to the latest release series (the `release/X.Y` branch with the
highest number) and to `main`. Older series are not maintained. A wrong
`equivalent` or `different` verdict in the stable tier is treated like a
vulnerability: the affected release is yanked and a patch release follows
(see [RELEASING.md](RELEASING.md#if-something-is-wrong-after-publication)).

The optional native C/ZDD core, external solver integrations, JSON importers
and isolated worker controls receive tests and CI. For the native core this
includes sanitizers, injected allocation failures and seeded fuzzing.
Those controls do **not** establish memory safety or suitability for
adversarial untrusted workloads.

## Reporting suspected vulnerabilities

Please **avoid posting exploit details, secrets or other sensitive
reproduction material in a public issue**.

- If GitHub's **Report a vulnerability** / private vulnerability reporting
  is available under this repository's Security tab, use it.
- If it is not enabled, contact the repository maintainer through GitHub
  privately before sharing a proof of concept. Do not assume a private
  reporting endpoint exists merely because this policy file is present.
- For non-sensitive correctness bugs and feature requests, use
  [public issues](https://github.com/yoch/symq/issues).

A useful report specifies the exact commit SHA, Python and operating system,
native build/toolchain information, the supported theorem and backend,
a minimal input and the expected versus observed result. Never include
tokens, credentials or private third-party circuits in a report.

## Scope

Results can be invalidated by an unsupported input domain, a wrong
output/ancilla contract, an incomplete quantum grammar or an exhausted
resource limit. Please report such failures as **correctness issues**,
not just performance anomalies. An `inconclusive` or `unsupported` result
must never be described as a proof.

For the current API boundaries see [README](README.md),
[architecture](docs/architecture.md) and
[resource limits](docs/guide/resources.md).
