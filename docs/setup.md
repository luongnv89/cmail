# cmail setup guide (0.4.0)

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
- macOS or Linux (x86_64 or arm64); `curl` to run the installer (or Homebrew), and `git` only if you install from a clone

Already use the domain for a website or email? Note its DNS records now (step 4).

**Done when:** you can log in to your registrar, Cloudflare and both mailboxes.

- [ ] I have everything I need

### 2. Install cmail

```bash
curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"       # only if the installer says it is not on PATH
cmail --version
cmail config init
cmail config set ADDRESSES hello,contact   # optional; default is hello
```

The installer downloads the prebuilt cmail binary for your system, checks its SHA-256 checksum and puts it in
`~/.local/bin` without sudo (set `CMAIL_BIN_DIR` to choose another directory). It never runs setup.
Add the `export PATH` line to your shell profile to keep it.

Use Homebrew? `brew install luongnv89/tap/cmail` installs cmail and its shell completions instead.

Prefer to review the code first? Clone it and build that checkout (needs Rust and cargo; `cargo install --path .` works too):

```bash
git clone https://github.com/luongnv89/cmail
cd cmail
bash install.sh --local
```

**Done when:** `cmail --version` prints `cmail 0.4.0`.

- [ ] cmail is installed

### 3. Create a Cloudflare API token

Open [My Profile → API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token → Custom token. Give the token any name you will recognise (for example `cmail yourdomain.com`), then add:

| Scope | Permission | Access |
|---|---|---|
| Zone | Zone | Read (Edit only if cmail adds your domain) |
| Zone | Zone Settings | Edit |
| Zone | Email Routing Rules | Edit |
| Account | Email Routing Addresses | Edit |

Then set the resources:

| Section | Include | Value |
|---|---|---|
| Account Resources | Include | the account that owns your domain |
| Zone Resources | Include | Specific zone → your domain |

Your domain is not on Cloudflare yet? Add it first (step 4) and keep the token above. Only if you want `cmail setup` to add
the domain for you (for example in GoDaddy mode), set **Zone** to **Edit** and Zone Resources to **All zones from an account**
→ your account: a token cannot name a zone that does not exist yet. Never choose **All accounts** or **All zones**.

Why these permissions: Zone finds your domain (Edit also creates it), Zone Settings turns on Email Routing, Email Routing Rules
adds the forwarding rules and Email Routing Addresses registers your inbox. cmail never edits other DNS records, so it does not
need DNS access: Cloudflare adds the Email Routing records itself.

Copy the token. Never paste it into chat, a web page or a screenshot.

**Done when:** the token has all four permissions and is copied somewhere private.

- [ ] I created the token

### 4. If needed: add your domain to Cloudflare

**Only needed if your domain is not on Cloudflare yet.** Already listed as **Active** under Domains in Cloudflare?
Tick this step and go on: `cmail setup` will say `zone already active on Cloudflare`.

1. Open the [Cloudflare dashboard](https://dash.cloudflare.com/) → **Domains** → **Add a domain**. Enter your domain and choose the Free plan.

   Prefer the terminal? Cloudflare's own CLI, [`cf`](https://developers.cloudflare.com/cf/get-started/) (beta, needs Node.js 22 or newer),
   can add the domain instead. Copy your **Account ID** (not Zone ID) from the dashboard first:

   ```bash
   npm install -g cf
   cf auth login                     # sign in to Cloudflare in your browser
   cf zones create --account-id <account ID> --name yourdomain.com
   cf auth logout                    # cf's sign-in can do far more than cmail's token
   ```

   Either way, cmail's token can stay at **Zone: Read** (step 3). The `cf` route may not copy your existing DNS records,
   so check them carefully in the next step.
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
cmail finds your domain on Cloudflare (or adds it, if it is not there yet and your token has Zone: Edit; see step 3), waits until it is active,
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
