# Public SymQ qualification kit — no private repository access required

**Audience:** independent external auditor of SymQ PRs #90, #92, #93, #94,
#95, #96 and #97. **No archive, private GitHub permission or third-party
fixture is needed to read or execute this kit.** This branch is an isolated
reviewable public proposal, not a production implementation.

## What is actually supplied

1. `field_hmr_reference.py`: **standalone, standard-library-only**
   polynomial-field MAC oracle for GF(4) and GF(8), built from published
   arithmetic identities without importing SymQ or any private code.
   On `|x><y|`, independently sums all Kraus outcome signs as exact
   `fractions.Fraction` values and distinguishes a corrected HMR
   channel from uncorrected outcome dephasing.
2. `tests/test_public_qualification.py`: unit tests on that oracle;
   these tests *do not* certify code from other branches.
3. An exact-commit cross-branch replay plan below, using public GitHub
   sources only; the audit PR #97 already carries its own dedicated CI.
4. Explicit coverage/limitations: an independently reconstructed
   example is not a historically authenticated real compiler fragment.

## Run entirely from GitHub

```sh
git clone https://github.com/yoch/symq.git
cd symq
git fetch origin research/public-qualification-kit-20261029
git switch research/public-qualification-kit-20261029
python -m pytest -q tests/test_public_qualification.py
python -m research.public_qualification.field_hmr_reference --degree 2
python -m research.public_qualification.field_hmr_reference --degree 3
```

To check that the **actual #94 synthesis** matches the separate arithmetic
oracle, fetch #94 at `ddd64606693042259fa76e1fe39dc161b0e34bcd`:

```sh
git fetch origin ddd64606693042259fa76e1fe39dc161b0e34bcd
git worktree add --detach /tmp/symq-pr94 ddd64606693042259fa76e1fe39dc161b0e34bcd
(cd /tmp/symq-pr94 && python -m pip install -e '.[test]' \
 && python -m pytest -q tests/test_hmr_field_mac_research.py)
```

The #94 test independently enumerates every data-input/outcome assignment
and uses a distinct integer polynomial field multiplier to validate the
synthesizer. For strict all-coherence CPTP oracle checks, use the
public #90 research module and #97 audit tests; these are in separate
commits and are not automatically imported or merged here.

To replay the existing independent audit:

```sh
git fetch origin 8150759a1cdb77fbb0d62c656b2ab81115aff0c9
git worktree add --detach /tmp/symq-pr97 8150759a1cdb77fbb0d62c656b2ab81115aff0c9
(cd /tmp/symq-pr97 && python -m pip install -e '.[dev]' \
 && python -m pytest -q tests/test_crossrepo_audit.py)
```

The #97 test module fetches the exact pinned PR commits and may explicitly
skip when that network access is unavailable. **A green job with partial
skips is not full independent validation.** Its official GitHub Actions
audit job should be checked for the complete passed/skipped denominator.

## Qualification matrix

| SymQ PR | Publicly verifiable evidence | Still unproved |
| --- | --- | --- |
| #90 | Small exact CPTP reference, off-diagonal coherence, channel vs classical-output instrument | Scalable general quantum-hybrid channel checking |
| #92 | Whole-transcript reconstruction, exact local substitutions, overlapping connected-wire examples | Real compiled wide circuit coverage and quantum phase composition |
| #93 | Bounded degree ANF, explicit finite legal domain, exact GF(2) unsat witnesses | Native speedup and general quantum coherent-domain semantics |
| #94 | New public GF4/GF8 multi-bit MAC HMR gadget with all data/outcome replay | General delayed-feedback synthesis optimality and real compiled HMR patterns |
| #95 | Measured nonlinear C/ZDD speedups, negative affine cases, explicit pair-variable limit | Genuine source-cleared real compiler ROI, >32 coherent data bits |
| #96 | Public audit checklist only | No executable tests/fixtures in that PR |
| #97 | Audited independent test harnesses + CI | Evidence bound to local source availability; external private corpus absent |

**Do not interpret** any case here as an export of, or proof about, an
unavailable private circuit. No secret, complete private payload or
copyright-sensitive dataset was used. We deliberately avoid any direct
private-repository name or import in this public package.

## Audit follow-up

- Compare #94's synthesized *repaired* field-MAC and its direct reversible
  reference against the independent exact `coherence_coefficient` oracle.
- Try missing feedback and delayed noncommuting gates; capture concrete
  `(x,y,m)` counterexamples.
- Restrict #95 claims to the measured non-linear families. It requires
  `2*n_data <= 64`; a data contract exceeding 32 coherent bits must
  either be rejected, proved on a smaller standalone subspace, or handled
  by a separately justified composition/domain theorem.
- Keep the actual end-user action explicit: a research PR merge is distinct
  from promotion into `src/symq/` and from full production readiness.
