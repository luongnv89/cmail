//! Cloudflare REST API client for zones and Email Routing.
//!
//! Every failure explains what to check next and never prints the token.

use crate::config::Config;
use crate::error::{die, Result};
use crate::ui;
use serde_json::{json, Map, Value};
use std::time::Duration;

pub const API: &str = "https://api.cloudflare.com/client/v4";

pub struct Cf {
    token: String,
    base: String,
    domain: String,
}

/// Base URL: the real API, or (tests only) `CMAIL_CF_API` on https or loopback http.
fn base_url() -> Result<String> {
    match std::env::var("CMAIL_CF_API").ok().filter(|v| !v.is_empty()) {
        None => Ok(API.to_string()),
        Some(url) => {
            let loopback =
                ["http://127.0.0.1:", "http://localhost:", "http://[::1]:"].iter().any(|p| url.starts_with(p));
            if url.starts_with("https://") || loopback {
                Ok(url.trim_end_matches('/').to_string())
            } else {
                die("CMAIL_CF_API must be an https:// URL or a loopback http:// URL")
            }
        }
    }
}

/// jq truthiness: everything except null and false.
pub fn truthy(value: &Value) -> bool {
    !matches!(value, Value::Null | Value::Bool(false))
}

pub fn nonempty_str(value: &Value) -> Option<&str> {
    value.as_str().filter(|s| !s.is_empty())
}

fn whole_number(value: &Value) -> Option<u64> {
    let f = value.as_f64()?;
    (f >= 0.0 && f.fract() == 0.0).then_some(f as u64)
}

pub fn account_recovery(domain: &str) {
    ui::always(&format!(
        "To unlock account discovery:
  1. Open https://dash.cloudflare.com/profile/api-tokens and edit your token.
     An active token is not proof of account/zone access. Under Account Resources,
     include the account that owns {domain}; under Zone Resources, include that
     account's zones (including {domain} if it already exists).
     Zone creation needs Zone > Zone > Edit. Destination registration needs
     Account > Email Routing Addresses > Edit.
  2. Open https://dash.cloudflare.com/ and select the intended account/domain.
     Copy its Account ID (not Zone ID) from the dashboard and add it to your config:
       cmail config set CF_ACCOUNT_ID <32-character account ID>
     This skips account listing; it does NOT grant zone read/create permissions.
     If the domain already exists but was not found, fix its token scope first.
  3. If you create a replacement token, update CLOUDFLARE_API_TOKEN in your config
     locally (do not share it), then rerun cmail setup.
"
    ));
}

impl Cf {
    pub fn new(config: &Config) -> Result<Cf> {
        Ok(Cf {
            token: config.get("CLOUDFLARE_API_TOKEN").to_string(),
            base: base_url()?,
            domain: config.get("DOMAIN").to_string(),
        })
    }

    pub fn set_token(&mut self, token: &str) {
        self.token = token.to_string();
    }

    fn send(
        &self,
        method: &str,
        path: &str,
        body: Option<&Value>,
        seconds: u64,
    ) -> std::result::Result<(u16, String), String> {
        let timeout = Duration::from_secs(seconds.max(1));
        let agent = ureq::AgentBuilder::new().timeout_connect(timeout).timeout(timeout).build();
        let request = agent
            .request(method, &format!("{}{path}", self.base))
            .set("Authorization", &format!("Bearer {}", self.token))
            .set("Content-Type", "application/json");
        let response = match body {
            Some(body) => request.send_string(&body.to_string()),
            None => request.call(),
        };
        match response {
            Ok(r) => Ok((r.status(), r.into_string().unwrap_or_default())),
            Err(ureq::Error::Status(code, r)) => Ok((code, r.into_string().unwrap_or_default())),
            Err(ureq::Error::Transport(t)) => Err(t.kind().to_string()),
        }
    }

    /// True only for an active token; errors are silent (doctor reports them).
    pub fn token_valid(&self) -> bool {
        if self.token.is_empty() {
            return false;
        }
        match self.send("GET", "/user/tokens/verify", None, ui::ctx().timeout as u64) {
            Ok((200..=299, body)) => serde_json::from_str::<Value>(&body)
                .is_ok_and(|v| v.pointer("/result/status").and_then(Value::as_str) == Some("active")),
            _ => false,
        }
    }

    pub fn get(&self, path: &str) -> Result<Value> {
        self.request("GET", path, None, None)
    }

