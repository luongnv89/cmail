//! `cmail setup`: guided receiving setup, its read-only `--dry-run` plan, and
//! recovery guidance when a step fails or the run is interrupted.

use crate::cli::SetupArgs;
use crate::cloudflare::{account_recovery, nonempty_str, Cf};
use crate::config::{self, Config, Overrides};
use crate::error::{config_error, die, usage, Error, Result};
use crate::godaddy::{self, normalize_nameservers, Io};
use crate::output::{self, check, checks_json, checks_text, envelope, Check};
use crate::style::{boxed, clean, span, table, Role};
use crate::{find_in_path, term, ui};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

static STARTED: OnceLock<Instant> = OnceLock::new();
/// 0: no nameserver step yet; 1: GoDaddy update reached; 2: manual delegation (never changed by cmail).
static DNS_CHECKPOINT: AtomicU8 = AtomicU8::new(0);

fn elapsed_seconds() -> u64 {
    STARTED.get().map_or(0, |s| s.elapsed().as_secs())
}

/// Printed once when setup stops early, including interrupts. Never prints
/// failed commands or values: they may contain credentials.
fn recovery() {
    let step = ui::current_step();
    let next = if step.starts_with("Dependencies") {
        "Next: install the missing tool using your OS package manager; check network/sudo access and PATH.".to_string()
    } else if step.starts_with("Configuration") {
        "Next: set DOMAIN, DEST_EMAIL and ADDRESSES with cmail config set (a bare domain such as example.com; local parts only, e.g. hello,contact). Keep the config private.".into()
    } else if step.starts_with("GoDaddy authentication") {
        let env = std::env::var("GDDY_ENV").ok().filter(|v| !v.is_empty()).unwrap_or_else(|| "prod".into());
        format!("Next: run gddy auth login --env {env} and complete browser consent; replace an expired GDDY_PAT in your config if using a PAT.")
    } else if step.starts_with("Choose domain") {
        "Next: check the domain is in the correct GoDaddy account/environment. Check orders before retrying a purchase; set DOMAIN in your config once owned.".into()
    } else if step.starts_with("Cloudflare API token") {
        "Next: open https://dash.cloudflare.com/profile/api-tokens. Replace an invalid/expired CLOUDFLARE_API_TOKEN in your config; for network/service errors, fix connectivity before changing the token.".into()
    } else if step.starts_with("Cloudflare zone:") {
        "Next: check token Account Resources and Zone Resources at https://dash.cloudflare.com/profile/api-tokens. For account discovery problems, set CF_ACCOUNT_ID from the dashboard in your config; this does not grant permissions.".into()
    } else if step.starts_with("Registrar nameservers") {
        "Next: at your domain registrar, replace ALL nameservers with the Cloudflare-assigned ones (Cloudflare > domain > Overview). Copy needed DNS records into Cloudflare and turn off DNSSEC first.".into()
    } else if step.starts_with("GoDaddy: point") {
        "Next: open GoDaddy > domain > DNS > Nameservers and compare with Cloudflare > domain > Overview. If an update failed, verify its outcome before retrying.".into()
    } else if step.starts_with("Waiting for zone activation") {
        "Next: compare the nameservers at your domain registrar with those on Cloudflare Overview. Wait for propagation (up to 24–48 hours); an API/auth failure is not propagation.".into()
    } else if step.starts_with("Enable Cloudflare Email Routing") {
        "Next: open Cloudflare > domain > Email > Email Routing. Check token Zone Settings:Edit and DNS conflicts; do not remove existing mail-provider records blindly.".into()
    } else if step.starts_with("Destination address:") {
        "Next: check the destination Inbox/Spam and click Cloudflare's verification link. Resend missing/expired links from Email Routing > Destination addresses; token needs Account > Email Routing Addresses > Edit.".into()
    } else if step.starts_with("Forwarding addresses") {
        "Next: open Cloudflare > domain > Email > Email Routing > Routing rules. Check enabled rules point to DEST_EMAIL and token has Zone > Email Routing Rules > Edit. Earlier rules may already exist.".into()
    } else {
        "Next: check the error above, configuration file permissions and required tools.".into()
    };
    let dns = match DNS_CHECKPOINT.load(Ordering::SeqCst) {
        1 => "Nameserver step was reached; delegation may already have changed. No rollback was attempted.",
        2 => "cmail never changes nameservers in manual registrar mode; only changes you made at your registrar apply. No rollback was attempted.",
        _ => "This run has not attempted a nameserver update. Earlier resources/configuration may have been saved.",
    };
    ui::always(&format!(
        "\nSetup stopped at: {step}\n    {next}\n    {dns}\n    After fixing the cause, rerun cmail setup. Use cmail status to inspect saved Cloudflare state; never share your config or tokens.\n"
    ));
}

fn interrupted() {
    recovery();
    ui::always(&format!("Elapsed time: {}\n", output::elapsed(elapsed_seconds())));
}

