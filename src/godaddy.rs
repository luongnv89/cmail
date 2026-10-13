//! GoDaddy automation through the external `gddy` CLI (opt-in: REGISTRAR=godaddy).

use crate::config::{self, Config};
use crate::error::{config_error, die, Result};
use crate::ui;
use serde_json::Value;
use std::process::{Command, Stdio};

/// How a gddy call's output is wired.
#[derive(Clone, Copy)]
pub enum Io {
    /// Capture stdout; discard stderr.
    Capture,
    /// Capture stdout; show stderr.
    CaptureShowErrors,
    /// Show stdout on stderr (results stay pipeable).
    ToStderr,
    /// Discard everything.
    Silent,
}

/// Run `gddy ARGS --timeout Ns` with GDDY_ENV and GDDY_PAT exported.
/// Login waits up to --wait-timeout; everything else uses --timeout.
pub fn gddy(config: &Config, args: &[&str], io: Io) -> (bool, String) {
    let ctx = ui::ctx();
    let login = args.len() >= 2 && args[0] == "auth" && args[1] == "login";
    let timeout = if login { ctx.wait_timeout } else { ctx.timeout as u64 };
    let mut command = Command::new("gddy");
    command.args(args).arg("--timeout").arg(format!("{timeout}s")).env("GDDY_ENV", config.get("GDDY_ENV"));
    if !config.get("GDDY_PAT").is_empty() {
        command.env("GDDY_PAT", config.get("GDDY_PAT"));
    }
    let (stdout, stderr) = match io {
        Io::Capture => (Stdio::piped(), Stdio::null()),
        Io::CaptureShowErrors => (Stdio::piped(), Stdio::inherit()),
        Io::ToStderr => (Stdio::from(std::io::stderr()), Stdio::inherit()),
        Io::Silent => (Stdio::null(), Stdio::null()),
    };
    match command.stdout(stdout).stderr(stderr).output() {
        Ok(output) => (output.status.success(), String::from_utf8_lossy(&output.stdout).into_owned()),
        Err(_) => (false, String::new()),
    }
}

/// A live (unexpired) gddy login exists for the selected environment.
pub fn auth_available(config: &Config) -> bool {
    let (_, out) = gddy(config, &["auth", "status", "--json"], Io::Capture);
    serde_json::from_str::<Value>(&out).is_ok_and(|v| {
        v["data"].as_array().is_some_and(|items| {
            items.iter().any(|i| i["env"].as_str() == Some(config.get("GDDY_ENV")) && i["expired"] == false)
        })
    })
}

pub fn ensure_auth(config: &Config) -> Result<()> {
    let env = config.get("GDDY_ENV").to_string();
    ui::step(&format!("GoDaddy authentication ({env})"));
    if !config.get("GDDY_PAT").is_empty() {
        ui::ok("GDDY_PAT set — using PAT");
        return Ok(());
    }
    if !auth_available(config) {
        ui::log("no valid credential — starting OAuth (a browser window will open)");
        let (ok, _) = gddy(config, &["auth", "login", "--env", &env], Io::ToStderr);
        if !ok {
            return die(format!(
                "gddy auth login failed — check network/browser access and the correct GoDaddy account; retry gddy auth login --env {env}, then re-run cmail setup. If using a PAT, renew/recreate it for {env} and update GDDY_PAT privately (never paste it into logs)"
            ));
        }
    }
    ui::ok("gddy authenticated");
    Ok(())
}

