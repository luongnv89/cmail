//! One module per command; `dispatch` routes the parsed invocation.

mod config_cmd;
mod doctor;
mod forward;
mod setup;
mod status;

use crate::cli::{self, Command, Invocation, Shell};
use crate::config;
use crate::error::Result;

pub fn dispatch(invocation: &Invocation) -> Result<()> {
    let path = config::resolve_path(invocation.cli.global.config.as_deref());
    let Some(command) = &invocation.cli.command else { return Ok(()) };
    match command {
        Command::Setup(args) => setup::setup(path, args),
        Command::Status => status::status(path),
        Command::List { domain } => status::list(path, domain.clone()),
        Command::Forward(args) => forward::forward(path, args),
        Command::Doctor { offline } => doctor::doctor(path, *offline),
        Command::SendAs => setup::send_as(path),
        Command::Config { command: Some(sub) } => config_cmd::run(sub, path),
        Command::Config { command: None } => Ok(()),
        Command::Completion { shell } => {
            completion(*shell);
            Ok(())
        }
    }
}

/// Completion scripts are generated from the command tree, so they never drift.
fn completion(shell: Shell) {
    use clap_complete::{generate, shells};
    let mut command = cli::command(&crate::style::Mode::plain());
    let mut out = std::io::stdout();
    match shell {
        Shell::Bash => generate(shells::Bash, &mut command, "cmail", &mut out),
        Shell::Zsh => generate(shells::Zsh, &mut command, "cmail", &mut out),
        Shell::Fish => generate(shells::Fish, &mut command, "cmail", &mut out),
    }
}