pub fn setup(path: PathBuf, args: &SetupArgs) -> Result<()> {
    let _ = STARTED.set(Instant::now());
    ui::step_silently("Configuration file");
    term::set_interrupt_hook(Some(interrupted));
    let result = run(path, args);
    term::set_interrupt_hook(None);
    match result {
        Ok(()) => Ok(()),
        Err(error @ Error::Usage(_)) => Err(error),
        Err(error) => {
            let code = ui::report(&error);
            recovery();
            ui::always(&format!("Elapsed time: {}\n", output::elapsed(elapsed_seconds())));
            Err(Error::Exit(if matches!(code, 2 | 3 | 130 | 143) { code } else { 1 }))
        }
    }
}

fn run(path: PathBuf, args: &SetupArgs) -> Result<()> {
    let overrides = Overrides {
        domain: args.domain.clone(),
        destination: args.destination.clone(),
        addresses: args.addresses.clone(),
        registrar: args.registrar.map(|r| r.as_str().to_string()),
    };
    let mut config = match Config::load(path.clone(), &overrides) {
        Ok(config) => config,
        Err(error) => {
            ui::report(&error);
            ui::always("cmail: could not load config; correct the selected private configuration.\n");
            return Err(Error::Exit(3));
        }
    };
    if args.dry_run || config.get("DRY_RUN") == "1" {
        return plan(&config);
    }
    if ui::ctx().json {
        return usage("JSON setup output requires --dry-run");
    }
    if !term::stdin_is_tty() {
        return usage("setup requires terminal input; run it interactively, or use setup --dry-run in scripts");
    }
    let godaddy = config.registrar() == "godaddy";
    if godaddy && ui::ctx().no_browser && config.get("GDDY_PAT").is_empty() {
        return config_error("--no-browser setup requires an existing GDDY_PAT to prevent automatic GoDaddy OAuth");
    }
    ui::log("Setting up RECEIVING: your custom addresses will forward to an inbox you already use.");
    ui::note("Sending is optional and not part of this setup (cmail send-as, only if you want it).");
    ui::step("Dependencies");
    if godaddy {
        if find_in_path("gddy").is_none() {
            return die("gddy missing — Install manually: https://developer.godaddy.com/en/docs/api-users/cli/set-up; check GitHub/network access, add ~/.local/bin to PATH, then re-run cmail setup");
        }
        ui::ok("gddy present");
    } else {
        ui::ok("no external tools needed in manual registrar mode");
    }
    ui::step("Configuration");
    config::ensure_file(&path)?;
    config = match Config::load(path, &overrides) {
        Ok(config) => config,
        Err(error) => {
            ui::report(&error);
            ui::always("cmail: could not load config; use literal NAME=value assignments and valid shell assignment syntax, without sharing secrets; re-run cmail setup.\n");
            return Err(Error::Exit(3));
        }
    };
    if let Some(domain) = &args.domain {
        config.set("DOMAIN", &domain.to_ascii_lowercase())?;
        config.set("CF_ZONE_ID", "")?;
    }
    if let Some(registrar) = args.registrar {
        config.set("REGISTRAR", registrar.as_str())?;
    }
    if let Some(destination) = &args.destination {
        config.set("DEST_EMAIL", destination)?;
    }
    if let Some(addresses) = &args.addresses {
        config.set("ADDRESSES", addresses)?;
    }
    // Collect what we're building early, so all prompts happen up front.
    require(&mut config, "DEST_EMAIL", "email address to receive forwarded mail (any provider)", false)?;
    require(&mut config, "ADDRESSES", "addresses to create, comma-separated (e.g. hello,contact,me)", false)?;
    if godaddy {
        // Opt-in registrar automation; the only path that can offer a domain purchase.
        godaddy::ensure_auth(&config)?;
        godaddy::pick_domain(&mut config)?;
    } else {
        // Default: an existing domain at any registrar; no gddy or GoDaddy login.
        require(&mut config, "DOMAIN", "domain you already own, at any registrar (e.g. example.com)", false)?;
    }
    let mut cf = Cf::new(&config)?;
    ensure_token(&mut config, &mut cf)?;
    let (zone, nameservers) = zone_ensure(&config, &cf)?;
    config.set("CF_ZONE_ID", &zone)?;
    if godaddy {
        DNS_CHECKPOINT.store(1, Ordering::SeqCst);
        godaddy::set_nameservers(&config, &nameservers)?;
    } else {
        DNS_CHECKPOINT.store(2, Ordering::SeqCst); // instructions only: cmail never changes delegation here
        manual_delegation(&config, &cf, &zone)?;
    }
    wait_active(&cf, &zone, &nameservers)?;
    email_enable(&cf, &zone)?;
    destination_ensure(&config, &cf, &zone)?;
    rules_ensure(&config, &cf, &zone)?;
    summary(&config);
    Ok(())
}

