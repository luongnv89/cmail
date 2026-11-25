//! `cmail sending enable`: onboard DOMAIN to Cloudflare Email Sending with a
//! separate sending-only token, without letting Cloudflare publish `p=reject`
//! over a domain that other services still send as.
//!
//! Every `/email/sending/*` call uses CF_SENDING_TOKEN; CLOUDFLARE_API_TOKEN is
//! never sent there. DMARC is read over public DNS (DoH) only; cmail never
//! writes DNS records.

use crate::cli::{Dmarc, SendingEnableArgs};
use crate::cloudflare::{nonempty_str, truthy, Cf};
use crate::config::{Config, Overrides};
use crate::error::{config_error, die, usage, Error, Result};
use crate::output::{self, check, checks_json, checks_text, envelope, Check};
use crate::{term, ui};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// Public DNS-over-HTTPS JSON endpoint; tests point CMAIL_DOH_URL at a loopback fixture.
const DOH: &str = "https://cloudflare-dns.com/dns-query";

const NON_TTY: &str = "sending enable requires terminal input: it may ask about Gmail Send-as (pass --dmarc none or --dmarc reject) and asks you to confirm; run it interactively, or add --dry-run to preview";

const NONE_EXPLANATION: &str = "Gmail \"Send mail as\" delivers through Google's servers, which can't sign with your domain's Cloudflare DKIM key, and your SPF only lists Cloudflare. That mail fails DMARC alignment; with `p=reject` receivers would bounce it. `p=none` only monitors. After Gmail removes third-party Send-as (January 2027), you can raise it to `p=quarantine` or `p=reject`.";

/// What public DNS says about `_dmarc.DOMAIN`.
#[derive(Debug, PartialEq)]
enum DmarcState {
    Present { policy: Option<String>, record: String },
    Missing,
}

/// What onboarding will do about DMARC.
#[derive(Clone, Copy, PartialEq)]
enum Outcome {
    /// An existing record stays; Cloudflare keeps it unchanged.
    Keep,
    /// No record and the user accepts Cloudflare's `p=reject`.
    Reject,
    /// No record and the user must add `p=none` by hand first.
    AddNone,
}

pub fn enable(path: PathBuf, args: &SendingEnableArgs) -> Result<()> {
    let mut config = Config::load(path, &Overrides::default())?;
    let dry_run = args.dry_run || config.get("DRY_RUN") == "1";
    // Same order as setup: refuse what cannot finish before any provider or DNS call.
    if !dry_run && ui::ctx().json {
        return usage("JSON sending enable output requires --dry-run");
    }
    if !dry_run && !term::stdin_is_tty() {
        return usage(NON_TTY);
    }
    let domain = config.get("DOMAIN").to_string();
    let zone = config.get("CF_ZONE_ID").to_string();
    if domain.is_empty() || zone.is_empty() {
        return config_error("DOMAIN and CF_ZONE_ID are required — run cmail setup first");
    }
    let main_token = config.get("CLOUDFLARE_API_TOKEN");
    if !main_token.is_empty() && config.get("CF_SENDING_TOKEN") == main_token {
        return config_error(
            "CF_SENDING_TOKEN must be a separate sending-only token, not CLOUDFLARE_API_TOKEN — create one with only Email Sending · Edit and set it with cmail config set CF_SENDING_TOKEN --stdin",
        );
    }
    if dry_run {
        return plan(&config, &domain, &zone, args.dmarc);
    }
    if config.get("CF_SENDING_TOKEN").is_empty() {
        ensure_token(&mut config, &domain, &zone)?;
    }
    let cf = Cf::sending(&config)?;
    ui::step(&format!("Cloudflare Email Sending: {domain}"));
    let entries = cf.sending_subdomains(&zone)?;
    if find(&entries, &domain)?.is_some_and(|(_, enabled)| enabled) {
        output::print(&format!("sending already enabled for {domain}"));
        return Ok(());
    }
    let state = lookup_dmarc(&domain)?;
    let mut outcome = match (&state, args.dmarc) {
        (DmarcState::Present { .. }, _) => Outcome::Keep,
        (DmarcState::Missing, Dmarc::Reject) => Outcome::Reject,
        (DmarcState::Missing, Dmarc::Monitor) => Outcome::AddNone,
        (DmarcState::Missing, Dmarc::Auto) => {
            ui::warn(&format!("_dmarc.{domain} has no DMARC record"));
            if ui::confirm(&format!("Do you send as @{domain} from Gmail (cmail send-as) or any other service?")) {
                Outcome::AddNone
            } else {
                Outcome::Reject
            }
        }
    };
    ui::always(&preview(&domain, &state, outcome));
    if outcome == Outcome::AddNone {
        ui::always(&none_instructions(&domain));
        wait_for_dmarc(&domain)?;
        outcome = Outcome::Keep;
        ui::ok(&format!("_dmarc.{domain} found — Cloudflare keeps an existing DMARC record unchanged"));
    }
    let question = if outcome == Outcome::Reject {
        format!("Onboard {domain} to Cloudflare Email Sending (Cloudflare adds v=DMARC1; p=reject;)?")
    } else {
        format!("Onboard {domain} to Cloudflare Email Sending?")
    };
    if !ui::confirm(&question) {
        return die(format!("cancelled — nothing was changed; {domain} is not onboarded for sending"));
    }
    onboard(&cf, &zone, &domain)
}

