//! btop-inspired styling: decisions per stream, theme roles, and components.
//!
//! Commands name a [`Role`]; only this module knows escape codes. Every render
//! function takes an explicit [`Mode`] so tests can render each path without a
//! terminal.

use unicode_width::{UnicodeWidthChar, UnicodeWidthStr};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tier {
    None,
    C16,
    C256,
    True,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Glyphs {
    Unicode,
    Ascii,
}

/// Styled streams get frames and (tier permitting) color; plain streams get
/// tab-separated records without escape codes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Mode {
    pub styled: bool,
    pub tier: Tier,
    pub glyphs: Glyphs,
    pub width: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Text,
    Title,
    Accent,
    Dim,
    Border,
    Low,
    Mid,
    High,
}

/// Inputs to the per-stream decision, gathered from the process environment.
pub struct Env {
    pub get: fn(&str) -> Option<String>,
}

fn set(env: &Env, key: &str) -> Option<String> {
    (env.get)(key).filter(|value| !value.is_empty())
}

impl Mode {
    pub fn plain() -> Mode {
        Mode { styled: false, tier: Tier::None, glyphs: Glyphs::Ascii, width: 80 }
    }

    /// Section 2 of the style guide: styled or plain, color tier, glyph set.
    pub fn detect(env: &Env, is_tty: bool, machine: bool, no_color: bool, columns: Option<usize>) -> Mode {
        let force = set(env, "FORCE_COLOR").is_some_and(|value| value != "0");
        let term = (env.get)("TERM").unwrap_or_default();
        let styled = !machine && term != "dumb" && (is_tty || force);
        let tier = if no_color || set(env, "NO_COLOR").is_some() {
            Tier::None
        } else if matches!(set(env, "COLORTERM").as_deref(), Some("truecolor" | "24bit")) {
            Tier::True
        } else if term.contains("256color") {
            Tier::C256
        } else {
            Tier::C16
        };
        let locale = ["LC_ALL", "LC_CTYPE", "LANG"].iter().find_map(|key| set(env, key)).unwrap_or_default();
        let lower = locale.to_ascii_lowercase();
        let glyphs = if lower.contains("utf-8") || lower.contains("utf8") { Glyphs::Unicode } else { Glyphs::Ascii };
        let width = set(env, "COLUMNS").and_then(|value| value.parse().ok()).or(columns).unwrap_or(80).max(20);
        Mode { styled, tier, glyphs, width }
    }

    fn colored(&self) -> bool {
        self.styled && self.tier != Tier::None
    }

    pub fn sgr(&self, role: Role) -> String {
        if !self.colored() {
            return String::new();
        }
        let color = |rgb: (u8, u8, u8), basic: u8| -> String {
            match self.tier {
                Tier::True => format!("38;2;{};{};{}", rgb.0, rgb.1, rgb.2),
                Tier::C256 => format!("38;5;{}", to_256(rgb)),
                _ => basic.to_string(),
            }
        };
        let code = match role {
            Role::Text => return String::new(),
            Role::Title => "1".to_string(),
            Role::Accent => format!("{};1", color((0xb5, 0x40, 0x40), 91)),
            Role::Dim => "2".to_string(),
            Role::Border => color((0x55, 0x6d, 0x59), 32),
            Role::Low => color((0x77, 0xca, 0x9b), 92),
            Role::Mid => color((0xcb, 0xc0, 0x6c), 93),
            Role::High => color((0xdc, 0x4c, 0x4c), 91),
        };
        format!("\x1b[{code}m")
    }

    pub fn paint(&self, role: Role, text: &str) -> String {
        let start = self.sgr(role);
        if start.is_empty() {
            text.to_string()
        } else {
            format!("{start}{text}\x1b[0m")
        }
    }

    pub fn g(&self) -> &'static G {
        match self.glyphs {
            Glyphs::Unicode => &UNICODE,
            Glyphs::Ascii => &ASCII,
        }
    }
}

