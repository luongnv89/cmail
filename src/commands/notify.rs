//! `cmail notify`: send a plain-text message through Cloudflare Email Sending to the
//! owner's own verified destination inbox. It never prompts, so cron can run it.
//!
//! The send uses CF_SENDING_TOKEN only. CLOUDFLARE_API_TOKEN (when set) reads the zone,
//! the owning account and the destination list, and is never sent to `/email/sending/*`.

use crate::cli::NotifyArgs;
use crate::cloudflare::{codes_text, nonempty_str, send_hint, sending_hint, Cf, ListError};
use crate::commands::sending::{failure_text, find, require_sending_token};
use crate::config::{self, Config, Overrides};
use crate::error::{config_error, die, usage, Error, Result};
use crate::output::{self, envelope};
use crate::{term, ui};
use serde_json::{json, Value};
use std::path::PathBuf;

const DEFAULT_SUBJECT: &str = "cmail notification";

/// Cloudflare's subject limit, in characters.
const MAX_SUBJECT: usize = 998;

/// Largest message body read from stdin, in bytes (well under Cloudflare's 25 MiB).
const MAX_BODY: usize = 256 * 1024;

const FREE_PLAN: &str = "On the Workers Free plan Cloudflare sends only to verified destination addresses";

/// Whether DOMAIN has an enabled Email Sending entry, as far as cmail could tell.
#[derive(Clone, Copy, PartialEq)]
enum Onboarding {
    Enabled,
    Missing,
    Unknown,
}

pub fn notify(path: PathBuf, args: &NotifyArgs) -> Result<()> {
    // Arguments first (exit 2), then the body (exit 3), then configuration (exit 3):
    // each refusal comes before any provider request.
    if args.stdin && term::stdin_is_tty() {
        return usage("--stdin needs piped input, such as: echo done | cmail notify --stdin");
    }
    if let Some(to) = &args.to {
        if !config::field_valid("DEST_EMAIL", to) {
            return usage("--to must be an email address such as you@example.net");
        }
    }
    if let Some(from) = &args.from {
        if !config::local_valid(from) {
            return usage("--from must be a local part such as hello (cmail adds @DOMAIN)");
        }
    }
    let subject = args.subject.as_deref().unwrap_or(DEFAULT_SUBJECT);
    if subject.contains(['\r', '\n', '\u{2028}', '\u{2029}']) {
        return usage("--subject must be a single line");
    }
    if subject.chars().any(|c| c.is_control() && c != '\t') {
        return usage("--subject must be printable text: no control characters other than tab");
    }
    if subject.trim().is_empty() {
        return usage("--subject must not be blank");
    }
    if subject.chars().count() > MAX_SUBJECT {
        return usage(format!("--subject must be at most {MAX_SUBJECT} characters"));
    }
    let body = match &args.message {
        Some(message) => message.clone(),
        None => read_body()?,
    };
    if body.trim().is_empty() {
        return config_error("the message is empty — pass MESSAGE or pipe text to --stdin; nothing was sent");
    }

    let config = Config::load(path, &Overrides::default())?;
    let domain = config.get("DOMAIN").to_string();
    if domain.is_empty() {
        return config_error("DOMAIN is required — run cmail setup first");
    }
    if config.get("CF_SENDING_TOKEN").is_empty() {
        return config_error(
            "CF_SENDING_TOKEN is not set — run cmail sending enable in a terminal, or set it with cmail config set CF_SENDING_TOKEN --stdin",
        );
    }
    require_sending_token(&config)?;
    let to = match &args.to {
        Some(to) => to.clone(),
        None if !config.get("DEST_EMAIL").is_empty() => config.get("DEST_EMAIL").to_string(),
        None => {
            return config_error(
                "no recipient — pass --to EMAIL, or set DEST_EMAIL (cmail config set DEST_EMAIL EMAIL)",
            )
        }
    };
    let local = match (&args.from, config.get("NOTIFY_FROM"), config.addresses().first()) {
        (Some(from), _, _) => from.clone(),
        (None, from, _) if !from.is_empty() => from.to_string(),
        (None, _, Some(first)) => first.clone(),
        (None, _, None) => {
            return config_error("no sender — pass --from LOCAL, or set NOTIFY_FROM or ADDRESSES");
        }
    };
    let from = format!("{local}@{domain}");

    let main = if config.get("CLOUDFLARE_API_TOKEN").is_empty() { None } else { Some(Cf::new(&config)?) };
    let zone = match (config.get("CF_ZONE_ID"), &main) {
        (saved, _) if !saved.is_empty() => Some(saved.to_string()),
        (_, Some(cf)) => Some(cf.zone_id_for_domain(&config)?),
        (_, None) => None,
    };
    let account = match (config.get("CF_ACCOUNT_ID"), &main, &zone) {
        (saved, _, _) if !saved.is_empty() => saved.to_string(),
        (_, Some(cf), Some(zone)) => cf.account_for_zone(zone, "nothing was sent")?,
        _ => {
            return config_error(
                "the Cloudflare account is unknown — set CF_ACCOUNT_ID, or CLOUDFLARE_API_TOKEN and CF_ZONE_ID (run cmail setup); nothing was sent",
            )
        }
    };

    match &main {
        Some(cf) => check_recipient(cf, &account, &to)?,
        None => ui::warn(&format!(
            "CLOUDFLARE_API_TOKEN is not set, so cmail can't check that {to} is a verified destination address; Cloudflare refuses an unverified recipient on the Workers Free plan (HTTP 403, error code 10208)"
        )),
    }

    let sending = Cf::sending(&config)?;
    let onboarding = onboarding(&sending, zone.as_deref(), &domain)?;
    let path = format!("/accounts/{account}/email/sending/send");
    let payload = json!({"from": from, "to": [to], "subject": subject, "text": body});
    let response = match sending.call("POST", &path, Some(&payload), None)? {
        Ok(response) => response,
        Err(error) => {
            match send_hint(error.status, &error.codes, &error.detail, &domain, &to) {
                Some(hint) => ui::warn(&hint),
                // Only an answer cmail has no documented hint for can mean "not onboarded".
                None => {
                    ui::warn(&sending_hint(error.status, &error.codes, &domain));
                    if onboarding == Onboarding::Missing && matches!(error.status, 403 | 404) {
                        ui::warn("onboard first: cmail sending enable");
                    }
                }
            }
            return die(format!(
                "Cloudflare API error: POST {path} (HTTP {} with {}): {}",
                error.status,
                codes_text(&error.codes),
                error.detail
            ));
        }
    };
    report(&response, &to)
}