/// POST once, then trust only the read-back: an error counts as success only when
/// Cloudflare then lists DOMAIN with `enabled: true`.
fn onboard(cf: &Cf, zone: &str, domain: &str) -> Result<()> {
    let path = format!("/zones/{zone}/email/sending/subdomains");
    let posted = cf.call("POST", &path, Some(&json!({"name": domain})), None)?;
    let entries = cf.sending_subdomains(zone)?;
    let found = find(&entries, domain)?;
    if let Err(error) = posted {
        if !found.is_some_and(|(_, enabled)| enabled) {
            return cf.fail("POST", &path, error);
        }
        ui::note(&format!(
            "Cloudflare answered HTTP {} to the request, but {domain} now reads back as enabled",
            error.status
        ));
    }
    let Some((entry, true)) = found else {
        return die(format!(
            "Cloudflare accepted the request but {domain} does not read back as enabled for sending — check Compute > Email Service > Email Sending in the dashboard before retrying"
        ));
    };
    let mut lines = vec![format!("Email Sending enabled for {domain}")];
    match subdomain_id(entry) {
        None => ui::warn(
            "Cloudflare returned no usable subdomain id — skipping the DNS record read-back; see Compute > Email Service > Email Sending in the dashboard",
        ),
        Some(id) => {
            let response = cf.get(&format!("/zones/{zone}/email/sending/subdomains/{id}/dns"))?;
            match response.get("result").and_then(Value::as_array) {
                None => ui::warn(
                    "Cloudflare returned no DNS record list for the sending subdomain — check DNS > Records in the dashboard",
                ),
                Some(records) => {
                    lines.push("DNS records Cloudflare manages for sending:".into());
                    lines.extend(records.iter().map(record_line));
                }
            }
        }
    }
    output::print(&lines.join("\n"));
    ui::note(
        "DNS can take 5–15 minutes to take effect; then test with cmail notify --subject \"cmail test\" \"it works\"",
    );
    Ok(())
}

/// The entry named DOMAIN (case-insensitive) and its enabled state. Missing fields stop
/// with a clear message rather than being guessed.
fn find<'a>(entries: &'a [Value], domain: &str) -> Result<Option<(&'a Value, bool)>> {
    let mut found = None;
    for entry in entries {
        let Some(name) = nonempty_str(&entry["name"]) else {
            return die("Cloudflare returned a sending subdomain without a name — nothing was changed; check Compute > Email Service > Email Sending in the dashboard");
        };
        if !name.eq_ignore_ascii_case(domain) {
            continue;
        }
        let Some(enabled) = entry["enabled"].as_bool() else {
            return die(format!(
                "Cloudflare returned the sending subdomain {name} without a valid enabled state — nothing was changed"
            ));
        };
        if found.is_none() || enabled {
            found = Some((entry, enabled));
        }
    }
    Ok(found)
}

/// `id`, else `tag`, restricted to a safe path segment.
fn subdomain_id(entry: &Value) -> Option<&str> {
    entry.get("id").filter(|v| truthy(v)).or_else(|| entry.get("tag")).and_then(Value::as_str).filter(|id| {
        (1..=64).contains(&id.len()) && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
    })
}

