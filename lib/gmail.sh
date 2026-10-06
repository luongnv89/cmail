# gmail.sh — guided "Send mail as" (the step that can't be OAuth'd cheaply)
# shellcheck shell=bash

gmail_sendas_guide() {
  step "Send FROM your custom address (manual, ~5 min)"
  cat <<EOF
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
EOF
  open_url "https://myaccount.google.com/apppasswords"
  open_url "https://mail.google.com/mail/u/0/#settings/accounts"
  pause
  ok "setup complete — send a test mail to ${ADDRESSES%%,*}@$DOMAIN to verify inbound"
}
