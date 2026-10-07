# Context discovery

Run these read-only probes with a shell tool before asking anything. Each probe
locates or lists; none executes cmail, reads config contents or changes state.

| Fact | Probe | Record |
|---|---|---|
| Request cues | The user's message: resume/failure wording, named gate, error text, domain or alias | user-reported |
| OS | `uname -s` | `Darwin` is macOS; anything other than macOS/Linux is out of scope |
| Source checkout | `git rev-parse --show-toplevel`, then `test -f` for `cmail`, `install.sh` and `lib/env.sh` at that root | checkout path, or none in cwd |
| Installed launcher | `command -v cmail`; `type -t cmail` in bash or `whence -w cmail` in zsh; `ls -ld ~/.local/bin/cmail ~/.local/share/cmail` | path and type; located, not executed |
| Path overrides | `printenv ENV_FILE CMAIL_BIN_DIR CMAIL_DATA_DIR CMAIL_CONFIG_DIR` | set paths only |
| Config presence | `ls -l ~/.config/cmail/.env`; `ls -l "$ENV_FILE"` when set; checkout `.env` only when `cmail`, `install.sh` and `lib/env.sh` all exist at the git root | owner, mode, size only |
| Tools | `command -v bash curl jq gddy brew apt-get dnf pacman` | found / missing |

A non-interactive agent shell cannot see the user's interactive aliases or shell
functions, so whether `cmail` is an alias or function in the user's terminal is
`unknown` or user-reported until Gate 1 rechecks it there.

When `ENV_FILE` is set, its `ls -l` result is the selected config path (metadata
only). If the agent's environment may differ from the user's interactive shell
(another shell profile, sandbox or host), record the selected path `unknown` and
confirm it at Gate 2.

Forbidden during discovery: running a found `cmail` (help, status, doctor, setup)
before Gate 1's provenance check; reading, grepping, sourcing or printing `.env`;
argument-less `env`, `set`, `printenv` or `export -p` (environment dumps can expose
CLOUDFLARE_API_TOKEN or GDDY_PAT); network or provider calls; installs, PATH edits
or config edits. A probe that fails or is unavailable is `unknown`, not a negative
result.

## Target machine

Probe results describe the agent's shell, which may not be the user's machine: a
remote sandbox, cloud VM, devcontainer or SSH host. Mark the target machine (and
the user's local terminal) `unknown` when:

- a user-stated fact conflicts with a probe (for example, "on my Mac" while
  `uname -s` prints `Linux`); or
- a failure/resume cue arrives but no launcher, checkout or config is found.

Then do not record OS, launcher, checkout, config or tool results as observed for
the user's machine; keep them as agent-shell observations only. Resolve the target
at Gate 1: asking which machine the user is setting up is allowed there because it
is undetectable. A probe on a non-target shell does not answer a Gate 1 question.
If the user confirms the agent shell is the target, keep the observations; if not,
continue as advice-only for that machine.

## Context block

Print this before any question or gate action. Label each fact observed or
user-reported; never guess a value.

```text
Context — observed <timestamp>
Agent shell: <present | none (advice-only)>
Target machine: agent shell | unknown (<reason>)
OS: <Darwin | Linux | unknown> (<probe>)
Browser access: unknown (asked when a gate needs it)
cmail: <launcher path | checkout path | not found | unknown> (not executed)
Config: <path, owner, mode | absent | unknown> (contents not read)
Tools: <found> / missing: <missing>
Mode: new setup | resume at gate <n> (<cue>)
      | resume, locating earliest unverified gate (<cue>)
Unknown: <each undetectable or failed probe>
```

## Advice-only

Without a shell tool, give the user the probes above as one combined local check
and ask them to report the sanitized results. Keep every fact `unknown` until they
report; label reported facts user-reported. Facts the user already stated (for
example, "on my Mac") are user-reported, not observed.
