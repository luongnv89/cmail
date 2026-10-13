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
    use std::io::Write;
    let _ = std::io::stdout().write_all(&completion_script(shell));
}

fn completion_script(shell: Shell) -> Vec<u8> {
    use clap_complete::{generate, shells};
    let mut command = cli::command(&crate::style::Mode::plain());
    let mut out = Vec::new();
    match shell {
        Shell::Bash => generate(shells::Bash, &mut command, "cmail", &mut out),
        Shell::Zsh => generate(shells::Zsh, &mut command, "cmail", &mut out),
        Shell::Fish => {
            generate(shells::Fish, &mut command, "cmail", &mut out);
            out.extend_from_slice(fish_config_keys().as_bytes());
        }
    }
    out
}

/// clap_complete's fish generator omits positional values, so offer the
/// `config set` KEY names until one has been given.
fn fish_config_keys() -> String {
    let keys = config::KEYS.join(" ");
    format!(
        "complete -c cmail -n \"__fish_cmail_using_subcommand config; and __fish_seen_subcommand_from set; \
         and not __fish_seen_subcommand_from {keys}\" -f -a \"{keys}\" -d 'Setting to update'\n"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fish_completion_offers_config_set_keys_only_before_a_key() {
        let script = String::from_utf8(completion_script(Shell::Fish)).unwrap();
        let line = script
            .lines()
            .find(|line| line.contains("__fish_seen_subcommand_from set; and not"))
            .expect("config set KEY completion line");
        let keys = config::KEYS.join(" ");
        assert!(line.contains(&format!("not __fish_seen_subcommand_from {keys}\"")), "{line}");
        assert!(line.ends_with(&format!("-f -a \"{keys}\" -d 'Setting to update'")), "{line}");
    }
}