/// Pick an owned domain, or offer registration of a new one; saves DOMAIN.
pub fn pick_domain(config: &mut Config) -> Result<()> {
    ui::step("Choose domain");
    if !config.get("DOMAIN").is_empty() {
        ui::ok(&format!("DOMAIN={} (from config)", config.get("DOMAIN")));
        return Ok(());
    }
    let env = config.get("GDDY_ENV").to_string();
    let (ok, out) = gddy(config, &["domain", "list", "--env", &env, "--json"], Io::Capture);
    if !ok {
        return die(format!(
            "could not list GoDaddy domains — check network, account access and gddy auth login --env {env}; renew GDDY_PAT privately if used. Check domains in the GoDaddy dashboard or run gddy domain list --env {env} --json, then re-run cmail setup"
        ));
    }
    let names: Option<Vec<String>> = serde_json::from_str::<Value>(&out).ok().and_then(|v| {
        v["data"].as_array().map(|items| {
            let mut names: Vec<String> = items
                .iter()
                .filter_map(|i| {
                    i["domain"]
                        .as_str()
                        .filter(|s| !s.is_empty())
                        .or_else(|| i["name"].as_str().filter(|s| !s.is_empty()))
                })
                .map(str::to_string)
                .collect();
            names.sort();
            names
        })
    });
    let Some(names) = names else {
        return die(format!(
            "could not read GoDaddy domain list — check gddy domain list --env {env} --json and your GoDaddy dashboard; update gddy if its response format changed, then re-run cmail setup"
        ));
    };
    if !names.is_empty() {
        let mut text = String::from("Your GoDaddy domains:\n");
        for name in &names {
            text.push_str(&format!("  - {name}\n"));
        }
        text.push_str("  - (type any other name to register a new one)\n");
        ui::always(&text);
    }
    let Some(value) = ui::ask("domain to use", false) else {
        return die("domain input unavailable — run cmail setup in an interactive terminal, or set DOMAIN in your private config");
    };
    if value.is_empty() {
        return die(
            "domain required — set DOMAIN in your private config or enter a domain when re-running cmail setup",
        );
    }
    if !config::domain_valid(&value) {
        return config_error("DOMAIN must be a domain name without a scheme or path");
    }
    if !names.contains(&value) {
        maybe_register(config, &value)?;
    }
    config.set("DOMAIN", &value)
}

fn maybe_register(config: &Config, domain: &str) -> Result<()> {
    let env = config.get("GDDY_ENV").to_string();
    if gddy(config, &["domain", "get", domain, "--env", &env], Io::Silent).0 {
        return Ok(());
    }
    ui::warn(&format!(
        "could not confirm {domain} in your GoDaddy account — check the dashboard, network and authentication before considering a purchase"
    ));
    if !gddy(config, &["domain", "available", domain, "--env", &env], Io::ToStderr).0 {
        return die(format!(
            "could not check availability for {domain} — check network, gddy auth login --env {env} and the GoDaddy dashboard, then re-run cmail setup; do not purchase until ownership/availability is clear"
        ));
    }
    if !ui::confirm("attempt registration via gddy now? (charges your GoDaddy account)") {
        return die(format!(
            "registration declined — check whether you already own {domain} in GoDaddy; register it if needed, then set DOMAIN and re-run cmail setup"
        ));
    }
    let (ok, out) = gddy(config, &["domain", "quote", domain, "--env", &env, "--json", "--fields", "all"], Io::Capture);
    if !ok {
        return die(format!(
            "quote failed — check network, authentication for {env} and domain availability. Check GoDaddy orders and domain ownership before retrying any purchase; once resolved, re-run cmail setup"
        ));
    }
    let quote: Value = serde_json::from_str(&out).unwrap_or(Value::Null);
    let d = &quote["data"];
    let nonempty = |v: &Value| v.as_str().is_some_and(|s| !s.is_empty());
    let agreements_ok = d["requiredAgreements"].as_array().is_some_and(|list| {
        list.iter().all(|a| nonempty(&a["title"]) && a["url"].as_str().is_some_and(|u| u.starts_with("https://")))
    });
    let valid = d["domain"].as_str() == Some(domain)
        && d["available"] == true
        && nonempty(&d["price"])
        && nonempty(&d["currency"])
        && agreements_ok
        && nonempty(&d["quoteToken"]);
    if !valid {
        return die("quote missing price, token, or agreement title/link; inspect gddy domain quote before purchasing");
    }
    let token = d["quoteToken"].as_str().unwrap().to_string();
    let mut summary = serde_json::Map::new();
    for key in ["domain", "price", "currency", "period", "renewalPrice", "fees", "requiredAgreements"] {
        summary.insert(key.into(), d.get(key).cloned().unwrap_or(Value::Null));
    }
    ui::always(&format!("{}\n", serde_json::to_string_pretty(&Value::Object(summary)).unwrap_or_default()));
    if !ui::confirm_payment(
        &format!("purchase {domain} at the quoted price, including fees, and accept the displayed agreements?"),
        domain,
    ) {
        return die("purchase declined — no purchase requested; check GoDaddy orders/domain ownership, then re-run cmail setup when ready");
    }
    let args = ["domain", "purchase", "--quote-token", &token, "--agree", "--confirm", "--env", &env];
    if !gddy(config, &args, Io::Silent).0 {
        return die(format!(
            "purchase failed — the outcome may be uncertain; check GoDaddy orders, billing and domain ownership BEFORE retrying purchase to avoid duplicate charges. Check network/authentication for {env}; if purchased, set DOMAIN and re-run cmail setup; otherwise resolve the order or contact GoDaddy support first"
        ));
    }
    ui::ok(&format!("registered {domain}"));
    Ok(())
}