fn record_line(record: &Value) -> String {
    let field = |key: &str| match record.get(key) {
        Some(Value::String(s)) if !s.is_empty() => s.clone(),
        Some(Value::Number(n)) => n.to_string(),
        _ => "?".into(),
    };
    let priority = match record.get("priority") {
        Some(Value::Number(n)) => format!(" (priority {n})"),
        _ => String::new(),
    };
    format!("  {:<5} {}  {}{priority}", field("type"), field("name"), field("content"))
}

fn preview(domain: &str, state: &DmarcState, outcome: Outcome) -> String {
    let dmarc = match (state, outcome) {
        (DmarcState::Present { policy, record }, _) => format!(
            "  DMARC: _dmarc.{domain} exists ({}) — Cloudflare keeps an existing DMARC record unchanged.\n         {record}",
            policy_text(policy)
        ),
        (_, Outcome::Reject) => format!(
            "  DMARC: _dmarc.{domain} is missing, so Cloudflare will add TXT _dmarc v=DMARC1; p=reject;\n         Mail that other services send as @{domain} (such as Gmail Send-as) will then bounce."
        ),
        (_, Outcome::AddNone) => {
            format!("  DMARC: _dmarc.{domain} is missing — add a p=none record by hand first (below)")
        }
        (_, Outcome::Keep) => format!("  DMARC: _dmarc.{domain} — Cloudflare keeps an existing DMARC record unchanged."),
    };
    format!(
        "\nCloudflare Email Sending adds these DNS records for {domain}:
  MX    cf-bounce.{domain}  route1.mx.cloudflare.net, route2.mx.cloudflare.net, route3.mx.cloudflare.net
  TXT   cf-bounce.{domain}  v=spf1 include:_spf.mx.cloudflare.net ~all  (SPF)
  TXT   cf-bounce._domainkey.{domain}  DKIM public key generated by Cloudflare
{dmarc}

"
    )
}

fn policy_text(policy: &Option<String>) -> String {
    match policy {
        Some(policy) => format!("policy p={policy}"),
        None => "no p= policy tag".into(),
    }
}

fn none_instructions(domain: &str) -> String {
    format!(
        "Add this record in Cloudflare > {domain} > DNS > Records > Add record:
  Type: TXT   Name: _dmarc   Content: v=DMARC1; p=none;   TTL: Auto

{NONE_EXPLANATION}

cmail never edits DNS and never onboards while _dmarc is missing in none mode.
Public DNS can cache the missing answer for up to 30 minutes after you add it.

"
    )
}

/// Re-check every 15 s until the record appears or `--wait-timeout` passes (exit 3).
fn wait_for_dmarc(domain: &str) -> Result<()> {
    let limit = ui::ctx().wait_timeout;
    let deadline = Instant::now() + Duration::from_secs(limit);
    ui::note(&format!("waiting for _dmarc.{domain} in public DNS (rechecking every 15s, up to {limit}s)…"));
    for _ in 0..limit.div_ceil(15) {
        let left = deadline.saturating_duration_since(Instant::now()).as_secs();
        if left == 0 {
            break;
        }
        term::sleep(left.min(15));
        if let DmarcState::Present { .. } = lookup_dmarc(domain)? {
            return Ok(());
        }
        ui::note("_dmarc still missing — waiting…");
    }
    ui::warn(&format!(
        "_dmarc.{domain} is still missing after {limit}s — add the record, then rerun cmail sending enable (public DNS can cache a missing answer for up to 30 minutes). Nothing was changed"
    ));
    Err(Error::Exit(3))
}

/// DoH endpoint: the public resolver, or (tests only) a loopback `http://` URL in CMAIL_DOH_URL.
fn doh_url() -> Result<String> {
    let Some(url) = std::env::var("CMAIL_DOH_URL").ok().filter(|v| !v.is_empty()) else {
        return Ok(DOH.to_string());
    };
    let invalid = || config_error("CMAIL_DOH_URL must be a loopback http:// URL with a port (tests only)");
    let Some(rest) = url.strip_prefix("http://") else { return invalid() };
    let (authority, tail) = rest.split_at(rest.find(['/', '?', '#']).unwrap_or(rest.len()));
    if tail.contains(['?', '#']) {
        return invalid();
    }
    let port = ["127.0.0.1:", "localhost:", "[::1]:"].iter().find_map(|host| authority.strip_prefix(host));
    match port {
        Some(port) if !port.is_empty() && port.bytes().all(|b| b.is_ascii_digit()) => {
            Ok(url.trim_end_matches('/').to_string())
        }
        _ => invalid(),
    }
}

