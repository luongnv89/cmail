# cmail setup guide (0.2.0)

[Home](index.html) · [Interactive guide](setup.html) · [CLI docs](docs.html) · [Changelog](changelog.html) · [Privacy](privacy.html)

Get `hello@your-domain` delivered to the inbox you already use in a few simple steps (8 in total).
Do them in order and tick each one when its **Done when** check passes.
`cmail setup` can be rerun at any time; finished steps are skipped.

```text
1 Prepare → 2 Install → 3 Token → 4 Add domain (if needed) → 5 Run setup → 6 Verify inbox → 7 Test → 8 Send (optional)
```

### 1. Check you have everything

- A domain you own, at any registrar
- A free Cloudflare account
- The inbox that should receive the mail (any provider)
- A second mailbox to send a test from
- macOS or Linux with `bash`, `curl`, `jq` and `git`

Already use the domain for a website or email? Note its DNS records now (step 4).

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

### 4. If needed: add your domain to Cloudflare

**Only needed if your domain is not on Cloudflare yet.** Already listed as **Active** under Domains in Cloudflare?
Tick this step and go on: `cmail setup` will say `zone already active on Cloudflare`.

1. Open the [Cloudflare dashboard](https://dash.cloudflare.com/) → **Domains** → **Add a domain**. Enter your domain and choose the Free plan.
2. Check the DNS records Cloudflare found. Add any you still need (website, MX, TXT).
3. Follow Cloudflare's instructions to switch nameservers at your current registrar: turn off DNSSEC (remove DS records)
   first, then replace **all** nameservers with the two Cloudflare shows.

Propagation can take 24–48 hours. You do not have to wait here: `cmail setup` (step 5) waits up to 20 minutes, and you can rerun it any time.

**Done when:** your domain is listed in Cloudflare and your registrar uses Cloudflare's two nameservers (it may still show Pending).

- [ ] My domain is on Cloudflare

### 5. Run `cmail setup`

```bash
cmail setup
```

Answer two questions (receiving inbox, your domain), then paste the token.
cmail finds your domain on Cloudflare (or adds it, if it is not there yet), waits until it is active,
enables Email Routing and adds a rule per address. If the nameservers are still switching, it prints them (step 4) and waits.
Want a preview first? `cmail setup --dry-run` changes nothing.

**Done when:** setup is running past the token step.

- [ ] Setup is running

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

## All done

Congratulations, you are all set! If cmail saved you some time, please
[star the project on GitHub](https://github.com/luongnv89/cmail). It helps other people find it.

## Stuck?

Read the `Setup stopped at:` line, fix that step and rerun `cmail setup`.
`cmail status` and `cmail doctor` show the current state. See the [CLI docs](docs.html).

## Local preview

From the repository root: `python3 -m http.server 8000 --bind 127.0.0.1`, then open `http://127.0.0.1:8000/docs/`.
