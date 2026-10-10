# cmail setup guide (0.2.0)

[Home](index.html) · [Interactive guide](setup.html) · [CLI docs](docs.html) · [Changelog](changelog.html) · [Privacy](privacy.html)

Get `hello@your-domain` delivered to the inbox you already use in a few simple steps (8 in total).
Do them in order and tick each one when its **Done when** check passes.
`cmail setup` can be rerun at any time; finished steps are skipped.

```text
1 Prepare → 2 Install → 3 Token → 4 Run setup → 5 Nameservers → 6 Verify inbox → 7 Test → 8 Send (optional)
```

### 1. Check you have everything

- A domain you own, at any registrar
- A free Cloudflare account
- The inbox that should receive the mail (any provider)
- A second mailbox to send a test from
- macOS or Linux with `bash`, `curl`, `jq` and `git`

Already use the domain for a website or email? Note its DNS records now (step 5).

**Done when:** you can log in to your registrar, Cloudflare and both mailboxes.

- [ ] I have everything I need

### 2. Install cmail

```bash
git clone https://github.com/luongnv89/cmail
cd cmail
bash install.sh --local
export PATH="$HOME/.local/bin:$PATH"
cmail --version
cmail config init
cmail config set ADDRESSES hello,contact   # optional; default is hello
```

**Done when:** `cmail --version` prints `cmail 0.2.0`.

- [ ] cmail is installed

### 3. Create a Cloudflare API token

Open [My Profile → API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token → Custom token, and add:

| Scope | Permission | Access |
|---|---|---|
| Zone | Zone | Edit |
| Zone | Zone Settings | Edit |
| Zone | DNS | Edit |
| Zone | Email Routing Rules | Edit |
| Account | Email Routing Addresses | Edit |

Zone Resources: All zones from an account → your account. Account Resources: the account that owns your domain.
Copy the token. Never paste it into chat, a web page or a screenshot.

**Done when:** the token has all five permissions and is copied somewhere private.

- [ ] I created the token

### 4. Run `cmail setup`

```bash
cmail setup
```

Answer two questions (receiving inbox, your domain), then paste the token.
cmail creates the zone, enables Email Routing and adds a rule per address.
Want a preview first? `cmail setup --dry-run` changes nothing.

**Done when:** setup is running past the token step.

- [ ] Setup is running

### 5. Point your domain at Cloudflare

Skip if setup says `zone already active on Cloudflare`. Otherwise, at your registrar:

1. Copy the DNS records you still need (website, MX, TXT) into Cloudflare DNS.
2. Turn off DNSSEC (remove DS records).
3. Replace **all** nameservers with the two cmail printed.

cmail waits up to 20 minutes. Propagation can take 24–48 hours; if the wait ends, rerun `cmail setup`.

**Done when:** cmail prints `✓ zone active`.

- [ ] The zone is active

### 6. Click the verification email

Open your receiving inbox (check Spam) and click **Verify email address** in Cloudflare's email.
cmail notices and finishes.

**Done when:** the terminal shows `Receiving is set up`.

- [ ] Setup finished

### 7. Send yourself a test

From a **different** mailbox, email `hello@your-domain` and check it arrives (and Spam). `cmail list` shows every address.
A test sent from the receiving inbox itself is not proof: some providers drop it.

**Done when:** a test message arrives for every address.

- [ ] Test emails arrived

### 8. Optional: send from your address

Sending is optional: skip if you only need to receive. Needs Gmail. Google has announced it will remove
third-party "Send as" starting **January 2027**; check [Google's help](https://support.google.com/mail/answer/22370) first.

Run `cmail send-as`, create a Google App Password, then in Gmail → Settings → Accounts and Import → Send mail as, use
`smtp.gmail.com`, port `587`, TLS, your Gmail address and the App Password.
App Passwords may be unavailable on work/school accounts or with Advanced Protection.

**Done when:** mail sent "from" your address reaches another mailbox, or you skipped this step.

- [ ] Sending works, or I skipped it

## Stuck?

Read the `Setup stopped at:` line, fix that step and rerun `cmail setup`.
`cmail status` and `cmail doctor` show the current state. See the [CLI docs](docs.html).

## Local preview

From the repository root: `python3 -m http.server 8000 --bind 127.0.0.1`, then open `http://127.0.0.1:8000/docs/`.