/// Read `_dmarc.DOMAIN` TXT over DoH with no credential. Any failure stops: an
/// unreadable answer must never pass for "missing" or "present".
fn lookup_dmarc(domain: &str) -> Result<DmarcState> {
    let url = format!("{}?name=_dmarc.{domain}&type=TXT", doh_url()?);
    let seconds = (ui::ctx().timeout as u64).max(1);
    ui::verbose(&format!("Request: public DNS TXT _dmarc.{domain} (timeout {seconds}s)"));
    let timeout = Duration::from_secs(seconds);
    let agent = ureq::AgentBuilder::new().timeout_connect(timeout).timeout(timeout).build();
    let answer = match agent.get(&url).set("Accept", "application/dns-json").call() {
        Ok(response) => response.into_string().map_err(|e| e.to_string()),
        Err(ureq::Error::Status(code, _)) => Err(format!("HTTP {code}")),
        Err(ureq::Error::Transport(t)) => Err(t.kind().to_string()),
    };
    match answer.and_then(|body| parse_doh(&body)) {
        Ok(state) => Ok(state),
        Err(reason) => die(format!(
            "could not read _dmarc.{domain} from public DNS ({reason}) — nothing was changed; check your connection and rerun cmail sending enable"
        )),
    }
}

/// DoH JSON (`application/dns-json`): Status 3 or no TXT answer is missing; exactly one
/// `v=DMARC1` TXT record is present; anything else is an error.
fn parse_doh(body: &str) -> std::result::Result<DmarcState, String> {
    let value: Value = serde_json::from_str(body).map_err(|_| "non-JSON DNS answer".to_string())?;
    match value.get("Status").and_then(Value::as_u64) {
        Some(3) => return Ok(DmarcState::Missing),
        Some(0) => {}
        Some(status) => return Err(format!("DNS status {status}")),
        None => return Err("DNS answer without a status".into()),
    }
    let answers = match value.get("Answer") {
        None | Some(Value::Null) => return Ok(DmarcState::Missing),
        Some(Value::Array(answers)) => answers,
        Some(_) => return Err("malformed DNS answer list".into()),
    };
    let mut records = Vec::new();
    for answer in answers.iter().filter(|a| a.get("type").and_then(Value::as_u64) == Some(16)) {
        let Some(data) = answer.get("data").and_then(Value::as_str) else {
            return Err("TXT answer without data".into());
        };
        let text = txt_text(data);
        if is_dmarc(&text) {
            records.push(text);
        }
    }
    match records.len() {
        0 => Ok(DmarcState::Missing),
        1 => {
            let record = records.remove(0);
            Ok(DmarcState::Present { policy: policy(&record), record })
        }
        n => Err(format!("{n} DMARC records — receivers ignore them all; keep exactly one")),
    }
}

/// Join a TXT record's character-strings: `"a" "b"` → `ab`; unquoted data is taken as is.
fn txt_text(data: &str) -> String {
    let data = data.trim();
    if !data.starts_with('"') {
        return data.to_string();
    }
    let mut out = String::new();
    let mut chars = data.chars();
    let mut quoted = false;
    while let Some(c) = chars.next() {
        match c {
            '"' => quoted = !quoted,
            '\\' if quoted => out.extend(chars.next()),
            _ if quoted => out.push(c),
            _ => {}
        }
    }
    out
}

fn is_dmarc(text: &str) -> bool {
    let text = text.trim_start();
    text.get(..8).is_some_and(|tag| tag.eq_ignore_ascii_case("v=DMARC1"))
        && text[8..].chars().next().is_none_or(|c| c == ';' || c.is_whitespace())
}

fn policy(record: &str) -> Option<String> {
    record.split(';').skip(1).find_map(|tag| {
        let (key, value) = tag.split_once('=')?;
        (key.trim().eq_ignore_ascii_case("p") && !value.trim().is_empty()).then(|| value.trim().to_string())
    })
}

