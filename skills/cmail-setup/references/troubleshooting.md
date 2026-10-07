# Recover without guessing

Start with the earliest failed gate and ask for the sanitized step name, exit/HTTP
status and observation time. Do not request full terminal logs, `.env`, auth status
payloads, headers, confirmation codes, screenshots or password/token values.

| Observation | Targeted repair | Original check to repeat |
|---|---|---|
| cmail not on PATH | Check selected absolute launcher; consented current-session PATH correction | `command -v cmail`, intended launcher `help` |
| Missing library / broken launcher | Reinstall from reviewed installer with same user-owned paths; existing config is preserved | Installed `help`, confirm intended runtime |
| Installer HTTPS/download failure | Check connection, proxy and upstream reachability; do not disable TLS or use HTTP | Repeat reviewed installer only after consent, then launcher help |
| Unmanaged path/symlink refused | Choose separate user-owned absolute dirs; do not delete unrelated files or bypass guard | Installer plus selected launcher help |
| Missing jq/curl/gddy | Use existing supported package manager or official gddy installer after consent; check ~/.local/bin | Each discovery/version/help check |
| Config absent/invalid/insecure | Correct selected file locally; private parent/file, literal assignments, no duplicates | Offline checker and private `bash -n` |
| GoDaddy lookup fails | Separate network, expiry, prod/ote, account and ownership; renew/login locally | Exact domain read, not just auth status |
| Purchase request timed out | Check orders, billing and domain ownership; contact support if uncertain | Exact ownership read; do not replay purchase |
| Active token but account invisible / HTTP 403 | Confirm owning account resources and operation-specific permission; optional correct CF_ACCOUNT_ID; dashboard login is not token authorization | Repeat actual-token authenticated exact-zone and owning-account address-list reads |
| Multiple accounts / stale CF_ZONE_ID | Select intended ID locally; compare domain and owner in dashboard | Gate 4 resource identity/access |
| Nameserver write fails or zone pending | Inspect actual nameservers first, DNS migration/DS plan, then wait for propagation | Fresh registrar set comparison and Cloudflare Active |
| Routing enable failed | Review Zone Settings permission and conflicting mail records; plan migration instead of deleting | Exact-domain routing enabled and DNS requirements |
| Destination still pending | Correct Gmail Inbox/Spam; consented resend expired link; keep pending destination | Owning account's exact destination verified state |
| Rule exists but wrong/disabled | Ask before correcting intended rule; preserve unrelated rules | Every alias's full enabled literal matcher/action |
| Gmail App Password unavailable | Respect policy/Advanced Protection; administrator or approved provider, no bypass | Gmail alias confirmation remains BLOCKED |
| Confirmation or inbound missing | Recheck active zone/routing, verified destination and exact rules; resend only with consent | Confirmed alias and independent inbound arrival |
| Outbound rejected/not delivered | Check smtp.gmail.com, 587/TLS, full username and private current App Password; recipient Spam | Independent recipient arrival and exact custom From |

HTTP 401/403 is not propagation. HTTP 429 requires waiting before rechecking; 5xx
or transport errors are unknown service outcomes, not automatic invalid credentials.
For uncertain writes inspect provider post-state before retrying. Do not repeatedly
run setup, enable DRY_RUN as a global safety switch or delete state to start over.

If the user pasted a credential, avoid quoting it back. Advise revocation/rotation
in the relevant provider, local replacement, and recheck the affected gate and its
dependents. Chat deletion alone is not credential rotation.

After three targeted unsuccessful repairs, report BLOCKED with the evidence,
what remains unknown, the exact next check and any administrator/support action.
For delayed DNS report PENDING without attempting dependent routing/DNS writes.
Resume at the failed gate after revalidating changed prerequisites. Never say
“setup complete” while Gmail confirmation or either delivery direction is unverified.