/// btop's 24-bit to 256-color conversion (rounding half up).
pub fn to_256((r, g, b): (u8, u8, u8)) -> u8 {
    let round = |value: u8, step: f64| ((value as f64) / step + 0.5).floor() as u8;
    let (gr, gg, gb) = (round(r, 11.0), round(g, 11.0), round(b, 11.0));
    if gr == gg && gg == gb {
        232u8.saturating_add(gr)
    } else {
        16 + 36 * round(r, 51.0) + 6 * round(g, 51.0) + round(b, 51.0)
    }
}

pub struct G {
    pub tl: &'static str,
    pub tr: &'static str,
    pub bl: &'static str,
    pub br: &'static str,
    pub h: &'static str,
    pub v: &'static str,
    pub open: &'static str,
    pub close: &'static str,
    pub foot_open: &'static str,
    pub foot_close: &'static str,
    pub tee_l: &'static str,
    pub tee_r: &'static str,
    pub ok: &'static str,
    pub warn: &'static str,
    pub bad: &'static str,
    pub arrow: &'static str,
    pub ellipsis: &'static str,
    pub rule: &'static str,
    pub meter_full: &'static str,
    pub meter_empty: &'static str,
}

pub static UNICODE: G = G {
    tl: "╭",
    tr: "╮",
    bl: "╰",
    br: "╯",
    h: "─",
    v: "│",
    open: "┐",
    close: "┌",
    foot_open: "┘",
    foot_close: "└",
    tee_l: "├",
    tee_r: "┤",
    ok: "●",
    warn: "▲",
    bad: "✗",
    arrow: "→",
    ellipsis: "…",
    rule: "──",
    meter_full: "■",
    meter_empty: "■",
};

pub static ASCII: G = G {
    tl: "+",
    tr: "+",
    bl: "+",
    br: "+",
    h: "-",
    v: "|",
    open: "[",
    close: "]",
    foot_open: "[",
    foot_close: "]",
    tee_l: "+",
    tee_r: "+",
    ok: "+",
    warn: "!",
    bad: "x",
    arrow: "->",
    ellipsis: "...",
    rule: "--",
    meter_full: "#",
    meter_empty: ".",
};