/// Guided creation of the sending-only token. A candidate is accepted only after the
/// subdomain list answers with it; nothing else uses it before then.
fn ensure_token(config: &mut Config, domain: &str, zone: &str) -> Result<()> {
    ui::step("Cloudflare sending token");
    ui::always(&format!(
        "Email Sending needs its own Cloudflare API token, separate from CLOUDFLARE_API_TOKEN
(that token keeps its four receiving permissions). Create it now (browser will open):

  1. \"Create token\" -> \"Custom token\" -> \"Get started\"
     Token name: any label you will recognise (e.g. cmail sending {domain})
  2. Permissions (one row):
       Email Sending · Edit
  3. Account Resources: Include -> <the account that owns {domain}>
     Zone Resources:    Include -> Specific zone -> {domain}
     Never choose All accounts or All zones.
  4. Create token, copy it, paste below (input hidden).

"
    ));
    ui::open_url("https://dash.cloudflare.com/profile/api-tokens");
    let path = format!("/zones/{zone}/email/sending/subdomains?per_page=50&page=1");
    loop {
        let Some(pasted) = ui::ask("paste Cloudflare sending token", true) else {
            return die("no token input — run cmail sending enable in an interactive terminal or set it with cmail config set CF_SENDING_TOKEN --stdin");
        };
        if pasted.is_empty() {
            return die("token required — create a sending-only token at https://dash.cloudflare.com/profile/api-tokens and rerun cmail sending enable");
        }
        if pasted == config.get("CLOUDFLARE_API_TOKEN") {
            ui::warn("that is CLOUDFLARE_API_TOKEN — create a separate token with only Email Sending · Edit");
            continue;
        }
        let mut cf = Cf::sending(config)?;
        cf.set_token(&pasted);
        match cf.call("GET", &path, None, None)? {
            Ok(_) => {
                config.set("CF_SENDING_TOKEN", &pasted)?;
                ui::ok("sending token verified and saved to your config");
                return Ok(());
            }
            Err(error) if error.status == 401 || error.status == 403 => {
                ui::warn(&crate::cloudflare::sending_hint(error.status, &error.codes, domain));
            }
            Err(error) => return cf.fail("GET", &path, error),
        }
    }
}

