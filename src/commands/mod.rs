//! One module per command; `dispatch` routes the parsed invocation.

mod config_cmd;

use crate::cli::{Command, Invocation};
use crate::config::{self, Overrides};
use crate::error::{die, Result};
use std::path::PathBuf;

pub fn config_path(invocation: &Invocation) -> PathBuf {
    config::resolve_path(invocation.cli.global.config.as_deref())
}

pub fn dispatch(invocation: &Invocation) -> Result<()> {
    let path = config_path(invocation);
    let Some(command) = &invocation.cli.command else { return Ok(()) };
    match command {
        Command::Config { command: Some(sub) } => config_cmd::run(sub, path),
        Command::Completion { .. } | Command::Config { command: None } => Ok(()),
        _ => {
            let _ = Overrides::default();
            die("this command is not available yet")
        }
    }
}