/// Make user-supplied text safe to print: controls become visible escapes.
/// Plain output also escapes backslashes so each record stays one line.
pub fn clean(text: &str, plain: bool) -> String {
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        match ch {
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\\' if plain => out.push_str("\\\\"),
            c if (c as u32) < 0x20 || (0x7f..=0x9f).contains(&(c as u32)) => {
                out.push_str(&format!("\\x{:02x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out
}

/// Terminal cells taken by `text` (CJK and emoji count two).
pub fn width(text: &str) -> usize {
    UnicodeWidthStr::width(text)
}

fn truncate(text: &str, max: usize, ellipsis: &str) -> String {
    if width(text) <= max {
        return text.to_string();
    }
    let room = max.saturating_sub(width(ellipsis));
    let mut out = String::new();
    let mut used = 0;
    for ch in text.chars() {
        let w = UnicodeWidthChar::width(ch).unwrap_or(0);
        if used + w > room {
            break;
        }
        used += w;
        out.push(ch);
    }
    out.push_str(ellipsis);
    out
}

/// A run of text drawn in one role.
#[derive(Clone, Debug)]
pub struct Span {
    pub role: Role,
    pub text: String,
}

pub fn span(role: Role, text: impl Into<String>) -> Span {
    Span { role, text: text.into() }
}

pub type Line = Vec<Span>;

fn line_width(line: &Line) -> usize {
    line.iter().map(|s| width(&s.text)).sum()
}

fn render_line(mode: &Mode, line: &Line, max: usize) -> (String, usize) {
    let mut out = String::new();
    let mut used = 0;
    for part in line {
        let room = max.saturating_sub(used);
        if room == 0 {
            break;
        }
        let text = if width(&part.text) > room { truncate(&part.text, room, mode.g().ellipsis) } else { part.text.clone() };
        used += width(&text);
        out.push_str(&mode.paint(part.role, &text));
    }
    (out, used)
}

/// Pad cells of each column to a common width (two spaces between columns).
pub fn table(rows: &[Vec<Line>]) -> Vec<Line> {
    let columns = rows.iter().map(Vec::len).max().unwrap_or(0);
    let widths: Vec<usize> =
        (0..columns).map(|c| rows.iter().filter_map(|r| r.get(c)).map(line_width).max().unwrap_or(0)).collect();
    rows.iter()
        .map(|row| {
            let mut line = Line::new();
            for (c, cell) in row.iter().enumerate() {
                line.extend(cell.iter().cloned());
                if c + 1 < row.len() {
                    line.push(span(Role::Text, " ".repeat(widths[c] - line_width(cell) + 2)));
                }
            }
            line
        })
        .collect()
}

/// Status mark and word: ok (low), warn (mid), bad (high). The word carries the meaning.
pub fn status(mode: &Mode, level: Level, word: &str) -> Line {
    let g = mode.g();
    let (role, mark) = match level {
        Level::Ok => (Role::Low, g.ok),
        Level::Warn => (Role::Mid, g.warn),
        Level::Bad => (Role::High, g.bad),
    };
    vec![span(role, mark), span(Role::Text, format!(" {word}"))]
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Level {
    Ok,
    Warn,
    Bad,
}

/// A box with the title set into the top border and an optional footer, its
/// sections divided by `├───┤`, sized to the content within the terminal width.
pub fn boxed(mode: &Mode, title: &str, footer: Option<&str>, sections: &[Vec<Line>]) -> String {
    let g = mode.g();
    let content = sections.iter().flatten().map(line_width).max().unwrap_or(0);
    let title_w = width(title);
    let footer_w = footer.map(width).unwrap_or(0);
    let mut total = (content + 4).max(title_w + 6).max(footer_w + 6);
    total = total.min(mode.width.max(12));
    let inner = total - 4;
    let border = |s: &str| mode.paint(Role::Border, s);
    let notch_line = |left: &str, open: &str, text: &str, close: &str, right: &str| {
        let text = truncate(text, total - 6, g.ellipsis);
        let fill = total - 5 - width(&text);
        format!(
            "{}{}{}{}\n",
            border(&format!("{left}{}{open}", g.h)),
            mode.paint(Role::Title, &text),
            border(&format!("{close}{}", g.h.repeat(fill))),
            border(right)
        )
    };
    let mut out = notch_line(g.tl, g.open, title, g.close, g.tr);
    for (i, section) in sections.iter().enumerate() {
        if i > 0 {
            out.push_str(&border(&format!("{}{}{}", g.tee_l, g.h.repeat(total - 2), g.tee_r)));
            out.push('\n');
        }
        for line in section {
            let (text, used) = render_line(mode, line, inner);
            out.push_str(&format!("{} {}{} {}\n", border(g.v), text, " ".repeat(inner - used), border(g.v)));
        }
    }
    match footer {
        Some(text) => out.push_str(&notch_line(g.bl, g.foot_open, text, g.foot_close, g.br)),
        None => {
            out.push_str(&border(&format!("{}{}{}", g.bl, g.h.repeat(total - 2), g.br)));
            out.push('\n');
        }
    }
    out
}

/// Meter of `cells` cells for a 0-100 value, then the right-aligned value.
pub fn meter(mode: &Mode, value: u32, cells: u32) -> String {
    let g = mode.g();
    let mut out = String::new();
    for i in 1..=cells {
        let threshold = ((i as f64) * 100.0 / cells as f64 + 0.5).floor() as u32;
        if value >= threshold {
            let position = i * 100 / cells;
            let role = if position <= 33 {
                Role::Low
            } else if position <= 66 {
                Role::Mid
            } else {
                Role::High
            };
            out.push_str(&mode.paint(role, g.meter_full));
        } else if mode.colored() {
            out.push_str(&mode.paint(Role::Dim, g.meter_empty));
        } else if mode.glyphs == Glyphs::Unicode {
            out.push('·');
        } else {
            out.push_str(g.meter_empty);
        }
    }
    format!("{out} {value:>3}%")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mode(tier: Tier, glyphs: Glyphs) -> Mode {
        Mode { styled: true, tier, glyphs, width: 60 }
    }

    fn env_none(_: &str) -> Option<String> {
        None
    }

    #[test]
    fn styled_16_color_unicode_box_has_escape_and_notch() {
        let out = boxed(&mode(Tier::C16, Glyphs::Unicode), "status", None, &[vec![vec![span(Role::Text, "hello")]]]);
        assert!(out.contains("\x1b["));
        assert!(out.contains("╭─┐"));
    }

    #[test]
    fn ascii_glyphs_are_ascii_only() {
        let m = mode(Tier::C16, Glyphs::Ascii);
        let mut out = boxed(&m, "status", Some("2 rules"), &[vec![status(&m, Level::Bad, "down")], vec![]]);
        out.push_str(&meter(&m, 40, 10));
        assert!(out.chars().all(|c| (c as u32) < 0x80), "{out}");
    }

    #[test]
    fn meter_half_without_color() {
        let m = mode(Tier::None, Glyphs::Unicode);
        assert_eq!(meter(&m, 50, 10), "■■■■■·····  50%");
    }

    #[test]
    fn hostile_text_never_prints_raw_escape() {
        let hostile = "evil\x1b[31m\tname";
        let plain = clean(hostile, true);
        assert!(!plain.contains('\x1b'));
        assert_eq!(format!("a\t{plain}\tc").split('\t').count(), 3);
        let m = mode(Tier::None, Glyphs::Unicode);
        let styled = boxed(&m, &clean(hostile, false), None, &[vec![vec![span(Role::Text, clean(hostile, false))]]]);
        assert!(!styled.contains('\x1b'));
    }

    #[test]
    fn tier_none_has_no_escapes_but_keeps_frames() {
        let m = mode(Tier::None, Glyphs::Unicode);
        let out = boxed(&m, "t", None, &[vec![status(&m, Level::Ok, "ok")]]);
        assert!(!out.contains('\x1b'));
        assert!(out.contains('╭'));
    }

    #[test]
    fn detection_rules() {
        let plain = Mode::detect(&Env { get: env_none }, false, false, false, None);
        assert!(!plain.styled);
        fn forced(key: &str) -> Option<String> {
            match key {
                "FORCE_COLOR" => Some("1".into()),
                "TERM" => Some("xterm-256color".into()),
                "LANG" => Some("C.UTF-8".into()),
                _ => None,
            }
        }
        let m = Mode::detect(&Env { get: forced }, false, false, false, None);
        assert!(m.styled);
        assert_eq!(m.tier, Tier::C256);
        assert_eq!(m.glyphs, Glyphs::Unicode);
        assert!(!Mode::detect(&Env { get: forced }, true, true, false, None).styled, "JSON stdout is always plain");
        assert_eq!(Mode::detect(&Env { get: forced }, true, false, true, None).tier, Tier::None);
        fn dumb(key: &str) -> Option<String> {
            (key == "TERM").then(|| "dumb".into())
        }
        assert!(!Mode::detect(&Env { get: dumb }, true, false, false, None).styled);
    }

    #[test]
    fn btop_256_conversion() {
        assert_eq!(to_256((0x55, 0x6d, 0x59)), 16 + 36 * 2 + 6 * 2 + 2);
        assert_eq!(to_256((0x30, 0x30, 0x30)), 232 + 4);
    }

    #[test]
    fn wide_text_is_measured_in_cells() {
        let m = mode(Tier::None, Glyphs::Unicode);
        let out = boxed(&m, "t", None, &[vec![vec![span(Role::Text, "日本")]]]);
        let widths: Vec<usize> = out.lines().map(width).collect();
        assert!(widths.windows(2).all(|w| w[0] == w[1]), "{out}");
    }
}
