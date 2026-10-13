//! Result rendering on stdout: JSON envelopes, check lists, and plain records.

use crate::style::{self, boxed, clean, span, Level, Line, Mode, Role};
use crate::ui;
use serde_json::{json, Value};

/// `{schema_version:1, command, data}` on one line.
pub fn envelope(command: &str, data: Value) -> String {
    json!({"schema_version": 1, "command": command, "data": data}).to_string()
}

pub fn print(text: &str) {
    print!("{text}");
    if !text.ends_with('\n') {
        println!();
    }
}

/// One tab-separated record with escaped fields.
pub fn record(fields: &[&str]) -> String {
    fields.iter().map(|f| clean(f, true)).collect::<Vec<_>>().join("\t")
}

#[derive(Clone, Debug)]
pub struct Check {
    pub name: String,
    pub state: String,
    pub message: String,
    pub next: String,
}

pub fn check(name: &str, state: &str, message: &str, next: &str) -> Check {
    Check { name: name.into(), state: state.into(), message: message.into(), next: next.into() }
}

pub fn level(state: &str) -> Level {
    match state {
        "pass" | "ready" => Level::Ok,
        "fail" | "blocked" => Level::Bad,
        _ => Level::Warn,
    }
}

pub fn checks_json(checks: &[Check]) -> Value {
    Value::Array(
        checks
            .iter()
            .map(|c| json!({"name": c.name, "state": c.state, "message": c.message, "next": c.next}))
            .collect(),
    )
}

/// Boxed check list for terminals; `name state message next` records otherwise.
pub fn checks_text(mode: &Mode, title: &str, checks: &[Check], footer_extra: Option<String>) -> String {
    if !mode.styled {
        let mut out: String =
            checks.iter().map(|c| record(&[&c.name, &c.state, &c.message, &c.next]) + "\n").collect();
        if let Some(extra) = footer_extra {
            out.push_str(&record(&["elapsed", &extra]));
            out.push('\n');
        }
        return out;
    }
    let mut rows: Vec<Vec<Line>> = Vec::new();
    let mut nexts = Vec::new();
    for c in checks {
        rows.push(vec![
            style::status(mode, level(&c.state), &c.state),
            vec![span(Role::Text, clean(&c.name, false))],
            vec![span(Role::Text, clean(&c.message, false))],
        ]);
        nexts.push(c.next.clone());
    }
    let mut lines = Vec::new();
    for (row, next) in style::table(&rows).into_iter().zip(nexts) {
        lines.push(row);
        if !next.is_empty() {
            lines.push(vec![span(Role::Dim, format!("    next: {}", clean(&next, false)))]);
        }
    }
    let passed = checks.iter().filter(|c| level(&c.state) == Level::Ok).count();
    let mut footer = format!("{} checks · {passed} ok", checks.len());
    if let Some(extra) = footer_extra {
        footer.push_str(&format!(" · {extra}"));
    }
    boxed(mode, title, Some(&footer), &[lines])
}

/// Print checks in the selected format; JSON goes in the command's envelope.
pub fn print_checks(command: &str, title: &str, checks: &[Check]) {
    if ui::ctx().json {
        print(&envelope(command, json!({"checks": checks_json(checks)})));
    } else {
        print(&checks_text(&ui::ctx().out, title, checks, None));
    }
}

pub fn elapsed(seconds: u64) -> String {
    let unit = if seconds == 1 { "second" } else { "seconds" };
    format!("{}m {}s ({seconds} {unit})", seconds / 60, seconds % 60)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn elapsed_format() {
        assert_eq!(elapsed(134), "2m 14s (134 seconds)");
        assert_eq!(elapsed(1), "0m 1s (1 second)");
    }

    #[test]
    fn plain_checks_are_records() {
        let text = checks_text(&Mode::plain(), "t", &[check("config", "pass", "ready\tnow", "")], None);
        assert_eq!(text, "config\tpass\tready\\tnow\t\n");
    }
}
