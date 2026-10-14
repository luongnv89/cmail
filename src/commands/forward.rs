//! `cmail forward ADDRESS --destination EMAIL`: change where one address forwards.

use crate::cli::ForwardArgs;
use crate::cloudflare::{nonempty_str, rules_for, Cf};
use crate::config::{self, Config, Overrides};
use crate::error::{config_error, die, usage, Error, Result};
use crate::{output, term, ui};
use serde_json::{json, Value};
use std::path::PathBuf;

enum RuleState<'a> {
    Missing,
    Unsupported,
    Editable { rule: &'a Value, current: String, enabled: bool },
}

/// Only one literal "to" rule with a single forward to one destination is edited.
fn editable<'a>(rules: &'a [Value], address: &str) -> RuleState<'a> {
    let matches = rules_for(rules, address);
    match matches.as_slice() {
        [] => RuleState::Missing,
        [rule] => {
            let matchers = rule["matchers"].as_array().map(Vec::as_slice).unwrap_or_default();
            let actions = rule["actions"].as_array().map(Vec::as_slice).unwrap_or_default();
            let literal = matches!(matchers, [m] if m["type"] == "literal" && m["field"] == "to");
            let target = match actions {
                [a] if a["type"] == "forward" => match a["value"].as_array().map(Vec::as_slice) {
                    Some([dest]) => nonempty_str(dest).map(str::to_string),
                    _ => None,
                },
                _ => None,
            };
            let source = rule.get("source").and_then(Value::as_str).unwrap_or("api");
            match target {
                Some(current) if literal && source == "api" => {
                    RuleState::Editable { rule, current, enabled: rule["enabled"] == true }
                }
                _ => RuleState::Unsupported,
            }
        }
        _ => RuleState::Unsupported,
    }
}

pub fn forward(path: PathBuf, args: &ForwardArgs) -> Result<()> {
    let overrides = Overrides { domain: args.domain.clone(), ..Overrides::default() };
    let mut config = Config::load(path, &overrides)?;
    let domain = config.get("DOMAIN").to_string();
    if domain.is_empty() || config.get("CLOUDFLARE_API_TOKEN").is_empty() {
        return config_error(
            "a domain (DOMAIN or --domain) and CLOUDFLARE_API_TOKEN are required; run cmail setup first",
        );
    }
    if !term::stdin_is_tty() {
        return usage("forward requires terminal input to confirm the change; run it interactively");
    }
    let mut local = args.address.clone();
    if let Some((left, right)) = args.address.split_once('@') {
        if right.to_ascii_lowercase() != domain {
            return usage(format!("{} is not on {domain}; pass --domain for another domain", args.address));
        }
        local = left.to_string();
    }
    if !config::local_valid(&local) {
        return usage(format!("ADDRESS must be a local part such as hello, or hello@{domain}"));
    }
    let address = format!("{local}@{domain}");
    let new = args.destination.clone();
    let rerun = format!(
        "cmail forward {address} --destination {new}{}",
        if args.domain.is_some() { format!(" --domain {domain}") } else { String::new() }
    );

    let cf = Cf::new(&config)?;
    let zone_id = cf.zone_id_for_domain(&config)?;
    let zone = cf.get(&format!("/zones/{zone_id}"))?;
    let account = match (&zone["result"]["name"].as_str(), nonempty_str(&zone["result"]["account"]["id"])) {
        (Some(name), Some(account)) if *name == domain => account.to_string(),
        _ => {
            return die(format!(
                "zone {zone_id} is not {domain} or returned malformed data — nothing was changed; check CF_ZONE_ID in cmail config and the Cloudflare dashboard"
            ))
        }
    };
    let rules = cf.rules(&zone_id)?;
    let (rule, old, enabled) = match editable(&rules, &address) {
        RuleState::Missing => {
            return die(format!(
                "{address} has no forwarding rule on {domain} — nothing was changed. Create it first: add {local} to ADDRESSES and run cmail setup"
            ))
        }
        RuleState::Unsupported => {
            return die(format!(
                "{address} has more than one rule, a custom matcher, a Worker-managed rule or an action other than one forward, so cmail will not edit it. Change it in Cloudflare > {domain} > Email > Email Routing > Routing rules. Existing rules were not changed"
            ))
        }
        RuleState::Editable { rule, current, enabled } => (rule.clone(), current, enabled),
    };
    if old.eq_ignore_ascii_case(&new) {
        output::print(&format!("{address} already forwards to {old}; nothing changed."));
        return Ok(());
    }

    let destinations = cf.addresses(&account, None)?;
    let dest = destinations.iter().find(|d| d["email"].as_str().is_some_and(|e| e.eq_ignore_ascii_case(&new)));
    let Some(dest) = dest else {
        ui::warn(&format!(
            "{new} is not a Cloudflare destination address yet; Cloudflare forwards only to verified destinations"
        ));
        if !ui::confirm(&format!("Register {new} and send Cloudflare's verification email to it?")) {
            return die(format!("nothing was changed; {address} still forwards to {old}"));
        }
        let response = cf.register_destination(&account, &new)?;
        if response["result"]["email"].as_str().map(str::to_ascii_lowercase) != Some(new.to_ascii_lowercase()) {
            return die(format!(
                "Cloudflare did not confirm registering {new} — check Email Routing > Destination addresses before retrying"
            ));
        }
        ui::warn(&format!(
            "{new} registered — click the Cloudflare verification link in {new}'s inbox (check Spam), then rerun: {rerun}. {address} is unchanged and still forwards to {old}"
        ));
        return Err(Error::Exit(1));
    };
    if dest["verified"].is_null() {
        return die(format!(
            "{new} is registered but not verified yet — click the Cloudflare verification link in {new}'s inbox (check Spam; resend it from Cloudflare > {domain} > Email > Email Routing > Destination addresses), then rerun: {rerun}. {address} is unchanged and still forwards to {old}"
        ));
    }
    let new = dest["email"].as_str().unwrap_or(&new).to_string(); // Cloudflare's spelling

    if !enabled {
        ui::warn(&format!(
            "the rule for {address} is disabled and stays disabled; enable it in Cloudflare > {domain} > Email > Email Routing > Routing rules"
        ));
    }
    eprintln!("{address}: {old} -> {new}");
    if !ui::confirm(&format!("Change where {address} forwards?")) {
        return die(format!("cancelled — nothing was changed; {address} still forwards to {old}"));
    }
    cf.update_rule_forward(&zone_id, &rule, &new)?;
    sync_config(&mut config, &rules, &rule, &address, &new);
    output::print(&format!("{address} now forwards to {new} (was {old})"));
    output::print(&format!(
        "Test it: from a DIFFERENT mailbox (not {new}), send to {address} and check delivery (including Spam)."
    ));
    Ok(())
}

