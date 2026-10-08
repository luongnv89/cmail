# Inputs, local secrets and config

## Select the config file

Pick the file the run will use, then pass it as `ENV_FILE` on every command.
Take the first that applies:

1. A config file the user named.
2. The trusted launcher's `default_config=` line (from install-time
   CMAIL_CONFIG_DIR, normally `~/.config/cmail/.env`), read as metadata after
   Gate 1 provenance without executing the launcher or reading `.env`. Use it when
   it is absent, or its summary shows the same DOMAIN or an empty one.
3. Otherwise a new per-domain file beside it: `<config dir>/<domain>.env`.

Never select a checkout `.env` or `.env-*` file the user did not name: such files
may belong to other domains. An `ENV_FILE` seen in the agent shell is an
agent-shell observation; use it only when the user confirms it. If the user says
their own terminal invocation uses another file, ask which file their invocation
actually uses. Do not edit a retained runtime's `.env`.

If the file is absent, copy the trusted `.env.example` from the reviewed source or
selected installed runtime without overwriting: `umask 077; mkdir -p <parent>;
cp -n <template> <file>; chmod 600 <file>; chmod 700 <parent>`. Reject
symlink/shared/unowned paths.

## Fill non-secret values yourself

Read the current state with
`python3 <skill-directory>/scripts/check_config.py --summary <file>`. It prints
DOMAIN, DEST_EMAIL, ADDRESSES, REGISTRAR, GDDY_ENV, CF_ACCOUNT_ID, CF_ZONE_ID and DRY_RUN,
reports CLOUDFLARE_API_TOKEN and GDDY_PAT only as set/empty/absent, and ends
with READY or NOT READY.

Take empty values from the user's message: DOMAIN (owned, registrable domain only;
no scheme/path), DEST_EMAIL (any receiving mailbox the user owns; it must be a
Gmail/Google account only if they also want sending), ADDRESSES (comma-separated
local parts, no `@domain`), GDDY_ENV (`prod` for real resources; `ote` cannot
prove production setup), REGISTRAR (`manual`, the current CLI's default for any
registrar; `godaddy` only when the user wants GoDaddy automation). With DOMAIN
unknown in GoDaddy mode, list candidates with
`gddy domain list --env <env> --json | jq -r '.data[] | .domain // .name'` and
offer them; in manual mode ask for the owned domain. Ask one batched question for whatever is still missing, then write
only the keys that need a value:

```text
python3 <skill-directory>/scripts/set_config.py <file> DOMAIN=<domain> DEST_EMAIL=<inbox> ADDRESSES=<locals>
```

The setter validates each value, refuses secret keys, keeps every other line
unchanged, writes atomically at mode 600 and prints key names only. It refuses a
key that already holds a different value unless `--replace` comes first. Use
`--replace` without asking for template defaults (`ADDRESSES=hello`,
`GDDY_ENV=prod`) and for values the user stated in this request; replacing any
other existing value is a stop.

## Secrets stay in the user's browser and editor

Never request CLOUDFLARE_API_TOKEN, GDDY_PAT or a Google App Password in chat.
cmail passes the token to curl in process arguments, visible to local `ps`
whoever launches it; this skill cannot change that runtime transport.

1. **GoDaddy (GoDaddy mode only):** browser OAuth via `gddy auth login --env prod`, which you start in
   the background. A headless user may instead create a PAT at
   https://developer.godaddy.com/personal-access-token and save GDDY_PAT locally.
2. **Cloudflare (hands-on):** open https://dash.cloudflare.com/profile/api-tokens
   → Create token → Custom token. Required permissions for current cmail are:

   | Scope | Permission | Access |
   |---|---|---|
   | Zone | Zone | Edit |
   | Zone | Zone Settings | Edit |
   | Zone | DNS | Edit |
   | Zone | Email Routing Rules | Edit |
   | Account | Email Routing Addresses | Edit |

   Include the intended owning account in Account Resources and the intended zone
   (or that account's zones for zone creation) in Zone Resources. Do not default to
   all accounts. Then open the config in an **unrecorded local editor** for the
   user (`open -t <file>` on macOS, `xdg-open <file>` on Linux) and ask them to
   paste the token right after `CLOUDFLARE_API_TOKEN=` with no quotes or spaces,
   then save. Ask only whether it is saved; then run `chmod 600 <file>` (editors
   may reset the mode) and rerun the summary. The checker rejects non-ASCII
   characters such as smart quotes an editor may insert. CF_ACCOUNT_ID is an optional 32-character hex
   **Account ID**, not Zone ID; CF_ZONE_ID must refer to this DOMAIN.
3. **Gmail (optional sending only):** the App Password from https://myaccount.google.com/apppasswords goes
   directly into Gmail's SMTP dialog, **not `.env`** and not an agent tool. Do not
   use the normal login password, share confirmation codes or disable policy.

## Literal-only config

Use `KEY='literal value'`. Do not put `$()`, backticks, variable expansions,
commands, multiline values or shell snippets in config. Legacy snapshots load
Bash assignments twice; the new 0.2.0-dev CLI uses a literal parser. The portable
checker remains intentionally narrower, so syntax validity alone is insufficient. Unknown or
runtime-control keys such as PATH or BASH_ENV are a stop: the user reviews and
removes them locally; never delete them silently or call them safe to source.

## Verify without executing or exposing assignments

```text
python3 <skill-directory>/scripts/check_config.py <file>
bash -n <file> >/dev/null 2>&1
```

The checker is read-only and value-free. It accepts a deliberately narrow
literal-assignment subset (including cmail's `%q` backslash escapes) and rejects
expansions, commands, unknown keys, duplicates, CR/CRLF and other control
characters, unquoted tilde/glob/brace syntax, symlinks and any mode other than 600.
A rejected but valid complex Bash file needs a local simplification, never
sourcing to bypass the gate. It does not verify mailbox ownership, credential
validity, resource authorization or network state. Do not print `bash -n`
diagnostics: they can contain a secret line. Without Python 3, offer installing
it (brew without sudo is auto) or do user-local manual checks and record their
limits; never call an unrun checker green.

Confirm no secret config is tracked. In a source checkout run
`git check-ignore <file>` and `git ls-files --error-unmatch <file>` (the latter
must fail). If tracked, stop and arrange credential rotation/removal with the
user; do not stage or display it.
