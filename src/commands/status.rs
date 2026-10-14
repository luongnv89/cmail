//! `cmail status` and `cmail list`: read-only reports of Cloudflare state.

use crate::cloudflare::{describe_targets, Cf};
use crate::config::{Config, Overrides};
use crate::error::{config_error, Result};
use crate::output::{self, envelope, record};
use crate::style::{boxed, clean, span, status as mark, table, Level, Line, Mode, Role};
use crate::ui;
use serde_json::Value;
use std::path::PathBuf;

fn load(path: PathBuf, overrides: &Overrides, missing: &str) -> Result<(Config, Cf)> {
    let config = Config::load(path, overrides)?;
    if config.get("DOMAIN").is_empty() || config.get("CLOUDFLARE_API_TOKEN").is_empty() {
        return config_error(missing);
    }
    let cf = Cf::new(&config)?;
    Ok((config, cf))
}

fn text(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn matched(rule: &Value) -> String {
    let matchers = rule["matchers"].as_array().cloned().unwrap_or_default();
    if matchers.iter().any(|m| m["type"] == "all") {
        "catch-all".into()
    } else {
        matchers.first().and_then(|m| m["value"].as_str()).unwrap_or("custom matcher").to_string()
    }
}

fn cell(role: Role, value: &str) -> Line {
    vec![span(role, clean(value, false))]
}

pub fn status(path: PathBuf) -> Result<()> {
    let (config, cf) =
        load(path, &Overrides::default(), "DOMAIN and CLOUDFLARE_API_TOKEN are required; run cmail setup")?;
    let zone = cf.zone_id_for_domain(&config)?;
    let data = cf.status_data(&zone, config.get("DOMAIN"))?;
    if ui::ctx().json {
        output::print(&envelope("status", data));
    } else {
        output::print(&render_status(&ui::ctx().out, &data));
    }
    Ok(())
}

pub fn render_status(mode: &Mode, data: &Value) -> String {
    let zone_status = text(&data["zone"]["status"]);
    let enabled = data["routing"]["enabled"] == true;
    let routing = text(&data["routing"]["status"]);
    let destinations = data["destinations"].as_array().cloned().unwrap_or_default();
    let rules = data["rules"].as_array().cloned().unwrap_or_default();
    let on_off = |v: bool| if v { "enabled" } else { "disabled" };
    if !mode.styled {
        let mut lines = vec![
            record(&["zone", &text(&data["zone"]["name"]), &zone_status]),
            record(&["routing", &routing, on_off(enabled)]),
        ];
        for d in &destinations {
            let state = if d["verified"] == true { "verified" } else { "unverified" };
            lines.push(record(&["destination", &text(&d["email"]), state]));
        }
        for r in &rules {
            lines.push(record(&[
                "rule",
                &matched(r),
                &describe_targets(&r["actions"], false),
                on_off(r["enabled"] == true),
            ]));
        }
        return lines.join("\n");
    }
    let zone_level = match zone_status.as_str() {
        "active" => Level::Ok,
        "pending" | "initializing" => Level::Warn,
        _ => Level::Bad,
    };
    let overview = table(&[
        vec![
            cell(Role::Title, "zone"),
            mark(mode, zone_level, &clean(&zone_status, false)),
            cell(Role::Dim, &text(&data["zone"]["id"])),
        ],
        vec![
            cell(Role::Title, "routing"),
            mark(mode, if enabled { Level::Ok } else { Level::Bad }, on_off(enabled)),
            cell(Role::Dim, &routing),
        ],
    ]);
    let mut dest_rows = Vec::new();
    for d in &destinations {
        let verified = d["verified"] == true;
        dest_rows.push(vec![
            cell(Role::Text, &text(&d["email"])),
            mark(
                mode,
                if verified { Level::Ok } else { Level::Warn },
                if verified { "verified" } else { "unverified" },
            ),
        ]);
    }
    let mut dest = vec![vec![span(Role::Title, "destinations")]];
    dest.extend(if dest_rows.is_empty() { vec![cell(Role::Dim, "none")] } else { table(&dest_rows) });
    let mut rule_rows = Vec::new();
    for r in &rules {
        let on = r["enabled"] == true;
        rule_rows.push(vec![
            cell(Role::Text, &matched(r)),
            cell(Role::Dim, mode.g().arrow),
            cell(Role::Text, &describe_targets(&r["actions"], false)),
            mark(mode, if on { Level::Ok } else { Level::Bad }, on_off(on)),
        ]);
    }
    let mut rule_lines = vec![vec![span(Role::Title, "rules")]];
    rule_lines.extend(if rule_rows.is_empty() { vec![cell(Role::Dim, "none")] } else { table(&rule_rows) });
    let footer = format!("{} destinations{}{} rules", destinations.len(), mode.g().sep, rules.len());
    boxed(mode, &clean(&text(&data["zone"]["name"]), false), Some(&footer), &[overview, dest, rule_lines])
}

pub fn list(path: PathBuf, domain: Option<String>) -> Result<()> {
    let overrides = Overrides { domain, ..Overrides::default() };
    let (config, cf) = load(path, &overrides, "a domain (DOMAIN or --domain) and CLOUDFLARE_API_TOKEN are required")?;
    let zone = cf.zone_id_for_domain(&config)?;
    let data = cf.list_data(&zone, config.get("DOMAIN"))?;
    if ui::ctx().json {
        output::print(&envelope("list", data));
    } else {
        output::print(&render_list(&ui::ctx().out, &data));
    }
    Ok(())
}

pub fn render_list(mode: &Mode, data: &Value) -> String {
    let addresses = data["addresses"].as_array().cloned().unwrap_or_default();
    let shown = |a: &Value| match a["address"].as_str() {
        Some(address) => address.to_string(),
        None => format!("custom matcher ({})", text(&a["name"])),
    };
    let on_off = |v: bool| if v { "enabled" } else { "disabled" };
    let catch_all = &data["catch_all"];
    if !mode.styled {
        let mut lines: Vec<String> = addresses
            .iter()
            .map(|a| record(&[&shown(a), &describe_targets(&a["actions"], true), on_off(a["enabled"] == true)]))
            .collect();
        lines.push(if catch_all.is_null() {
            record(&["catch-all", "", "not configured"])
        } else {
            record(&["catch-all", &describe_targets(&catch_all["actions"], true), on_off(catch_all["enabled"] == true)])
        });
        return lines.join("\n");
    }
    let rows: Vec<Vec<Line>> = addresses
        .iter()
        .map(|a| {
            let on = a["enabled"] == true;
            vec![
                cell(Role::Text, &shown(a)),
                cell(Role::Dim, mode.g().arrow),
                cell(Role::Text, &describe_targets(&a["actions"], true)),
                mark(mode, if on { Level::Ok } else { Level::Bad }, on_off(on)),
            ]
        })
        .collect();
    let body = if rows.is_empty() { vec![cell(Role::Dim, "no addresses")] } else { table(&rows) };
    let catch = if catch_all.is_null() {
        vec![vec![span(Role::Title, "catch-all "), span(Role::Dim, "(any other address): not configured")]]
    } else {
        let on = catch_all["enabled"] == true;
        let mut line = vec![span(Role::Title, "catch-all "), span(Role::Dim, format!("{} ", mode.g().arrow))];
        line.push(span(Role::Text, clean(&describe_targets(&catch_all["actions"], true), false)));
        line.push(span(Role::Text, "  "));
        line.extend(mark(mode, if on { Level::Ok } else { Level::Bad }, on_off(on)));
        vec![line]
    };
    let title = format!("{} addresses", clean(&text(&data["domain"]), false));
    let footer = format!("{} addresses", addresses.len());
    boxed(mode, &title, Some(&footer), &[body, catch])
}