    /// One API call with shared diagnostics. `limit` shortens the timeout for bounded waits.
    pub fn request(&self, method: &str, path: &str, body: Option<&Value>, limit: Option<u64>) -> Result<Value> {
        let configured = ui::ctx().timeout as u64;
        let seconds = limit.map_or(configured, |l| l.min(configured));
        ui::verbose(&format!("Request: Cloudflare {method} {path} (timeout {configured}s)"));
        let (status, body) = match self.send(method, path, body, seconds) {
            Ok(result) => result,
            Err(kind) => {
                ui::warn("check your connection, DNS, proxy and https://www.cloudflarestatus.com/; this is not evidence of an invalid token");
                if method != "GET" {
                    ui::warn("the write outcome is unknown — inspect the Cloudflare dashboard before retrying");
                }
                return die(format!("Cloudflare request failed: {method} {path} ({kind})"));
            }
        };
        let parsed: Option<Value> = serde_json::from_str(&body).ok();
        let success = parsed.as_ref().is_some_and(|v| v.get("success") == Some(&Value::Bool(true)));
        if (200..300).contains(&status) && success {
            return Ok(parsed.unwrap());
        }
        let mut detail = match &parsed {
            _ if body.is_empty() => "empty response body".to_string(),
            Some(v) => match v.get("errors") {
                Some(errors) if truthy(errors) => errors.to_string(),
                _ => v.to_string(),
            },
            None => format!("non-JSON response: {}", body.chars().take(500).collect::<String>()),
        };
        if !self.token.is_empty() {
            detail = detail.replace(&self.token, "[redacted]");
        }
        let detail: String = detail.chars().take(1000).collect();
        let domain = if self.domain.is_empty() { "your domain" } else { &self.domain };
        let route = path.split('?').next().unwrap_or(path);
        if status == 401 || status == 403 {
            if route.starts_with("/accounts/") && route.contains("/email/routing/addresses") {
                ui::warn("check token access to this account and grant Account > Email Routing Addresses > Edit");
            } else if route.starts_with("/zones/") && route.contains("/email/routing/rules") {
                ui::warn("check token access to this zone and grant Zone > Email Routing Rules > Edit");
            } else if route.starts_with("/zones/") && route.contains("/email/routing") {
                ui::warn("check token access to this zone and grant Zone > Zone Settings > Edit");
            } else if route == "/accounts" {
                account_recovery(domain);
            } else if route == "/zones" || route.starts_with("/zones/") {
                ui::warn(&format!(
                    "check Zone Resources includes {domain} (or its account's zones for creation); grant Zone > Zone > Edit"
                ));
            } else if route == "/user/tokens/verify" {
                ui::warn("token rejected: replace CLOUDFLARE_API_TOKEN in your config with an active API token from https://dash.cloudflare.com/profile/api-tokens");
            } else {
                ui::warn(&format!("check token resource access and permissions for {path}"));
            }
        }
        if route.starts_with("/zones/") && route.ends_with("/email/routing/dns") {
            ui::warn(&format!(
                "open Cloudflare > {domain} > Email > Email Routing; check conflicting MX/TXT records. Do not delete an existing mail provider's records without planning the migration"
            ));
        }
        if status == 429 {
            ui::warn("Cloudflare rate limit reached — wait before rerunning cmail setup");
        } else if (500..600).contains(&status) {
            ui::warn("Cloudflare service error — check https://www.cloudflarestatus.com/ and retry later; inspect the dashboard first if a write was attempted");
        }
        die(format!("Cloudflare API error: {method} {path} (HTTP {status}): {detail}"))
    }

    /// Every destination address of an account, across all pages.
    pub fn addresses(&self, account: &str, limit: Option<u64>) -> Result<Vec<Value>> {
        let mut records = Vec::new();
        let mut page = 1u64;
        loop {
            if page > 1000 {
                return die("destination listing exceeded 1000 pages — no complete result available");
            }
            let path = format!("/accounts/{account}/email/routing/addresses?per_page=50&page={page}");
            let response = self.request("GET", &path, None, limit)?;
            let batch = match response.get("result").and_then(Value::as_array) {
                Some(batch)
                    if batch.iter().all(|d| {
                        nonempty_str(&d["email"]).is_some()
                            && (d["verified"].is_null() || nonempty_str(&d["verified"]).is_some())
                    }) =>
                {
                    batch.clone()
                }
                _ => return die("Cloudflare returned invalid destination addresses"),
            };
            let count = batch.len();
            records.extend(batch);
            let total = response.pointer("/result_info/total_pages").cloned().unwrap_or(Value::Null);
            let pages =
                if total.is_null() { Some(if count == 50 { page + 1 } else { page }) } else { whole_number(&total) };
            let Some(pages) = pages else { return die("Cloudflare returned invalid destination pagination") };
            if page >= pages {
                break;
            }
            page += 1;
        }
        Ok(records)
    }