/// Keep DEST_EMAIL only while it is the one inbox every configured address uses.
fn sync_config(config: &mut Config, before: &[Value], changed: &Value, address: &str, dest: &str) {
    if std::fs::symlink_metadata(&config.path).is_err() {
        return;
    }
    let Ok(saved) = config::read_file(&config.path) else {
        ui::warn("could not reread the configuration; DEST_EMAIL was not updated");
        return;
    };
    let field = |key: &str| saved.iter().find(|(k, _)| k == key).map(|(_, v)| v.clone()).unwrap_or_default();
    let (file_domain, file_addresses, file_dest) =
        (field("DOMAIN").to_ascii_lowercase(), field("ADDRESSES"), field("DEST_EMAIL"));
    let domain = config.get("DOMAIN").to_string();
    if file_domain != domain || file_addresses.is_empty() {
        ui::note(&format!("configuration not changed: {domain} is not the configured domain with ADDRESSES"));
        return;
    }
    let id = |r: &Value| r.get("id").filter(|v| !v.is_null()).or_else(|| r.get("tag")).cloned();
    let rules: Vec<Value> = before
        .iter()
        .map(|r| {
            let mut r = r.clone();
            if id(&r) == id(changed) {
                r["actions"] = json!([{"type": "forward", "value": [dest]}]);
            }
            r
        })
        .collect();
    let configured: Vec<String> =
        config::address_list(&file_addresses).iter().map(|a| format!("{a}@{domain}").to_ascii_lowercase()).collect();
    if !configured.contains(&address.to_ascii_lowercase()) {
        ui::note(&format!("configuration not changed: {address} is not in ADDRESSES"));
        return;
    }
    let pending: Vec<&String> = configured
        .iter()
        .filter(|a| {
            let matches = rules_for(&rules, a);
            let fine = matches!(matches.as_slice(), [r] if {
                let actions = r["actions"].as_array().map(Vec::as_slice).unwrap_or_default();
                matches!(actions, [x] if x["type"] == "forward" && x["value"].as_array().is_some_and(|v| {
                    v.len() == 1 && v[0].as_str().is_some_and(|e| e.eq_ignore_ascii_case(dest))
                }))
            });
            !fine
        })
        .collect();
    if !pending.is_empty() {
        let list = pending.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ");
        let shown = if file_dest.is_empty() { "unset" } else { &file_dest };
        ui::warn(&format!(
            "DEST_EMAIL in the configuration stays {shown} because these configured addresses forward elsewhere: {list}. cmail setup checks every address against DEST_EMAIL, so it will report them as conflicting until all addresses forward to one inbox (use cmail forward for each)"
        ));
    } else if !file_dest.eq_ignore_ascii_case(dest) {
        config.put("DOMAIN", &file_domain);
        match config.set("DEST_EMAIL", dest) {
            Ok(()) => ui::ok(&format!("saved DEST_EMAIL={dest}: every configured address now forwards there")),
            Err(_) => {
                ui::warn(&format!("could not save DEST_EMAIL={dest}; set it with cmail config set DEST_EMAIL {dest}"))
            }
        }
    }
}
