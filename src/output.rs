//! Result rendering on stdout: JSON envelopes, check lists, and plain records.

use crate::style::{self, boxed, clean, span, Level, Mode, Role};
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
        let mut out: String = checks.iter().map(|c| record(&[&c.name, &c.state, &c.message, &c.next]) + "\n").collect();
        if let Some(extra) = footer_extra {
            out.push_str(&record(&["elapsed", &extra]));
            out.push('\n');
        }
        return out;
    }
    // Guidance is what the user acts on, so long messages wrap instead of being cut.
    let state_w = checks.iter().map(|c| style::width(&c.state)).max().unwrap_or(0) + 2;
    let name_w = checks.iter().map(|c| style::width(&clean(&c.name, false))).max().unwrap_or(0);
    let indent = state_w + 2 + name_w + 2;
    let room = mode.width.saturating_sub(4 + indent).max(20);
    let mut lines = Vec::new();
    for c in checks {
        let mut first = style::status(mode, level(&c.state), &c.state);
        first.push(span(Role::Text, " ".repeat(state_w - style::width(&c.state) - 2 + 2)));
        let name = clean(&c.name, false);
        first.push(span(Role::Text, format!("{name}{}", " ".repeat(name_w - style::width(&name) + 2))));
        let mut message = wrap(&clean(&c.message, false), room).into_iter();
        first.push(span(Role::Text, message.next().unwrap_or_default()));
        lines.push(first);
        for more in message {
            lines.push(vec![span(Role::Text, format!("{}{more}", " ".repeat(indent)))]);
        }
        if !c.next.is_empty() {
            for (i, part) in wrap(&clean(&c.next, false), room).into_iter().enumerate() {
                let label = if i == 0 { "next: " } else { "      " };
                lines.push(vec![span(Role::Dim, format!("{}{label}{part}", " ".repeat(indent.saturating_sub(6))))]);
            }
        }
    }
    let passed = checks.iter().filter(|c| level(&c.state) == Level::Ok).count();
    let sep = mode.g().sep;
    let mut footer = format!("{} checks{sep}{passed} ok", checks.len());
    if let Some(extra) = footer_extra {
        footer.push_str(&format!("{sep}{extra}"));
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

/// Greedy word wrap to `width` terminal cells; words longer than a line stay whole.
pub fn wrap(text: &str, width: usize) -> Vec<String> {
    let mut lines = Vec::new();
    let mut line = String::new();
    for word in text.split(' ') {
        if !line.is_empty() && style::width(&line) + 1 + style::width(word) > width {
            lines.push(std::mem::take(&mut line));
        }
        if !line.is_empty() {
            line.push(' ');
        }
        line.push_str(word);
    }
    lines.push(line);
    lines
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
    fn wrap_keeps_words_whole() {
        assert_eq!(wrap("one two three four", 9), vec!["one two", "three", "four"]);
        assert_eq!(wrap("short", 40), vec!["short"]);
    }

    #[test]
    fn plain_checks_are_records() {
        let text = checks_text(&Mode::plain(), "t", &[check("config", "pass", "ready\tnow", "")], None);
        assert_eq!(text, "config\tpass\tready\\tnow\t\n");
    }
}