fn require(config: &mut Config, key: &str, prompt: &str, secret: bool) -> Result<()> {
    if !config.get(key).is_empty() {
        return Ok(());
    }
    let Some(value) = ui::ask(prompt, secret) else {
        return die(format!(
            "{key} input unavailable — run cmail setup in an interactive terminal, or set {key} in your private config first"
        ));
    };
    if value.is_empty() {
        return die(format!(
            "{key} is required — enter a non-empty value when re-running cmail setup, or set {key} in your private config first; do not share secret values"
        ));
    }
    if !config::field_valid(key, &value) {
        return if key == "DOMAIN" {
            config_error("DOMAIN must be a domain name without a scheme or path")
        } else {
            config_error(format!("{key} has an invalid value"))
        };
    }
    let value = if key == "DOMAIN" { value.to_ascii_lowercase() } else { value };
    config.set(key, &value)
}

fn ensure_token(config: &mut Config, cf: &mut Cf) -> Result<()> {
    ui::step("Cloudflare API token");
    let mut token = config.get("CLOUDFLARE_API_TOKEN").to_string();
    loop {
        if !token.is_empty() {
            let response = cf.get("/user/tokens/verify")?;
            let Some(state) = nonempty_str(&response["result"]["status"]) else {
                return die("Cloudflare returned no token status — check https://www.cloudflarestatus.com/ before replacing credentials");
            };
            if state == "active" {
                break;
            }
            ui::warn(&format!("token is '{state}' — create an active replacement token"));
        }
        ui::always(
            "Cloudflare has no self-service OAuth for scripts — a scoped API token is
needed once. Create it now (browser will open):

  1. \"Create token\" -> \"Custom token\" -> \"Get started\"
     Token name: any label you will recognise (e.g. cmail <your domain>)
  2. Permissions (four rows):
       Zone    | Zone                    | Read (Edit if cmail adds the domain)
       Zone    | Zone Settings           | Edit
       Zone    | Email Routing Rules     | Edit
       Account | Email Routing Addresses | Edit
  3. Account Resources: Include -> <the account that owns your domain>
     Zone Resources:
       domain already on Cloudflare: Include -> Specific zone -> <your domain>
       cmail adds the domain:        Include -> All zones from an account -> <that account>
     Never choose All accounts or All zones.
  4. Create token, copy it, paste below (input hidden).

",
        );
        ui::open_url("https://dash.cloudflare.com/profile/api-tokens");
        let Some(pasted) = ui::ask("paste Cloudflare API token", true) else {
            return die("no token input — run cmail setup in an interactive terminal or set CLOUDFLARE_API_TOKEN with cmail config set CLOUDFLARE_API_TOKEN --stdin");
        };
        if pasted.is_empty() {
            return die("token required — create a custom API token at https://dash.cloudflare.com/profile/api-tokens and rerun cmail setup");
        }
        token = pasted;
        cf.set_token(&token);
    }
    config.set("CLOUDFLARE_API_TOKEN", &token)?;
    ui::ok("Cloudflare token verified and saved to .env");
    ui::note("Token is active; account/zone permissions are checked by the following steps.");
    Ok(())
}

fn valid_nameservers(zone: &Value) -> Option<Vec<String>> {
    let list = zone["result"]["name_servers"].as_array()?;
    if list.len() < 2 || !list.iter().all(|n| nonempty_str(n).is_some()) {
        return None;
    }
    Some(list.iter().map(|n| n.as_str().unwrap().to_string()).collect())
}

fn zone_ensure(config: &Config, cf: &Cf) -> Result<(String, Vec<String>)> {
    let domain = config.get("DOMAIN");
    ui::step(&format!("Cloudflare zone: {domain}"));
    let response = cf.get(&format!("/zones?name={domain}"))?;
    let Some(zones) = response["result"].as_array() else {
        return die("Cloudflare returned an invalid zone list — no zone created or nameservers changed");
    };
    let mut zone_id = zones.first().and_then(|z| z["id"].as_str()).unwrap_or("").to_string();
    if zone_id.is_empty() {
        let mut account = config.get("CF_ACCOUNT_ID").to_string();
        if account.is_empty() {
            let response = cf.get("/accounts")?;
            let Some(accounts) = response["result"].as_array() else {
                return die("Cloudflare returned an invalid account list — no zone created or nameservers changed");
            };
            match accounts.len() {
                0 => {
                    account_recovery(domain);
                    return die("no Cloudflare account visible to token — no zone created or nameservers changed");
                }
                1 => {}
                _ => {
                    ui::warn("multiple Cloudflare accounts visible; refusing to choose one automatically");
                    let listed: String = accounts
                        .iter()
                        .map(|a| {
                            format!("  {}: {}\n", a["name"].as_str().unwrap_or(""), a["id"].as_str().unwrap_or(""))
                        })
                        .collect();
                    ui::always(&listed);
                    account_recovery(domain);
                    return die("set CF_ACCOUNT_ID to the intended account — no zone created or nameservers changed");
                }
            }
            account = match nonempty_str(&accounts[0]["id"]) {
                Some(id) => id.to_string(),
                None => return die("Cloudflare account has no valid ID — no zone created or nameservers changed"),
            };
        }
        if !config::field_valid("CF_ACCOUNT_ID", &account) {
            return die(
                "CF_ACCOUNT_ID must be the 32-character account ID from the Cloudflare dashboard, not the account name",
            );
        }
        ui::log(&format!("creating zone {domain} in account {account}"));
        let created = cf.request("POST", "/zones", Some(&json!({"name": domain, "account": {"id": account}})), None)?;
        zone_id = match nonempty_str(&created["result"]["id"]) {
            Some(id) => id.to_string(),
            None => return die("Cloudflare did not confirm zone creation — check the dashboard before retrying"),
        };
    } else {
        ui::ok("zone already exists");
    }
    let zone = cf.get(&format!("/zones/{zone_id}"))?;
    let Some(nameservers) = valid_nameservers(&zone) else {
        return die("Cloudflare returned no valid nameservers — open the domain Overview in Cloudflare; no nameserver change applied");
    };
    ui::ok(&format!("zone {zone_id} — nameservers: {}", nameservers.join(" ")));
    Ok((zone_id, nameservers))
}

