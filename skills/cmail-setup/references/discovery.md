# Context discovery

Run these read-only probes with a shell tool before asking anything. Each probe
locates or lists; none executes cmail, reads config contents or changes state.

| Fact | Probe | Record |
|---|---|---|
| Request cues | The user's message: resume/failure wording, named gate, error text, domain or alias | user-reported |
| OS | `uname -s` | `Darwin` is macOS; anything other than macOS/Linux is out of scope |
| Source checkout | `git rev-parse --show-toplevel`, then `test -f` for `cmail`, `install.sh` and `lib/env.sh` at that root | checkout path or none |
| Installed launcher | `command -v cmail`, Bash `type -t cmail`, `ls -ld ~/.local/bin/cmail ~/.local/share/cmail` | path and type; located, not executed |
| Config presence | `ls -l` on `~/.config/cmail/.env` and the checkout `.env`; whether `ENV_FILE`/`CMAIL_*_DIR` path overrides are set | owner, mode, size only |
| Tools | `command -v bash curl jq gddy brew apt-get dnf pacman` | found / missing |

Forbidden during discovery: running a found `cmail` (help, status, doctor, setup)
before Gate 1's provenance check; reading, grepping, sourcing or printing `.env`;
network or provider calls; installs, PATH edits or config edits. A probe that
fails or is unavailable is `unknown`, not a negative result.

## Context block

Print this before any question or gate action. Label each fact observed or
user-reported; never guess a value.

```text
Context — observed <timestamp>
OS: <Darwin | Linux | unknown> (<probe>)
Agent terminal: observed | none (advice-only)
Browser access: unknown (asked when a gate needs it)
cmail: <launcher path | checkout path | not found | unknown> (not executed)
Config: <path, owner, mode | absent | unknown> (contents not read)
Tools: <found> / missing: <missing>
Mode: new setup | resume at gate <n> (<cue>)
Unknown: <each undetectable or failed probe>
```

## Advice-only

Without a shell tool, give the user the probes above as one combined local check
and ask them to report the sanitized results. Keep every fact `unknown` until they
report; label reported facts user-reported. Facts the user already stated (for
example, "on my Mac") are user-reported, not observed.