/// Read-only plan: no token flow, writes, prompts, browser or waits.
fn plan(config: &Config, domain: &str, zone: &str, mode: Dmarc) -> Result<()> {
    let mut actions: Vec<Check> = Vec::new();
    let mut act = |name: &str, state: &str, message: &str, next: &str| actions.push(check(name, state, message, next));
    let mut enabled = None;
    if config.get("CF_SENDING_TOKEN").is_empty() {
        act(
            "token",
            "blocked",
            "CF_SENDING_TOKEN is not set.",
            "Run cmail sending enable in a terminal to create one, or cmail config set CF_SENDING_TOKEN --stdin.",
        );
        act("sending", "manual", "Not checked: Email Sending state needs CF_SENDING_TOKEN.", "");
    } else {
        act("token", "ready", "CF_SENDING_TOKEN is set, separate from CLOUDFLARE_API_TOKEN.", "");
        let cf = Cf::sending(config)?;
        let entries = cf.sending_subdomains(zone)?;
        let state = find(&entries, domain)?.map(|(_, enabled)| enabled);
        enabled = Some(state == Some(true));
        if state == Some(true) {
            act("sending", "ready", &format!("sending already enabled for {domain}"), "");
        } else {
            act("sending", "planned", &format!("Onboard {domain} to Cloudflare Email Sending."), "");
        }
    }
    let mut dmarc = json!(null);
    if enabled != Some(true) {
        act(
            "records",
            "planned",
            &format!(
                "Cloudflare adds MX and SPF TXT on cf-bounce.{domain} and DKIM TXT on cf-bounce._domainkey.{domain}."
            ),
            "",
        );
        let state = lookup_dmarc(domain)?;
        match &state {
            DmarcState::Present { policy, record } => {
                dmarc = json!({"state": "present", "policy": policy, "record": record});
                act(
                    "dmarc",
                    "ready",
                    &format!(
                        "_dmarc.{domain} exists ({}) — Cloudflare keeps an existing DMARC record unchanged.",
                        policy_text(policy)
                    ),
                    "",
                );
            }
            DmarcState::Missing => {
                dmarc = json!({"state": "missing", "policy": null, "record": null});
                match mode {
                    Dmarc::Reject => act(
                        "dmarc",
                        "planned",
                        &format!("Cloudflare adds v=DMARC1; p=reject; and mail other services send as @{domain} will bounce."),
                        "",
                    ),
                    Dmarc::Monitor => act(
                        "dmarc",
                        "blocked",
                        &format!("_dmarc.{domain} is missing; none mode never onboards until it exists."),
                        "Add TXT _dmarc v=DMARC1; p=none; in Cloudflare DNS, then rerun.",
                    ),
                    Dmarc::Auto => act(
                        "dmarc",
                        "manual",
                        &format!("_dmarc.{domain} is missing; a real run asks whether you send as @{domain} elsewhere."),
                        "Pass --dmarc none or --dmarc reject to decide now.",
                    ),
                }
            }
        }
    }
    if ui::ctx().json {
        let blockers: Vec<&str> = actions.iter().filter(|a| a.state == "blocked").map(|a| a.message.as_str()).collect();
        let data = json!({"dry_run": true, "domain": domain, "dmarc": dmarc, "actions": checks_json(&actions),
                          "blockers": blockers});
        output::print(&envelope("sending enable", data));
    } else {
        let title = format!("Read-only Email Sending plan for {domain}");
        output::print(&checks_text(&ui::ctx().out, &title, &actions, None));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn present(policy: &str, record: &str) -> DmarcState {
        DmarcState::Present { policy: Some(policy.into()), record: record.into() }
    }

    #[test]
    fn doh_answers_decide_missing_or_present() {
        let txt = |data: &str| json!({"Status": 0, "Answer": [{"type": 16, "data": data}]}).to_string();
        assert_eq!(parse_doh(&txt("\"v=DMARC1; p=none;\"")), Ok(present("none", "v=DMARC1; p=none;")));
        assert_eq!(
            parse_doh(&txt("\"v=DMARC1; \" \"p=quarantine\"")),
            Ok(present("quarantine", "v=DMARC1; p=quarantine"))
        );
        assert_eq!(parse_doh(&txt("\"V=dmarc1;P=Reject\"")), Ok(present("Reject", "V=dmarc1;P=Reject")));
        assert_eq!(parse_doh(&txt("\"v=spf1 -all\"")), Ok(DmarcState::Missing));
        assert_eq!(parse_doh(&txt("\"v=DMARC10; p=none\"")), Ok(DmarcState::Missing));
        assert_eq!(parse_doh(r#"{"Status":3}"#), Ok(DmarcState::Missing));
        assert_eq!(parse_doh(r#"{"Status":0}"#), Ok(DmarcState::Missing));
        let cname = json!({"Status": 0, "Answer": [{"type": 5, "data": "dmarc.provider.example."}]}).to_string();
        assert_eq!(parse_doh(&cname), Ok(DmarcState::Missing));
        let chased =
            json!({"Status": 0, "Answer": [{"type": 5, "data": "x."}, {"type": 16, "data": "\"v=DMARC1; p=none\""}]});
        assert_eq!(parse_doh(&chased.to_string()), Ok(present("none", "v=DMARC1; p=none")));
    }

    #[test]
    fn doh_failures_are_never_missing() {
        let two = json!({"Status": 0, "Answer": [{"type": 16, "data": "\"v=DMARC1; p=none\""},
                                                  {"type": 16, "data": "\"v=DMARC1; p=reject\""}]});
        for body in [r#"{"Status":2}"#, "<html>", r#"{"Answer":[]}"#, r#"{"Status":0,"Answer":{}}"#, &two.to_string()] {
            assert!(parse_doh(body).is_err(), "{body}");
        }
        assert!(parse_doh(r#"{"Status":0,"Answer":[{"type":16}]}"#).is_err());
    }

    #[test]
    fn subdomain_id_prefers_id_then_tag() {
        assert_eq!(subdomain_id(&json!({"id": "abc", "tag": "t1"})), Some("abc"));
        assert_eq!(subdomain_id(&json!({"tag": "t1"})), Some("t1"));
        assert_eq!(subdomain_id(&json!({"id": "../x"})), None);
        assert_eq!(subdomain_id(&json!({"name": "example.com"})), None);
    }

    #[test]
    fn missing_record_fields_print_placeholders() {
        assert_eq!(record_line(&json!({})), "  ?     ?  ?");
        assert_eq!(
            record_line(
                &json!({"type": "MX", "name": "cf-bounce.example.com", "content": "route1.mx.cloudflare.net", "priority": 10})
            ),
            "  MX    cf-bounce.example.com  route1.mx.cloudflare.net (priority 10)"
        );
    }
}