fn zone_status(zone: &Value) -> Result<String> {
    match nonempty_str(&zone["result"]["status"]) {
        Some(status) => Ok(status.to_string()),
        None => die("Cloudflare returned no zone status — check the domain Overview in the dashboard"),
    }
}

/// Registrar-independent instructions; cmail never changes delegation here.
fn manual_delegation(config: &Config, cf: &Cf, zone_id: &str) -> Result<()> {
    let domain = config.get("DOMAIN");
    ui::step(&format!("Registrar nameservers: {domain}"));
    let zone = cf.get(&format!("/zones/{zone_id}"))?;
    let status = zone_status(&zone)?;
    if status == "active" {
        ui::ok("zone already active on Cloudflare — no registrar changes needed");
        return Ok(());
    }
    let Some(nameservers) = valid_nameservers(&zone) else {
        return die("Cloudflare returned no valid nameservers — open the domain Overview in Cloudflare; no nameserver change applied");
    };
    ui::warn(&format!(
        "zone is '{status}' — update the nameservers at your domain registrar yourself (cmail does not change them)"
    ));
    let listed: String = nameservers.iter().map(|n| format!("  {n}\n")).collect();
    let wait = ui::ctx().wait_timeout;
    // Printed even with --quiet: the user must act on these instructions.
    ui::always(&format!(
        "
Cloudflare assigned these nameservers to {domain}:
{listed}
Before switching (services still using the old DNS host stop resolving otherwise):
  1. Copy every DNS record you still need (website A/AAAA/CNAME, MX, TXT such as
     SPF/DKIM/verification, and any others) into Cloudflare > {domain} > DNS.
  2. Turn off DNSSEC at your registrar (remove DS records) before switching;
     re-enable it from Cloudflare after the zone is active.
Then:
  3. Log in to your domain registrar, open the nameserver settings for {domain},
     and replace ALL nameservers with exactly the ones listed above.
  4. Save. cmail now checks Cloudflare activation for up to {wait}s.
     Propagation can take 24–48 hours; if the wait ends first, rerun cmail setup.
"
    ));
    Ok(())
}

fn remaining(deadline: Instant) -> u64 {
    deadline.saturating_duration_since(Instant::now()).as_secs_f64().ceil() as u64
}

fn wait_active(cf: &Cf, zone_id: &str, nameservers: &[String]) -> Result<()> {
    ui::step("Waiting for zone activation (nameserver propagation)");
    let limit = ui::ctx().wait_timeout;
    let deadline = Instant::now() + Duration::from_secs(limit);
    let mut status = String::new();
    for _ in 0..limit.div_ceil(20) {
        let left = remaining(deadline);
        if left == 0 {
            break;
        }
        let zone = cf.request("GET", &format!("/zones/{zone_id}"), None, Some(left))?;
        status = zone_status(&zone)?;
        match status.as_str() {
            "active" => {
                ui::ok("zone active");
                return Ok(());
            }
            "pending" | "initializing" => {}
            other => {
                return die(format!(
                    "zone status '{other}' needs attention — open the domain Overview in Cloudflare before retrying"
                ))
            }
        }
        let left = remaining(deadline);
        if left == 0 {
            break;
        }
        let delay = left.min(20);
        ui::note(&format!("status: {status} — retrying in {delay}s"));
        term::sleep(delay);
    }
    let shown = if nameservers.is_empty() { "see dashboard".to_string() } else { nameservers.join(" ") };
    die(format!(
        "zone still '{status}' after {limit}s — compare the nameservers at your domain registrar with Cloudflare Overview nameservers ({shown}). Propagation can take 24–48 hours; rerun cmail setup once Cloudflare shows Active. Any nameserver change already made stays in place; no rollback was attempted"
    ))
}

