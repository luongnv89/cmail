# Distribution decision and status

## Current reviewed-checkout installation

`bash install.sh --local` installs the complete `0.2.0-dev` runtime and its
completion files from this reviewed checkout, without downloads, setup, or
provider access. Config and upgrade/rollback protections are preserved.
The new CLI is not published in a tagged release; remote installation keeps
its existing immutable legacy pin. See [current CLI usage](https://github.com/luongnv89/cmail/blob/main/docs/cli.md).

## Chosen route: upstream GitHub source distribution

cmail's upstream repository and its GitHub releases are the chosen distribution
route. This is upstream distribution, **not** Homebrew/core admission or an
endorsement by Homebrew. The user-local installer is deliberately independent
of a package manager and does not need sudo. From a checkout containing the
installer, the installation entry point is one command:

```bash
bash install.sh
```

See [README installation](https://github.com/luongnv89/cmail/blob/main/README.md#installation) for verification, paths,
configuration and upgrades. Remote installation downloads the nine base runtime files
and additional allowlisted libraries/completions when the selected runtime uses them,
from the upstream repository at an immutable commit, stages them privately,
checks Bash syntax and offline help, then replaces a generated launcher by a
same-directory rename. It does not extract archives. Previous installed
runtimes remain available on disk; a failed download/validation never changes
the active launcher. A late activation failure may retain an unused validated
runtime; retaining it also prevents signal cleanup from deleting a newly active
runtime. A local lock rejects concurrent installs into the same runtime store. Different runtime stores must not share a launcher destination.

The default runtime commit is `eb45f9558ecc5874e6a21d6f1b93fe1379f46841`
(the existing v0.1.0 source tree). Installation requires Bash 3.2+, curl and
standard macOS/Linux utilities. HTTPS is required even across redirects. An
immutable source pin and TLS do **not** constitute signed release verification
or independent checksums. Only run installers and configurations you trust.
All destinations and their parent directories must be controlled by your user;
do not install into shared/untrusted writable directories. Direct symlink
runtime/config/bin directories and launcher destinations are refused. Existing
marked destinations are a management convention, not an authentication boundary.

## Homebrew evaluation

Official policy pages consulted on 2026-10-07:

- [Acceptable Formulae](https://docs.brew.sh/Acceptable-Formulae): core requires
  a DFSG-compatible open-source license, stable versioned/verifiable sources,
  SHA-256-verified archives, supported-platform build/test coverage, suitable
  dependency management, and reliable installation behavior. Core admission
  also depends on the shared [Package Acceptance Policy](https://docs.brew.sh/Package-Acceptance-Policy).
- [Adding Software to Homebrew](https://docs.brew.sh/Adding-Software-to-Homebrew):
  CLI software normally uses a formula; author and test the formula, declare
  dependencies, run build-from-source installation, `brew test`, strict/new
  online audit and style checks, then submit a PR and respond to review.
- [How to Create and Maintain a Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap):
  a maintainer tap is an external formula repository, not admission to core.
  It requires an actual maintained/published repository and formula with
  versioned sources, checksum, dependencies, installation and tests.

A Bash CLI is a plausible formula candidate, but cmail is **not currently
ready for a core submission**. No LICENSE exists in this repository; public
source access alone is not an open-source license. The maintainer must decide
licensing and distribution rights; this change does not select a license.
The current development CLI checks dependencies without installing them; legacy
v0.1.0 still has nested installers. A Homebrew package would need to declare
appropriate dependencies and target a reviewed compatible release. A formula must place the complete runtime in libexec and
keep mutable user config outside the keg. Provider-dependent setup cannot be
a formula test; help and private-config behavior can be tested offline.

A maintainer tap could offer familiar `brew install owner/tap/cmail` upgrades,
but it adds a second publication/maintenance surface and is not an official
Homebrew/core package. Neither a tap nor core is chosen for this iteration.
No formula, external repository or Homebrew submission is created here, and
no `brew install cmail` availability or eventual acceptance is promised.

## Recorded publication/submission outcome

Observed via GitHub on 2026-10-07:

| Item | Actual outcome | Outstanding requirements |
|---|---|---|
| Upstream v0.1.0 source release | Published 2026-10-07T08:31:22Z: [release](https://github.com/luongnv89/cmail/releases/tag/v0.1.0). Zero uploaded assets; GitHub supplies source archives. | Existing release does not contain this installer. It is not proof of installer publication. |
| New user-local installer | Implemented/tested and merged via [PR #7](https://github.com/luongnv89/cmail/pull/7) at `bbd7a135e2794bae840277da361c39d2101357e0`; **not published in a tagged release**. | Maintainer distribution/license decision, then separately authorized release/publication including installer and these docs. |
| Homebrew/core | **Not submitted; no admission outcome.** | Licensing, stable checksummed release, dependency integration, supported-platform tests, formula/audit, authorized submission and Homebrew review. |
| Maintainer Homebrew tap | **Not created or published.** | Distribution rights, separately authorized tap creation/publication, tested formula, checksums and maintenance commitment. |

No release was created or amended, no package was published, and no Homebrew
submission was made as part of this change. Recording these pending outcomes
is intentional, not a claim that publication occurred. A source checkout with
this change can install now; a released remote bootstrap command is pending.

Before advertising a remote one-command installer, publish a reviewed immutable
revision containing `install.sh`, document that exact revision (not a moving
`main` URL), verify a download/install/help cycle on clean macOS and Linux
machines, and record the actual release URL/outcome here. The current offline
regressions verify the local installer and installed CLI, not public hosting,
Homebrew eligibility/admission, provider authentication, DNS or mail delivery.