pub fn normalize_nameservers(list: &[String]) -> Vec<String> {
    let mut out: Vec<String> = list.iter().map(|n| n.to_ascii_lowercase().trim_end_matches('.').to_string()).collect();
    out.sort();
    out.dedup();
    out
}

/// Current GoDaddy nameservers, normalized; `None` when unreadable.
pub fn current_nameservers(json: &str) -> Option<Vec<String>> {
    let v: Value = serde_json::from_str(json).ok()?;
    let list = v["data"]["nameServers"].as_array()?;
    if list.is_empty() || !list.iter().all(|n| n.as_str().is_some_and(|s| !s.is_empty())) {
        return None;
    }
    Some(normalize_nameservers(&list.iter().map(|n| n.as_str().unwrap().to_string()).collect::<Vec<_>>()))
}

/// Point the domain at Cloudflare after an explicit confirmation; skip when it already does.
pub fn set_nameservers(config: &Config, nameservers: &[String]) -> Result<()> {
    let domain = config.get("DOMAIN").to_string();
    let env = config.get("GDDY_ENV").to_string();
    ui::step(&format!("GoDaddy: point {domain} nameservers at Cloudflare"));
    let (ok, out) = gddy(config, &["domain", "get", &domain, "--env", &env, "--json"], Io::CaptureShowErrors);
    if !ok {
        return die(format!(
            "could not verify current nameservers — no change applied; check network, account access and gddy auth login --env {env}. Check GoDaddy dashboard > domain > DNS > Nameservers, or gddy domain get {domain} --env {env} --json, then re-run cmail setup"
        ));
    }
    let Some(current) = current_nameservers(&out) else {
        return die(format!(
            "could not read current nameservers — no change applied; inspect GoDaddy dashboard > domain > DNS > Nameservers, or gddy domain get {domain} --env {env} --json. Check/update gddy for response-format issues, then re-run cmail setup"
        ));
    };
    let desired = normalize_nameservers(nameservers);
    let listed = nameservers.join(" ");
    if current == desired {
        ui::ok(&format!("nameservers already point at Cloudflare: {listed} — skipping update"));
        return Ok(());
    }
    ui::note(&format!("current nameservers: {}", serde_json::to_string(&current).unwrap_or_default()));
    ui::note(&format!("desired nameservers: {}", serde_json::to_string(&desired).unwrap_or_default()));
    ui::warn(&format!(
        "this replaces ALL nameservers for {domain} — copy existing DNS records (web, mail/MX, TXT and other services) to Cloudflare first or those services may break"
    ));
    // DRY_RUN=1 never reaches this step: setup then runs the read-only plan instead.
    let mut args: Vec<&str> = vec!["domain", "nameservers", "set"];
    for ns in nameservers {
        args.push("--nameserver");
        args.push(ns);
    }
    args.extend([domain.as_str(), "--env", env.as_str()]);
    if !ui::confirm("apply nameserver change") {
        return die("aborted before nameserver change — migrate existing DNS records to Cloudflare, then re-run cmail setup when ready");
    }
    if !gddy(config, &args, Io::Silent).0 {
        return die(format!(
            "nameserver update failed — it may still have applied; check GoDaddy dashboard > domain > DNS > Nameservers or gddy domain get {domain} --env {env} --json against the desired nameservers above. Check network/authentication and domain permissions/locks; once resolved, re-run cmail setup (matching nameservers skip the write)"
        ));
    }
    ui::ok(&format!(
        "nameservers set: {listed} (change submitted) — allow DNS propagation; verify in the GoDaddy dashboard or with gddy domain get {domain} --env {env} --json"
    ));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nameserver_normalization() {
        let got =
            current_nameservers(r#"{"data":{"nameServers":["Bob.NS.cloudflare.com.","alice.ns.cloudflare.com"]}}"#);
        assert_eq!(got, Some(vec!["alice.ns.cloudflare.com".into(), "bob.ns.cloudflare.com".into()]));
        assert_eq!(current_nameservers(r#"{"data":{"nameServers":[]}}"#), None);
        assert_eq!(current_nameservers("not json"), None);
    }
}