fn email_enable(cf: &Cf, zone_id: &str) -> Result<()> {
    ui::step("Enable Cloudflare Email Routing");
    let routing = cf.get(&format!("/zones/{zone_id}/email/routing"))?;
    let Some(enabled) = routing["result"]["enabled"].as_bool() else {
        return die("Cloudflare Email Routing settings missing a valid enabled state — no change applied");
    };
    if enabled {
        ui::ok("email routing already enabled");
        return Ok(());
    }
    // https://developers.cloudflare.com/api/resources/email_routing/subresources/dns/methods/create/
    let response = cf.request("POST", &format!("/zones/{zone_id}/email/routing/dns"), Some(&json!({})), None)?;
    if response["result"]["enabled"] != true {
        return die("Cloudflare did not confirm Email Routing is enabled — check the zone in the dashboard");
    }
    ui::ok("email routing enabled (Cloudflare routing DNS records added and locked)");
    Ok(())
}

/// Register the destination if needed and wait for the user to click Cloudflare's link.
fn destination_ensure(config: &Config, cf: &Cf, zone_id: &str) -> Result<()> {
    let dest = config.get("DEST_EMAIL");
    let domain = config.get("DOMAIN");
    ui::step(&format!("Destination address: {dest}"));
    let account = cf.account_for_zone(zone_id)?;
    let find = |list: &[Value]| list.iter().find(|d| d["email"].as_str() == Some(dest)).cloned();
    let destination = match find(&cf.addresses(&account, None)?) {
        Some(found) => {
            if found["verified"].is_null() {
                ui::warn(&format!(
                    "{dest} already registered but unverified — click the existing Cloudflare verification email"
                ));
            }
            found
        }
        None => {
            let response = cf.register_destination(&account, dest)?;
            let r = &response["result"];
            if r["email"].as_str() != Some(dest) || !(r["verified"].is_null() || nonempty_str(&r["verified"]).is_some())
            {
                return die("Cloudflare did not confirm destination registration");
            }
            ui::warn(&format!("verification email sent to {dest} — click the Cloudflare link"));
            r.clone()
        }
    };
    let mut verified = nonempty_str(&destination["verified"]).is_some();
    if !verified {
        ui::note(&format!("Sign into the {dest} mailbox and check Inbox and Spam for Cloudflare's verification link."));
        ui::note(&format!(
            "Missing or expired link? Open Cloudflare > {domain} > Email > Email Routing > Destination addresses and resend verification."
        ));
        if dest.ends_with("@gmail.com") || dest.ends_with("@googlemail.com") {
            ui::open_url("https://mail.google.com/");
        }
        let limit = ui::ctx().wait_timeout;
        let deadline = Instant::now() + Duration::from_secs(limit);
        for _ in 0..limit.div_ceil(15) {
            let left = remaining(deadline);
            if left == 0 {
                break;
            }
            term::sleep(left.min(15));
            let left = remaining(deadline);
            if left == 0 {
                break;
            }
            verified =
                find(&cf.addresses(&account, Some(left))?).is_some_and(|d| nonempty_str(&d["verified"]).is_some());
            if verified {
                break;
            }
            ui::note("still unverified — waiting (click the email link)…");
        }
        if !verified {
            return die(format!(
                "{dest} not verified after {limit}s — check Inbox/Spam in the correct mailbox, resend an expired/missing link from Cloudflare Email Routing > Destination addresses, then rerun cmail setup after clicking it. The pending destination is kept"
            ));
        }
    }
    ui::ok(&format!("{dest} verified"));
    Ok(())
}

/// Rules whose matchers include exactly `address` (setup compares case-sensitively).
fn exact_matches<'a>(rules: &'a [Value], address: &str) -> Vec<&'a Value> {
    rules
        .iter()
        .filter(|r| r["matchers"].as_array().is_some_and(|ms| ms.iter().any(|m| m["value"].as_str() == Some(address))))
        .collect()
}

fn rule_is_ready(matches: &[&Value], address: &str, dest: &str) -> bool {
    matches!(matches, [r] if r["enabled"] == true
        && r["matchers"] == json!([{"type": "literal", "field": "to", "value": address}])
        && r["actions"] == json!([{"type": "forward", "value": [dest]}]))
}

