//! Process-wide options and stderr diagnostics: progress, prompts, errors.
//!
//! Results go to stdout through `output`; everything here writes to stderr so
//! stdout stays pipeable.

use crate::error::Error;
use crate::style::{Mode, Role};
use crate::term;
use std::sync::{Mutex, OnceLock};

#[derive(Debug)]
pub struct Ctx {
    pub json: bool,
    pub timeout: u32,
    pub wait_timeout: u64,
    pub verbose: bool,
    pub quiet: bool,
    pub no_browser: bool,
    /// `cmail config set`, for usage hints.
    pub command: String,
    /// stderr and stdout are decided separately: stdout may be piped while stderr is a terminal.
    pub err: Mode,
    pub out: Mode,
}

static CTX: OnceLock<Ctx> = OnceLock::new();
static STEP: Mutex<String> = Mutex::new(String::new());

pub fn init(ctx: Ctx) {
    let _ = CTX.set(ctx);
}

pub fn ctx() -> &'static Ctx {
    CTX.get_or_init(|| Ctx {
        json: false,
        timeout: 30,
        wait_timeout: 1200,
        verbose: false,
        quiet: false,
        no_browser: false,
        command: String::new(),
        err: Mode::plain(),
        out: Mode::plain(),
    })
}

fn emit(text: &str) {
    eprintln!("{text}");
}

fn mark(role: Role, glyph: &str) -> String {
    ctx().err.paint(role, glyph)
}

/// Routine progress (suppressed by --quiet).
pub fn log(message: &str) {
    if !ctx().quiet {
        emit(&format!("{} {message}", mark(Role::Border, "==>")));
    }
}

pub fn ok(message: &str) {
    if !ctx().quiet {
        emit(&format!(" {} {message}", mark(Role::Low, ctx().err.g().ok)));
    }
}

/// Warnings always print: they ask the user to act or explain a risk.
pub fn warn(message: &str) {
    emit(&format!(" {} {message}", mark(Role::Mid, ctx().err.g().warn)));
}

pub fn note(message: &str) {
    if !ctx().quiet {
        emit(&ctx().err.paint(Role::Dim, &format!("    {message}")));
    }
}

/// Start a named workflow step; setup recovery reports the step it stopped at.
pub fn step(title: &str) {
    *STEP.lock().unwrap() = title.to_string();
    if !ctx().quiet {
        let rule = ctx().err.g().rule;
        emit(&format!("\n{}", ctx().err.paint(Role::Border, &format!("{rule} {title} {rule}"))));
    }
}

/// Record the step for recovery guidance without printing a header.
pub fn step_silently(title: &str) {
    *STEP.lock().unwrap() = title.to_string();
}

pub fn current_step() -> String {
    let step = STEP.lock().unwrap().clone();
    if step.is_empty() {
        "startup".into()
    } else {
        step
    }
}

/// Text printed even with --quiet (instructions the user must act on).
pub fn always(text: &str) {
    eprint!("{text}");
}

pub fn verbose(message: &str) {
    if ctx().verbose {
        emit(message);
    }
}

fn question(text: &str) {
    eprint!("{} {text}", mark(Role::Mid, " ?"));
}

/// `[y/N]` question on the terminal; anything but y/yes declines.
pub fn confirm(text: &str) -> bool {
    question(&format!("{text} [y/N] "));
    matches!(term::read_line().map(|a| a.to_ascii_lowercase()).as_deref(), Some("y" | "yes"))
}

/// Typed approval for any charge: no flag or environment variable skips it.
pub fn confirm_payment(text: &str, phrase: &str) -> bool {
    if !term::stdin_is_tty() {
        warn("payment approval must be typed at an interactive terminal — nothing was charged");
        return false;
    }
    question(&format!("{text}\n    Type {phrase} to approve this charge (anything else cancels): "));
    term::read_line().as_deref() == Some(phrase)
}

/// Ask for one value; `None` when input ends.
pub fn ask(text: &str, secret: bool) -> Option<String> {
    question(&format!("{text}: "));
    if secret {
        let value = term::read_secret();
        eprintln!();
        value
    } else {
        term::read_line()
    }
}

pub fn pause() -> bool {
    eprint!("{} ", ctx().err.paint(Role::Dim, "… press Enter to continue"));
    term::read_line().is_some()
}

/// Best-effort browser open; the URL is always printed for manual opening.
pub fn open_url(url: &str) {
    eprintln!("Open: {url}");
    if ctx().no_browser {
        return;
    }
    let quiet = |mut command: std::process::Command| {
        let _ = command
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();
    };
    if let Some(browser) = std::env::var_os("BROWSER").filter(|b| !b.is_empty()) {
        let mut command = std::process::Command::new(browser);
        command.arg(url);
        quiet(command);
        return;
    }
    let opener = if cfg!(target_os = "macos") {
        Some("open")
    } else {
        ["xdg-open", "wslview"].into_iter().find(|tool| crate::find_in_path(tool).is_some())
    };
    if let Some(opener) = opener {
        let mut command = std::process::Command::new(opener);
        command.arg(url);
        quiet(command);
        term::sleep(1);
    }
}

/// Print a failure on stderr and return its exit code.
pub fn report(error: &Error) -> i32 {
    let c = ctx();
    let bad = c.err.paint(Role::High, &format!("{} ", c.err.g().bad));
    let strong = |text: &str| c.err.paint(Role::High, &c.err.paint(Role::Title, text));
    let hint = |text: &str| emit(&c.err.paint(Role::Dim, &format!("hint: {text}")));
    match error {
        Error::Usage(message) => {
            emit(&format!("{bad}{} {message}", strong("cmail:")));
            let command = if c.command.is_empty() { String::new() } else { format!("{} ", c.command) };
            hint(&format!("cmail {command}--help"));
        }
        Error::Config(message) => print_config_error(message),
        Error::Fail(message) => emit(&format!("{bad}{} {message}", strong("error:"))),
        Error::Exit(_) => {}
    }
    error.code()
}

/// Configuration problems: printed where the old `config_error` printed them.
pub fn print_config_error(message: &str) {
    let c = ctx();
    let bad = c.err.paint(Role::High, &format!("{} ", c.err.g().bad));
    emit(&format!("{bad}{} {message}", c.err.paint(Role::Title, "cmail:")));
    emit(&c.err.paint(Role::Dim, "hint: correct the private config locally (cmail config --help)"));
}