    /// Every routing rule of a zone, across all pages.
    pub fn rules(&self, zone: &str) -> Result<Vec<Value>> {
        let mut records = Vec::new();
        let mut page = 1u64;
        loop {
            if page > 1000 {
                return die("forwarding-rule listing exceeded 1000 pages");
            }
            let response = self.get(&format!("/zones/{zone}/email/routing/rules?per_page=50&page={page}"))?;
            let Some(batch) = response.get("result").and_then(Value::as_array).cloned() else {
                return die("Cloudflare returned invalid forwarding rules — no complete result available");
            };
            let count = batch.len() as u64;
            records.extend(batch);
            let total = response.pointer("/result_info/total_pages").cloned().unwrap_or(Value::Null);
            let pages =
                if truthy(&total) { whole_number(&total) } else { Some(if count >= 50 { page + 1 } else { page }) };
            let Some(pages) = pages else { return die("Cloudflare returned invalid forwarding-rule pagination") };
            if page >= pages {
                break;
            }
            page += 1;
        }
        Ok(records)
    }

    /// The saved CF_ZONE_ID, else the single zone named DOMAIN.
    pub fn zone_id_for_domain(&self, config: &Config) -> Result<String> {
        let saved = config.get("CF_ZONE_ID");
        if !saved.is_empty() {
            return Ok(saved.to_string());
        }
        let domain = config.get("DOMAIN");
        let response = self.get(&format!("/zones?name={domain}"))?;
        let found: Option<Vec<&Value>> = response
            .get("result")
            .and_then(Value::as_array)
            .map(|zones| zones.iter().filter(|z| z["name"].as_str() == Some(domain)).collect());
        match found.as_deref() {
            Some([zone]) => match zone["id"].as_str() {
                Some(id) => Ok(id.to_string()),
                None => die(format!(
                    "zone for {domain} not uniquely found; check Cloudflare token resources and cmail setup"
                )),
            },
            _ => die(format!("zone for {domain} not uniquely found; check Cloudflare token resources and cmail setup")),
        }
    }

    /// Owning account of a zone; never assume the first account owns it.
    pub fn account_for_zone(&self, zone: &str) -> Result<String> {
        let response = self.get(&format!("/zones/{zone}"))?;
        match nonempty_str(&response["result"]["account"]["id"]) {
            Some(account) => Ok(account.to_string()),
            None => die("Cloudflare zone is missing its account ID — no destination change applied"),
        }
    }

    /// Register a destination and send Cloudflare's verification email; never waits.
    pub fn register_destination(&self, account: &str, email: &str) -> Result<Value> {
        self.request(
            "POST",
            &format!("/accounts/{account}/email/routing/addresses"),
            Some(&json!({"email": email})),
            None,
        )
    }

    /// Replace only the forward destination of one rule, then read it back.
    /// PUT replaces the whole rule, so name, matchers, priority and enabled are resent.
    pub fn update_rule_forward(&self, zone: &str, rule: &Value, destination: &str) -> Result<()> {
        let id =
            rule.get("id").filter(|v| truthy(v)).or_else(|| rule.get("tag")).and_then(Value::as_str).filter(|id| {
                (1..=64).contains(&id.len()) && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
            });
        let Some(id) = id else { return die("forwarding rule has no usable ID — nothing was changed") };
        let mut payload = Map::new();
        for key in ["name", "matchers", "priority", "enabled"] {
            if let Some(value) = rule.get(key).filter(|v| !v.is_null()) {
                payload.insert(key.into(), value.clone());
            }
        }
        payload.insert("actions".into(), json!([{"type": "forward", "value": [destination]}]));
        let payload = Value::Object(payload);
        self.request("PUT", &format!("/zones/{zone}/email/routing/rules/{id}"), Some(&payload), None)?;
        let response = self.get(&format!("/zones/{zone}/email/routing/rules/{id}"))?;
        let result = &response["result"];
        if result["actions"] != payload["actions"] || result["matchers"] != payload["matchers"] {
            let domain = if self.domain.is_empty() { "your domain" } else { &self.domain };
            return die(format!(
                "Cloudflare accepted the change but the rule does not read back as forwarding to {destination} — open Cloudflare > {domain} > Email > Email Routing > Routing rules and check where the address forwards"
            ));
        }
        Ok(())
    }