fn rules_ensure(config: &Config, cf: &Cf, zone_id: &str) -> Result<()> {
    let (domain, dest) = (config.get("DOMAIN"), config.get("DEST_EMAIL"));
    ui::step(&format!("Forwarding addresses ({} -> {dest})", config.get("ADDRESSES")));
    let mut rules = cf.rules(zone_id)?;
    let mut priority = 0;
    for local in config.addresses() {
        let address = format!("{local}@{domain}");
        let matches = exact_matches(&rules, &address);
        if !matches.is_empty() {
            if !rule_is_ready(&matches, &address, dest) {
                return die(format!(
                    "{address} has an existing disabled, conflicting, or different forwarding rule — open Cloudflare > {domain} > Email > Email Routing > Routing rules and enable/correct it to forward to {dest}, then rerun cmail setup. Existing rules were not overwritten"
                ));
            }
            ui::ok(&format!("{address} already exists"));
            continue;
        }
        let payload = json!({
            "name": format!("fwd {address}"), "enabled": true, "priority": priority,
            "matchers": [{"type": "literal", "field": "to", "value": address}],
            "actions": [{"type": "forward", "value": [dest]}],
        });
        cf.request("POST", &format!("/zones/{zone_id}/email/routing/rules"), Some(&payload), None)?;
        rules.push(payload);
        ui::ok(&format!("{address} -> {dest}"));
        priority += 1;
    }
    Ok(())
}

fn summary(config: &Config) {
    let (domain, dest) = (config.get("DOMAIN"), config.get("DEST_EMAIL"));
    let addresses = config.addresses();
    let first = addresses.first().cloned().unwrap_or_default();
    let elapsed = output::elapsed(elapsed_seconds());
    let mode = ui::ctx().out;
    if mode.styled {
        let rows: Vec<_> = addresses
            .iter()
            .map(|a| {
                vec![
                    vec![span(Role::Text, clean(&format!("{a}@{domain}"), false))],
                    vec![span(Role::Dim, mode.g().arrow)],
                    vec![span(Role::Text, clean(dest, false))],
                ]
            })
            .collect();
        print!("\n{}", boxed(&mode, "Receiving is set up", Some(&format!("Elapsed time: {elapsed}")), &[table(&rows)]));
    } else {
        let mut text = String::from("\nReceiving is set up\n");
        for a in &addresses {
            text.push_str(&format!("  {a}@{domain} -> {dest}\n"));
        }
        text.push_str(&format!("\nElapsed time: {elapsed}\n"));
        print!("{text}");
    }
    println!(
        "Test it: from a DIFFERENT mailbox (not {dest}), send to {first}@{domain} and check delivery (including Spam)."
    );
    println!("Delivery is not verified automatically. Sending is optional: cmail send-as");
}

