//! cmail — free custom-domain email with Cloudflare Email Routing.

mod cli;
mod cloudflare;
mod commands;
mod config;
mod error;
mod godaddy;
mod output;
mod style;
mod term;
mod ui;

use std::path::PathBuf;

fn env_value(key: &str) -> Option<String> {
    std::env::var(key).ok()
}

/// First executable named `tool` on PATH (the old `type -P`).
pub fn find_in_path(tool: &str) -> Option<PathBuf> {
    use std::os::unix::fs::PermissionsExt;
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).filter(|dir| !dir.as_os_str().is_empty()).map(|dir| dir.join(tool)).find(|candidate| {
        std::fs::metadata(candidate).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
    })
}

fn run() -> i32 {
    let args: Vec<std::ffi::OsString> = std::env::args_os().collect();
    // --no-color must be known before help is rendered; clap validates it later.
    let no_color = args.iter().skip(1).take_while(|a| *a != "--").any(|a| a == "--no-color");
    let env = style::Env { get: env_value };
    let err_mode = style::Mode::detect(&env, term::fd_is_tty(2), false, no_color, term::fd_columns(2));
    let help_mode = style::Mode::detect(&env, term::fd_is_tty(1), false, no_color, term::fd_columns(1));
    let invocation = match cli::parse(args, &help_mode) {
        cli::Parsed::Run(invocation) => invocation,
        cli::Parsed::Done(code, error) => {
            if let Some((message, command)) = error {
                ui::init(ui::Ctx { command, err: err_mode, ..default_ctx() });
                return ui::report(&error::Error::Usage(message));
            }
            return code;
        }
    };
    let wait_timeout = match &invocation.cli.command {
        Some(cli::Command::Setup(setup)) => setup.wait_timeout,
        _ => 1200,
    };
    ui::init(ui::Ctx {
        json: invocation.json,
        timeout: invocation.timeout,
        wait_timeout,
        verbose: invocation.verbose,
        quiet: invocation.quiet,
        no_browser: invocation.cli.global.no_browser,
        command: invocation.command_path.clone(),
        err: err_mode,
        out: style::Mode::detect(&env, term::fd_is_tty(1), invocation.json, no_color, term::fd_columns(1)),
    });
    term::install_signal_handlers();
    match commands::dispatch(&invocation) {
        Ok(()) => 0,
        Err(error) => ui::report(&error),
    }
}

fn default_ctx() -> ui::Ctx {
    ui::Ctx {
        json: false,
        timeout: 30,
        wait_timeout: 1200,
        verbose: false,
        quiet: false,
        no_browser: false,
        command: String::new(),
        err: style::Mode::plain(),
        out: style::Mode::plain(),
    }
}

fn main() {
    let code = run();
    use std::io::Write;
    let _ = std::io::stdout().flush();
    std::process::exit(code);
}
