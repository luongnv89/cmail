# Inputs, local secrets and config

## Ask for non-secret intent

Reuse the OS from discovery; confirm it only if `unknown`. Reuse a config path only
when it came from the trusted launcher's `default_config=` line or from an
ENV_FILE confirmed here; otherwise ask which file the invocation actually uses.
Confirm any of these not already given: DOMAIN (owned, registrable domain only; no
scheme/path), DEST_EMAIL (receiving Gmail account), ADDRESSES (comma-separated
local parts, no `@domain`), GDDY_ENV (`prod` for real resources; `ote` cannot prove
production setup), intended Cloudflare account, aliases needing send-as and
existing DNS/mail.
Never request CLOUDFLARE_API_TOKEN, GDDY_PAT or a Google App Password in chat.

## Acquire secrets in the user's browser

1. **GoDaddy:** prefer browser OAuth via local `gddy auth login --env prod` after
   permission. A headless user may create an optional PAT at
   https://developer.godaddy.com/personal-access-token and save GDDY_PAT locally.
   Ask only whether it was saved; recheck exact-domain access at gate 3.
2. **Cloudflare:** https://dash.cloudflare.com/profile/api-tokens → Create token
   → Custom token. Required permissions for current cmail are:

   | Scope | Permission | Access |
   |---|---|---|
   | Zone | Zone | Edit |
   | Zone | Zone Settings | Edit |
   | Zone | DNS | Edit |
   | Zone | Email Routing Rules | Edit |
   | Account | Email Routing Addresses | Edit |

   Include the intended owning account in Account Resources and the intended zone
   (or account's zones for zone creation) in Zone Resources. Do not default to all
   accounts. Copy into private local config, then clear the clipboard if desired.
   Activity, resource access and successful operations are distinct gates.
   CF_ACCOUNT_ID is an optional 32-character hex **Account ID**, not Zone ID.
   CF_ZONE_ID must refer to this DOMAIN, not another existing zone.
3. **Gmail:** enable 2-Step Verification if allowed. Open
   https://myaccount.google.com/apppasswords and generate an App Password for Mail.
   Enter it directly in Gmail's SMTP dialog, **not `.env`** and not an agent tool.
   Do not use the normal login password, share confirmation codes or disable policy.

## Choose the correct file and update privately

Installed launcher default: the trusted launcher's `default_config=` line (from
install-time CMAIL_CONFIG_DIR, normally `~/.config/cmail/.env`), read as metadata
after Gate 1 provenance without executing the launcher or reading `.env`. An
ENV_FILE set when cmail runs wins. An ENV_FILE seen by the agent is an agent-shell
observation, and one set only in the user's interactive profile is invisible, so
confirm with the user whether their invocation sets ENV_FILE before selecting a
file. Source execution default: checkout `.env`. Reuse the path only when it came
from the trusted launcher line or a confirmed ENV_FILE; otherwise ask the user
which file their invocation actually uses. Do not edit a retained runtime's `.env`
or assume checkout and installed configs match.

If absent, use the trusted `.env.example` from the reviewed source or selected
installed runtime. After consent, create its parent privately (`umask 077`) and
copy without overwriting an existing file. Make the file mode 600 and parent 700.
Reject symlink/shared/unowned paths. If editing a checkout, apply the sync gate.

Guide the user in an **unrecorded local editor**, not by sending the file to the
agent. Preserve existing data rather than overwriting it; avoid duplicate keys.
The checker permits only documented cmail keys. Unknown/runtime-control keys
such as PATH or BASH_ENV need local review and removal from the selected config;
do not silently delete them or claim they are safe to source. A private
backup is optional, also mode 600, never committed. Use `KEY='literal value'`;
quote spaces. Do not put `$()`, backticks, variable expansions, commands, multiline
values or shell snippets in config. A quote inside a value needs correct Bash
escaping; do not invent a token-containing command. Current cmail loads config
as Bash twice, so syntax validity alone does not make it safe.

Required filled keys: DOMAIN, DEST_EMAIL, ADDRESSES, CLOUDFLARE_API_TOKEN.
Set GDDY_ENV explicitly; GDDY_PAT is optional for OAuth. CF_ACCOUNT_ID and
CF_ZONE_ID are optional and must match the intended resource when set.
DRY_RUN may be 0/1; it only affects nameserver replacement, not other writes.

## Verify without executing or exposing assignments

With Python 3 available, run the bundled checker using absolute paths (resolve
`scripts/check_config.py` relative to this skill's directory):

```text
python3 <skill-directory>/scripts/check_config.py <selected-config-file>
```

This read-only check emits field names and a generic result, never values. It
accepts a deliberately narrow literal-assignment subset, including cmail's `%q`
backslash escapes; it rejects expansions, commands, unknown keys and duplicates.
Use LF-only text: CR/CRLF, other controls and Unicode line separators are rejected
before comment handling. Full-line comments are supported; inline comments, line
continuations and complex Bash are outside this conservative grammar. Single/double
quotes and escaped literals follow Bash semantics; unquoted tilde/glob/brace syntax
is rejected (quote literal characters). Some otherwise literal values containing
`$` or backticks are intentionally rejected. Parent directories must be user-controlled;
the check does not guarantee the file stays unchanged before a later runtime load.
A rejected valid-but-complex Bash file needs a **local** review/simplification,
not sourcing it to bypass the gate. It validates user ownership/mode 600 and
conservative domain/email/local-part/ID formats. It does not verify actual Gmail
ownership, credential validity, intent, resource authorization or network state.

Run `bash -n <selected-config-file> >/dev/null 2>&1` locally as a separate syntax
check; do not print syntax diagnostics containing a secret line. If Python is
missing, do not install it silently: offer consented installation or user-local
manual checks of every required field, mode, ownership, syntax and literal-only
content. Record manual evidence and limitations; do not call an unrun checker green.

Confirm no secret config is tracked before proceeding. In a source checkout use
`git check-ignore .env` and `git ls-files --error-unmatch .env` (the latter must
fail); use the actual path if different. If tracked, stop and arrange credential
rotation/removal with the user; do not stage or display it. Config outside a repo
still needs private permissions and local-only storage.