/// Read-only setup plan: no authentication flows, writes, prompts, or browser calls.
fn plan(config: &Config) -> Result<()> {
    config.ready()?;
    let cf = Cf::new(config)?;
    let (domain, dest) = (config.get("DOMAIN").to_string(), config.get("DEST_EMAIL").to_string());
    let registrar = config.registrar().to_string();
    let mut actions: Vec<Check> = Vec::new();
    let mut act = |name: &str, state: &str, message: &str, next: &str| actions.push(check(name, state, message, next));
    act(
        "config",
        "planned",
        "Setup will save explicit settings and discovered resource IDs in private configuration.",
        "",
    );
    let token = cf.get("/user/tokens/verify")?;
    let Some(state) = token["result"]["status"].as_str() else { return die("Cloudflare token status missing") };
    if state != "active" {
        return die("Cloudflare token is not active; replace it locally before setup");
    }
    act("cloudflare", "ready", "Cloudflare token active; read access is checked below.", "");
    // gddy can start OAuth even during reads when scopes are missing; only a
    // supplied PAT guarantees a read-only GoDaddy check.
    let mut current: Vec<String> = Vec::new();
    if registrar != "godaddy" {
        act(
            "registrar",
            "ready",
            "Manual registrar mode: no GoDaddy access or gddy needed; you update nameservers at your registrar.",
            "",
        );
    } else if !config.get("GDDY_PAT").is_empty() {
        if find_in_path("gddy").is_none() {
            return die("gddy missing; install it before checking GoDaddy domain access");
        }
        let env = config.get("GDDY_ENV").to_string();
        let (ok, out) = godaddy::gddy(config, &["domain", "get", &domain, "--env", &env, "--json"], Io::Capture);
        if ok {
            match godaddy::current_nameservers(&out) {
                Some(list) => current = list,
                None => return die("GoDaddy returned invalid nameservers; check domain access"),
            }
            act("godaddy", "ready", "GoDaddy domain ownership and nameservers readable.", "");
        } else {
            act(
                "godaddy",
                "blocked",
                "GoDaddy domain ownership could not be verified.",
                "Check the account, domain ownership, PAT, and connectivity; preview never purchases domains.",
            );
        }
    } else {
        act(
            "godaddy",
            "blocked",
            "GoDaddy delegation check requires an existing PAT for a guaranteed read-only preview.",
            "Set GDDY_PAT privately, or check current nameservers in the dashboard. Guided setup supports browser OAuth.",
        );
    }
    let listing = cf.get(&format!("/zones?name={domain}"))?;
    let named: Option<Vec<&Value>> = listing["result"]
        .as_array()
        .map(|zones| zones.iter().filter(|z| z["name"].as_str() == Some(&domain)).collect());
    let zone_id = match named.as_deref() {
        Some([]) => String::new(),
        Some([zone]) => zone["id"].as_str().unwrap_or("").to_string(),
        _ => return die("Cloudflare returned an invalid or ambiguous zone list"),
    };
    let (mut account, mut desired, mut zone_state, mut enabled, mut rules) =
        (String::new(), Vec::new(), String::new(), false, Vec::new());
    if !zone_id.is_empty() {
        let zone = cf.get(&format!("/zones/{zone_id}"))?;
        let z = &zone["result"];
        if z["name"].as_str() != Some(&domain)
            || !z["status"].is_string()
            || nonempty_str(&z["account"]["id"]).is_none()
        {
            return die("Cloudflare zone does not match DOMAIN or returned malformed data");
        }
        account = z["account"]["id"].as_str().unwrap().to_string();
        desired = match valid_nameservers(&zone) {
            Some(list) => normalize_nameservers(&list),
            None => return die("Cloudflare assigned nameservers missing"),
        };
        zone_state = z["status"].as_str().unwrap().to_string();
        act("zone", "ready", "Reuse the existing Cloudflare zone.", "");
        let routing = cf.get(&format!("/zones/{zone_id}/email/routing"))?;
        enabled = match routing["result"]["enabled"].as_bool() {
            Some(enabled) => enabled,
            None => return die("Cloudflare returned invalid Email Routing state"),
        };
        rules = cf.rules(&zone_id)?;
    } else {
        if !config.get("CF_ACCOUNT_ID").is_empty() {
            account = config.get("CF_ACCOUNT_ID").to_string();
        } else {
            let accounts = cf.get("/accounts")?;
            let Some(list) = accounts["result"].as_array() else { return die("Cloudflare returned invalid accounts") };
            if list.len() == 1 {
                account = match nonempty_str(&list[0]["id"]) {
                    Some(id) => id.to_string(),
                    None => return die("Cloudflare account ID missing"),
                };
            } else {
                act(
                    "account",
                    "blocked",
                    "Select the intended Cloudflare account.",
                    "Set CF_ACCOUNT_ID from the dashboard; token resource access still applies.",
                );
            }
        }
        act("zone", "planned", "Create a Cloudflare zone and fetch its assigned nameservers.", "");
    }
    if registrar != "godaddy" {
        if zone_state == "active" {
            act("nameservers", "ready", "Zone active on Cloudflare; no registrar change needed.", "");
        } else if !zone_id.is_empty() {
            act(
                "nameservers",
                "manual",
                &format!("Set these Cloudflare nameservers at your registrar: {}.", desired.join(", ")),
                "Update nameservers at your registrar after copying web, MX, TXT, and other records into Cloudflare and turning off DNSSEC.",
            );
        } else {
            act(
                "nameservers",
                "manual",
                "Setup creates the zone and prints the nameservers to set at your registrar.",
                "Update nameservers at your registrar when setup prints them; copy existing DNS records and turn off DNSSEC first.",
            );
        }
    } else if !desired.is_empty() && current == desired {
        act("nameservers", "ready", "Delegation already matches Cloudflare; skip the update.", "");
    } else {
        act(
            "nameservers",
            "confirmation",
            "Review existing DNS records, then confirm the full nameserver replacement if needed.",
            "Migrate web, MX, TXT, DNSSEC, and other service records before changing delegation.",
        );
    }
    if zone_state == "active" {
        act("activation", "ready", "Zone currently active; setup rechecks activation after delegation.", "");
    } else {
        act("activation", "wait", "Wait for Cloudflare zone activation after delegation.", "");
    }
    if enabled {
        act("routing", "ready", "Email Routing enabled; skip activation.", "");
    } else {
        act("routing", "planned", "Enable Email Routing after reviewing existing mail DNS records.", "");
    }
    if !account.is_empty() {
        let destinations = cf.addresses(&account, None)?;
        let found = destinations.iter().find(|d| d["email"].as_str() == Some(&dest));
        match found {
            Some(d) if nonempty_str(&d["verified"]).is_some() => {
                act("destination", "ready", "Destination already verified.", "")
            }
            Some(_) => act(
                "destination",
                "manual",
                "Reuse the pending destination; wait for its verification link.",
                "Click the Cloudflare link in the receiving inbox.",
            ),
            None => act(
                "destination",
                "manual",
                "Register the destination; wait for its verification link.",
                "Click the Cloudflare link in the receiving inbox.",
            ),
        }
    } else {
        act(
            "destination",
            "blocked",
            "Destination registration cannot be inspected until the account is selected.",
            "Set CF_ACCOUNT_ID and rerun the preview.",
        );
    }
    for local in config.addresses() {
        let address = format!("{local}@{domain}");
        let matches = exact_matches(&rules, &address);
        if matches.is_empty() {
            act(&address, "planned", &format!("Create forwarding to {dest}."), "");
        } else if rule_is_ready(&matches, &address, &dest) {
            act(&address, "ready", "Existing enabled forwarding rule matches; skip creation.", "");
        } else {
            act(
                &address,
                "blocked",
                "An existing disabled or conflicting rule requires attention.",
                "Enable/correct the rule in Cloudflare; setup never overwrites conflicting rules.",
            );
        }
    }
    act("delivery", "manual", "Send from a different mailbox to verify receiving after setup.", "");
    let seconds = elapsed_seconds();
    if ui::ctx().json {
        let blockers: Vec<&str> = actions.iter().filter(|a| a.state == "blocked").map(|a| a.message.as_str()).collect();
        let data = json!({"dry_run": true, "domain": domain, "destination": dest, "registrar": registrar,
                          "actions": checks_json(&actions), "blockers": blockers, "elapsed_seconds": seconds});
        output::print(&envelope("setup", data));
    } else {
        let mode = ui::ctx().out;
        let title = format!("Read-only setup plan for {domain} (registrar: {registrar})");
        if mode.styled {
            output::print(&checks_text(
                &mode,
                &title,
                &actions,
                Some(format!("Elapsed time: {}", output::elapsed(seconds))),
            ));
        } else {
            output::print(&checks_text(&mode, &title, &actions, None));
            ui::always(&format!("Elapsed time: {}\n", output::elapsed(seconds)));
        }
    }
    Ok(())
}