/// The message from stdin: UTF-8 text without NUL, at most MAX_BODY bytes once one
/// trailing line ending (LF, or CRLF as a unit) is dropped.
fn read_body() -> Result<String> {
    // Up to two bytes may be dropped, so reading one more keeps any oversize input above the cap.
    let mut bytes = term::read_stdin_bytes(MAX_BODY + 3);
    if bytes.ends_with(b"\r\n") {
        bytes.truncate(bytes.len() - 2);
    } else if bytes.last() == Some(&b'\n') {
        bytes.pop();
    }
    // Still exit 3 (invalid input), but the config hint would point at the wrong thing.
    let invalid = || {
        ui::print_input_error(
            &format!("stdin must be UTF-8 text without NUL, at most {MAX_BODY} bytes; nothing was sent"),
            &format!("pipe plain UTF-8 text without NUL bytes, at most {MAX_BODY} bytes"),
        );
        Err(Error::Exit(3))
    };
    if bytes.len() > MAX_BODY || bytes.contains(&0) {
        return invalid();
    }
    String::from_utf8(bytes).or_else(|_| invalid())
}

/// Refuse a recipient Cloudflare would not send to for free, before any send.
/// The last entry wins when Cloudflare lists an address twice, as in `cmail list`.
fn check_recipient(cf: &Cf, account: &str, to: &str) -> Result<()> {
    let destinations = cf.addresses(account, None)?;
    let found =
        destinations.iter().rev().find(|d| d["email"].as_str().is_some_and(|email| email.eq_ignore_ascii_case(to)));
    match found {
        None => config_error(format!(
            "{to} is not a Cloudflare destination address, so nothing was sent. {FREE_PLAN}: add and verify it with cmail forward or cmail setup, or in the dashboard (Email > Email Routing > Destination addresses), then rerun"
        )),
        Some(destination) if destination["verified"].is_null() => config_error(format!(
            "{to} is registered but not verified yet, so nothing was sent. {FREE_PLAN}: click the Cloudflare verification link in {to}'s inbox (check Spam; resend it from Email > Email Routing > Destination addresses), then rerun"
        )),
        Some(_) => Ok(()),
    }
}