    /// Zone, routing, destination, and rule state for `cmail status`.
    pub fn status_data(&self, zone_id: &str, domain: &str) -> Result<Value> {
        let zone = self.get(&format!("/zones/{zone_id}"))?;
        let z = &zone["result"];
        if z["name"].as_str() != Some(domain) || !z["status"].is_string() || nonempty_str(&z["account"]["id"]).is_none()
        {
            return die("saved zone does not match DOMAIN or returned malformed data; check cmail config and the Cloudflare dashboard");
        }
        let account = z["account"]["id"].as_str().unwrap();
        let routing = self.get(&format!("/zones/{zone_id}/email/routing"))?;
        if !routing["result"]["enabled"].is_boolean() {
            return die("Cloudflare returned invalid Email Routing state");
        }
        let destinations = self.addresses(account, None)?;
        let rules = self.rules(zone_id)?;
        let pick = |v: &Value, k: &str| v.get(k).cloned().unwrap_or(Value::Null);
        Ok(json!({
            "zone": {"id": zone_id, "name": z["name"], "status": z["status"], "account_id": account,
                     "nameservers": if truthy(&z["name_servers"]) { z["name_servers"].clone() } else { json!([]) }},
            "routing": {"enabled": routing["result"]["enabled"],
                        "status": if truthy(&routing["result"]["status"]) { routing["result"]["status"].clone() } else { json!("unknown") }},
            "destinations": destinations.iter().map(|d| json!({"email": d["email"], "verified": !d["verified"].is_null(), "verified_at": d["verified"]})).collect::<Vec<_>>(),
            "rules": rules.iter().map(|r| json!({"id": pick(r, "id"), "enabled": pick(r, "enabled"), "matchers": pick(r, "matchers"), "actions": pick(r, "actions")})).collect::<Vec<_>>(),
        }))
    }

    /// Every address on a domain and where it forwards, for `cmail list`.
    pub fn list_data(&self, zone_id: &str, domain: &str) -> Result<Value> {
        let zone = self.get(&format!("/zones/{zone_id}"))?;
        let z = &zone["result"];
        if z["name"].as_str() != Some(domain) || nonempty_str(&z["account"]["id"]).is_none() {
            return die("zone does not match DOMAIN or returned malformed data; check cmail config and the Cloudflare dashboard");
        }
        let destinations = self.addresses(z["account"]["id"].as_str().unwrap(), None)?;
        let rules = self.rules(zone_id)?;
        let catch_all = self.get(&format!("/zones/{zone_id}/email/routing/rules/catch_all"))?;
        let catch_all = catch_all.get("result").cloned().unwrap_or(Value::Null);
        if !(catch_all.is_null() || catch_all.is_object()) {
            return die("Cloudflare returned an invalid catch-all rule");
        }
        // Destination state decides whether forwarding actually delivers.
        let state = |email: &str| -> &'static str {
            let email = email.to_ascii_lowercase();
            destinations
                .iter()
                .rev()
                .find(|d| d["email"].as_str().map(str::to_ascii_lowercase).as_deref() == Some(&email))
                .map_or("unregistered", |d| if d["verified"].is_null() { "unverified" } else { "verified" })
        };
        let actions = |rule: &Value| -> Value {
            let list = rule.get("actions").and_then(Value::as_array).cloned().unwrap_or_default();
            Value::Array(
                list.iter()
                    .map(|a| {
                        let kind = if truthy(&a["type"]) { a["type"].clone() } else { json!("unknown") };
                        let value = if truthy(&a["value"]) { a["value"].clone() } else { json!([]) };
                        let mut out = json!({"type": kind, "value": value});
                        if out["type"] == "forward" {
                            let targets: Vec<Value> = out["value"]
                                .as_array()
                                .map(|v| {
                                    v.iter()
                                        .map(|e| json!({"email": e, "state": state(e.as_str().unwrap_or(""))}))
                                        .collect()
                                })
                                .unwrap_or_default();
                            out["destinations"] = Value::Array(targets);
                        }
                        out
                    })
                    .collect(),
            )
        };
        let matchers = |rule: &Value| rule.get("matchers").and_then(Value::as_array).cloned().unwrap_or_default();
        let rule_id = |rule: &Value| match rule.get("id") {
            Some(id) if truthy(id) => id.clone(),
            _ => rule.get("tag").cloned().unwrap_or(Value::Null),
        };
        let mut addresses: Vec<Value> = rules
            .iter()
            .filter(|r| !matchers(r).iter().any(|m| m["type"] == "all"))
            .map(|r| {
                let address = matchers(r)
                    .iter()
                    .find(|m| m["type"] == "literal" && m["field"] == "to")
                    .map_or(Value::Null, |m| m["value"].clone());
                json!({
                    "address": address, "rule_id": rule_id(r),
                    "name": if truthy(&r["name"]) { r["name"].clone() } else { json!("") },
                    "enabled": r["enabled"] == true, "priority": r.get("priority").cloned().unwrap_or(Value::Null),
                    "matchers": Value::Array(matchers(r)), "actions": actions(r),
                })
            })
            .collect();
        addresses.sort_by_key(|a| a["address"].as_str().unwrap_or("~").to_ascii_lowercase());
        let catch_all = if catch_all.is_null() || (matchers_empty_actions(&catch_all) && catch_all["enabled"].is_null())
        {
            Value::Null
        } else {
            json!({"rule_id": rule_id(&catch_all), "enabled": catch_all["enabled"] == true, "actions": actions(&catch_all)})
        };
        Ok(
            json!({"domain": z["name"], "zone_id": zone_id, "zone_status": z["status"], "addresses": addresses, "catch_all": catch_all}),
        )
    }
}