pub fn send_as(path: PathBuf) -> Result<()> {
    let config = Config::load(path, &Overrides::default())?;
    for key in ["DOMAIN", "DEST_EMAIL", "ADDRESSES"] {
        if config.get(key).is_empty() {
            return config_error(format!("no {key} in config — run cmail setup first so receiving works"));
        }
    }
    if !term::stdin_is_tty() {
        return usage("send-as requires terminal input; run it interactively to follow the manual guide");
    }
    let (dest, domain) = (config.get("DEST_EMAIL"), config.get("DOMAIN"));
    let first = config.addresses().first().cloned().unwrap_or_default();
    ui::step("Send FROM your custom address (optional, manual, ~5 min)");
    print!(
        "Only needed if you want to SEND from your custom address. Receiving already
works without it. This guide needs {dest} to be a Gmail/Google account
that can use App Passwords.

Automating Gmail aliases needs Google's restricted gmail.settings.* scope
(a verified OAuth app — overkill here). Do it once by hand:

  1. Gmail -> Settings -> See all settings -> \"Accounts and Import\"
  2. \"Send mail as\" -> \"Add another email address\"
  3. Name + your custom address (first of: {first}@{domain})
  4. SMTP settings — IMPORTANT, replace what Gmail pre-fills:
       SMTP server : smtp.gmail.com
       Port        : 587
       Username    : {dest}
       Password    : Google App Password (NOT your Gmail password)
         -> Google Account -> Security -> 2-Step Verification
            -> App passwords -> generate one for \"Mail\"
  5. Gmail emails a confirmation code to your custom address — it lands
     back in your Gmail via Cloudflare forwarding. Paste the code.

Repeat per extra address, or use \"Send mail as\" -> make default.

If blocked:
  - App passwords unavailable: enable 2-Step Verification on the SMTP
    account. Work/school policy, Advanced Protection or security-key-only
    settings may prevent App Passwords; ask your administrator or use an
    approved SMTP provider. Do not disable security controls to work around it.
  - SMTP rejected: check server/port, TLS, the full account username and a
    current App Password (not your normal password). If revoked, generate a
    new one privately. Check account security alerts or ask your administrator.
    Retry \"Add another email address\" after resolving the SMTP issue.
  - Confirmation missing: check Spam/All Mail, verify the Cloudflare
    destination is confirmed, the address rule points to it, and Email Routing
    and DNS/MX are active. Resolve any pending steps with cmail setup, then
    resend the Gmail confirmation (cmail status shows the saved state). Do not mark the alias ready without it.

Verify from a DIFFERENT mailbox (not {dest}):
  - Send to {first}@{domain} and confirm it arrives at {dest}.
  - Send from Gmail using the custom From address to that different mailbox;
    check delivery, the From address, Spam and replies back to your alias.
"
    );
    use std::io::Write;
    let _ = std::io::stdout().flush();
    ui::open_url("https://myaccount.google.com/apppasswords");
    ui::open_url("https://mail.google.com/mail/u/0/#settings/accounts");
    if !ui::pause() {
        return die("Gmail guide paused without input — finish the manual steps in Gmail settings, then run cmail send-as in an interactive terminal to resume; confirmation and mailbox tests are not automatically verified");
    }
    ui::note("manual Gmail setup is not automatically verified — complete confirmation and both mailbox tests above; re-open Gmail settings to resume if needed");
    Ok(())
}