/// Advisory only: Cloudflare documents a legacy path for routing-only domains, so the
/// send is tried whatever this finds; the answer only shapes the warnings.
fn onboarding(sending: &Cf, zone: Option<&str>, domain: &str) -> Result<Onboarding> {
    const ANYWAY: &str = "trying the send anyway";
    let Some(zone) = zone else {
        ui::warn(&format!(
            "CF_ZONE_ID is not set, so cmail can't check whether {domain} is onboarded to Email Sending — {ANYWAY}"
        ));
        return Ok(Onboarding::Unknown);
    };
    let entries = match sending.sending_subdomains(zone) {
        Ok(entries) => entries,
        Err(ListError::Failed { path, failure }) => {
            ui::warn(&format!(
                "couldn't read the Email Sending list (GET {path}: {}) — {ANYWAY}",
                failure_text(&failure)
            ));
            return Ok(Onboarding::Unknown);
        }
        Err(ListError::Malformed(reason)) => {
            ui::warn(&format!("couldn't read the Email Sending list ({reason}) — {ANYWAY}"));
            return Ok(Onboarding::Unknown);
        }
    };
    // `find` stops on a malformed entry; here that only means the state is unknown.
    match find(&entries, domain, ANYWAY) {
        Ok(Some((_, true))) => Ok(Onboarding::Enabled),
        Ok(_) => {
            ui::warn(&format!(
                "{domain} is not onboarded to Email Sending — using Cloudflare's legacy routing path; run cmail sending enable"
            ));
            Ok(Onboarding::Missing)
        }
        Err(Error::Fail(message)) => {
            ui::warn(&format!("couldn't read the Email Sending list: {message}"));
            Ok(Onboarding::Unknown)
        }
        Err(other) => Err(other),
    }
}

/// Success only when Cloudflare reports the message delivered or queued. No field of the
/// answer is assumed present: a missing or mistyped one reads as absent.
fn report(response: &Value, to: &str) -> Result<()> {
    let result = response.get("result");
    let list = |key: &str| -> Vec<String> {
        result
            .and_then(|r| r.get(key))
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(Value::as_str).map(str::to_string).collect())
            .unwrap_or_default()
    };
    let message_id = result.and_then(|r| r.get("message_id")).and_then(nonempty_str);
    let (delivered, queued) = (list("delivered"), list("queued"));
    if !delivered.is_empty() || !queued.is_empty() {
        if ui::ctx().json {
            output::print(&envelope(
                "notify",
                json!({"message_id": message_id, "delivered": delivered, "queued": queued}),
            ));
        } else {
            output::print(&format!("sent (message_id {}) to {to}", message_id.unwrap_or("unknown")));
        }
        return Ok(());
    }
    let suppressed = list("suppressed_recipients");
    if !suppressed.is_empty() {
        return die(format!(
            "Cloudflare suppressed {} after a bounce or complaint, so nothing was delivered — check Compute > Email Service > Email Sending > Suppressions; hard bounces expire after 7 days",
            suppressed.join(", ")
        ));
    }
    let bounced = list("permanent_bounces");
    if !bounced.is_empty() {
        return die(format!(
            "Cloudflare reported a permanent bounce for {}, so nothing was delivered — check that the address exists and its mailbox accepts mail",
            bounced.join(", ")
        ));
    }
    die("Cloudflare accepted the request but reported no delivered or queued recipient — check Compute > Email Service > Email Sending in the dashboard before retrying")
}