fn matchers_empty_actions(rule: &Value) -> bool {
    rule.get("actions").and_then(Value::as_array).is_none_or(Vec::is_empty)
}

/// Rules matching `address` (any matcher value, case-insensitive).
pub fn rules_for<'a>(rules: &'a [Value], address: &str) -> Vec<&'a Value> {
    let address = address.to_ascii_lowercase();
    rules
        .iter()
        .filter(|r| {
            r.get("matchers").and_then(Value::as_array).is_some_and(|ms| {
                ms.iter().any(|m| m["value"].as_str().is_some_and(|v| v.to_ascii_lowercase() == address))
            })
        })
        .collect()
}

/// Human-readable targets of a rule's actions.
pub fn describe_targets(actions: &Value, list_style: bool) -> String {
    let actions = actions.as_array().cloned().unwrap_or_default();
    if actions.is_empty() {
        return "no action".into();
    }
    actions
        .iter()
        .map(|a| {
            let kind = a["type"].as_str().unwrap_or("unknown");
            let strings = |v: &Value| -> Vec<String> {
                v.as_array()
                    .map(|v| v.iter().map(|e| e.as_str().unwrap_or("").to_string()).collect())
                    .unwrap_or_default()
            };
            if kind == "forward" {
                if list_style {
                    let dests = a["destinations"].as_array().cloned().unwrap_or_default();
                    if dests.is_empty() {
                        return "forward (no destination)".into();
                    }
                    return dests
                        .iter()
                        .map(|d| {
                            format!("{} ({})", d["email"].as_str().unwrap_or(""), d["state"].as_str().unwrap_or(""))
                        })
                        .collect::<Vec<_>>()
                        .join(", ");
                }
                let values = strings(&a["value"]);
                if values.is_empty() {
                    "forward (no destination)".into()
                } else {
                    values.join(", ")
                }
            } else if kind == "drop" && list_style {
                "drop".into()
            } else if a["value"].is_array() {
                format!("{kind} {}", strings(&a["value"]).join(", ")).trim_end().to_string()
            } else {
                kind.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("; ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn targets_text() {
        assert_eq!(
            describe_targets(&json!([{"type": "forward", "value": ["a@x.io", "b@x.io"]}]), false),
            "a@x.io, b@x.io"
        );
        assert_eq!(describe_targets(&json!([{"type": "worker", "value": ["parser"]}]), false), "worker parser");
        assert_eq!(describe_targets(&json!([{"type": "drop"}]), false), "drop");
        assert_eq!(describe_targets(&json!([]), false), "no action");
        assert_eq!(describe_targets(&json!([{"type": "forward", "value": []}]), false), "forward (no destination)");
    }

    #[test]
    fn rule_matching_is_case_insensitive() {
        let rules = vec![json!({"matchers": [{"value": "Hello@Example.com"}]}), json!({"matchers": [{"type": "all"}]})];
        assert_eq!(rules_for(&rules, "hello@example.com").len(), 1);
    }
}
