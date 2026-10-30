# Security policy

SymQ is **experimental research software (0.1.0)**, not a hardened
security product or a certified general quantum-circuit verifier.
There is currently **no supported stable release line** and no security
response-time SLA.

The optional native C/ZDD core, external solver integrations, JSON importers
and isolated worker controls receive tests and CI, including sanitizers.
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
[architecture](docs/ARCHITECTURE.md) and
[resource limits](docs/verification-resources.md).
