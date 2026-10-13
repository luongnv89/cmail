//! `cmail config init|show|check|set|path`.

use crate::cli::ConfigCommand;
use crate::config::{self, Config, Overrides, KEYS};
use crate::error::{config_error, usage, Error, Result};
use crate::output::{self, check, envelope, record};
use crate::style::{boxed, clean, span, table, Line, Role};
use crate::{term, ui};
use serde_json::{Map, Value};
use std::path::PathBuf;

pub fn run(command: &ConfigCommand, path: PathBuf) -> Result<()> {
    match command {
        ConfigCommand::Init => {
            output::print(&config::init(&path)?);
            Ok(())
        }
        ConfigCommand::Show => show(path),
        ConfigCommand::Check => check_ready(path),
        ConfigCommand::Set { key, value, stdin } => set(path, key, value.as_deref(), *stdin),
        ConfigCommand::Path => {
            output::print(&path.display().to_string());
            Ok(())
        }
    }
}

fn show(path: PathBuf) -> Result<()> {
    let config = Config::load(path, &Overrides::default())?;
    let c = ui::ctx();
    let mut settings = Map::new();
    let mut secrets = Map::new();
    let mut rows: Vec<Vec<Line>> = Vec::new();
    let mut plain = vec![record(&["path", &config.path.display().to_string()])];
    for key in KEYS {
        let (value, secret) = if config::is_secret(key) {
            let state = if config.get(key).is_empty() { "empty" } else { "set" };
            secrets.insert(key.into(), Value::from(state));
            (state.to_string(), true)
        } else {
            let value = config::public_value(&config, key);
            settings.insert(key.into(), Value::from(value.clone()));
            (value, false)
        };
        plain.push(record(&[key, &value]));
        let role = if secret { Role::Dim } else { Role::Text };
        let shown = if value.is_empty() { "—".to_string() } else { clean(&value, false) };
        rows.push(vec![vec![span(Role::Title, key)], vec![span(role, shown)]]);
    }
    if c.json {
        let data = serde_json::json!({"path": config.path.display().to_string(), "settings": settings, "secrets": secrets});
        output::print(&envelope("config show", data));
    } else if c.out.styled {
        let footer = clean(&config.path.display().to_string(), false);
        output::print(&boxed(&c.out, "cmail config", Some(&footer), &[table(&rows)]));
    } else {
        output::print(&plain.join("\n"));
    }
    Ok(())
}

fn check_ready(path: PathBuf) -> Result<()> {
    let ready = Config::load(path, &Overrides::default()).and_then(|config| config.ready());
    let checks = match &ready {
        Ok(()) => vec![check("config", "pass", "configuration ready", "Use cmail setup --dry-run to inspect provider state.")],
        Err(error) => {
            if let Error::Config(message) = error {
                ui::print_config_error(message);
            }
            vec![check(
                "config",
                "fail",
                "configuration invalid or incomplete",
                "Correct the fields reported on stderr, then rerun cmail config check.",
            )]
        }
    };
    output::print_checks("config check", "cmail config check", &checks);
    ready.map_err(|_| Error::Exit(3))
}

fn set(path: PathBuf, key: &str, value: Option<&str>, stdin: bool) -> Result<()> {
    if config::is_secret(key) && !stdin {
        return usage("secret settings require --stdin; pipe from a private source, never pass a token as an argument");
    }
    let value = if stdin {
        if term::stdin_is_tty() {
            return usage("--stdin needs piped input or a private file; use setup for hidden terminal token entry");
        }
        // EOF, NUL, or the size cap ends the read; only one trailing LF is allowed.
        let mut bytes = term::read_stdin_bytes(4098);
        if bytes.contains(&0) || bytes.len() >= 4098 {
            return config_error("stdin must contain one value, without NUL, at most 4096 bytes");
        }
        if bytes.last() == Some(&b'\n') {
            bytes.pop();
        }
        match String::from_utf8(bytes) {
            Ok(value) => value,
            Err(_) => return config_error(format!("{key} has invalid input")),
        }
    } else {
        value.unwrap_or_default().to_string()
    };
    if value.len() > 4096 {
        return config_error("value exceeds 4096 bytes");
    }
    if !value.is_empty() && !config::field_valid(key, &value) {
        return config_error(format!("{key} has invalid input"));
    }
    // Compare a new DOMAIN with the saved one, so the saved zone ID is dropped only on change.
    let mut config = Config::read(path, &Overrides::default())?;
    if let Ok(saved) = config::read_file(&config.path) {
        let domain = saved.iter().find(|(k, _)| k == "DOMAIN").map(|(_, v)| v.clone()).unwrap_or_default();
        config.put("DOMAIN", &domain);
    }
    config.set(key, &value)?;
    output::print(&format!("Updated {key} (value hidden)."));
    Ok(())
}
