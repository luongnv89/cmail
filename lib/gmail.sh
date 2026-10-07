# gmail.sh — optional guided "Send mail as" (the step that can't be OAuth'd cheaply)
# shellcheck shell=bash

gmail_sendas_guide() {
  step "Send FROM your custom address (optional, manual, ~5 min)"
  cat <<EOF
Only needed if you want to SEND from your custom address. Receiving already
works without it. This guide needs $DEST_EMAIL to be a Gmail/Google account
that can use App Passwords.

Automating Gmail aliases needs Google's restricted gmail.settings.* scope
(a verified OAuth app — overkill here). Do it once by hand:

  1. Gmail -> Settings -> See all settings -> "Accounts and Import"
  2. "Send mail as" -> "Add another email address"
  3. Name + your custom address (first of: ${ADDRESSES%%,*}@$DOMAIN)
  4. SMTP settings — IMPORTANT, replace what Gmail pre-fills:
       SMTP server : smtp.gmail.com
       Port        : 587
       Username    : $DEST_EMAIL
       Password    : Google App Password (NOT your Gmail password)
         -> Google Account -> Security -> 2-Step Verification
            -> App passwords -> generate one for "Mail"
  5. Gmail emails a confirmation code to your custom address — it lands
     back in your Gmail via Cloudflare forwarding. Paste the code.

Repeat per extra address, or use "Send mail as" -> make default.

If blocked:
  - App passwords unavailable: enable 2-Step Verification on the SMTP
    account. Work/school policy, Advanced Protection or security-key-only
    settings may prevent App Passwords; ask your administrator or use an
    approved SMTP provider. Do not disable security controls to work around it.
  - SMTP rejected: check server/port, TLS, the full account username and a
    current App Password (not your normal password). If revoked, generate a
    new one privately. Check account security alerts or ask your administrator.
    Retry "Add another email address" after resolving the SMTP issue.
  - Confirmation missing: check Spam/All Mail, verify the Cloudflare
    destination is confirmed, the address rule points to it, and Email Routing
    and DNS/MX are active. Resolve any pending steps with ./cmail setup, then
    resend the Gmail confirmation (./cmail status shows the saved state). Do not mark the alias ready without it.

Verify from a DIFFERENT mailbox (not $DEST_EMAIL):
  - Send to ${ADDRESSES%%,*}@$DOMAIN and confirm it arrives at $DEST_EMAIL.
  - Send from Gmail using the custom From address to that different mailbox;
    check delivery, the From address, Spam and replies back to your alias.
EOF
  open_url "https://myaccount.google.com/apppasswords"
  open_url "https://mail.google.com/mail/u/0/#settings/accounts"
  pause || die "Gmail guide paused without input — finish the manual steps in Gmail settings, then run ./cmail send-as in an interactive terminal to resume; confirmation and mailbox tests are not automatically verified"
  note "manual Gmail setup is not automatically verified — complete confirmation and both mailbox tests above; re-open Gmail settings to resume if needed"
}
