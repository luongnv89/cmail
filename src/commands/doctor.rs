//! `cmail doctor`: read-only configuration, tool, and authentication checks.

use crate::cloudflare::Cf;
use crate::config::{Config, Overrides};
use crate::error::{Error, Result};
use crate::godaddy;
use crate::output::{check, print_checks, Check};
use crate::{find_in_path, ui};
use std::path::PathBuf;

pub fn doctor(path: PathBuf, offline: bool) -> Result<()> {
    let mut checks: Vec<Check> = Vec::new();
    let mut invalid = false;
    let mut failed = false;
    let env_registrar = std::env::var("REGISTRAR").ok().filter(|r| !r.is_empty()).unwrap_or_else(|| "manual".into());
    let mut config: Option<Config> = None;
    let mut registrar = env_registrar.clone();
    if std::fs::symlink_metadata(&path).is_err() {
        checks.push(check("config", "fail", "configuration missing", "Run cmail config init."));
        invalid = true;
    } else {
        match Config::read(path, &Overrides::default()) {
            Ok(loaded) => {
                registrar = loaded.registrar().to_string();
                match loaded.ready() {
                    Ok(()) => {
                        checks.push(check("config", "pass", "configuration ready", ""));
                        config = Some(loaded);
                    }
                    Err(error) => {
                        report(&error);
                        checks.push(check("config", "fail", "configuration incomplete", "Run cmail config check."));
                        invalid = true;
                    }
                }
            }
            Err(error) => {
                report(&error);
                checks.push(check("config", "fail", "configuration incomplete", "Run cmail config check."));
                invalid = true;
            }
        }
    }
    // gddy is required only for opt-in GoDaddy automation (REGISTRAR=godaddy).
    if registrar == "godaddy" {
        if find_in_path("gddy").is_some() {
            checks.push(check("gddy", "pass", "gddy available", ""));
        } else {
            checks.push(check(
                "gddy",
                "fail",
                "gddy missing",
                "Install gddy and check PATH, or set REGISTRAR=manual to update nameservers at your registrar yourself.",
            ));
            failed = true;
        }
    } else if !invalid {
        checks.push(check("registrar", "pass", "manual registrar mode; gddy not required", ""));
    }
    if let (false, false, false, Some(config)) = (offline, invalid, failed, &config) {
        if Cf::new(config)?.token_valid() {
            checks.push(check("cloudflare", "pass", "Cloudflare token active", ""));
        } else {
            checks.push(check(
                "cloudflare",
                "fail",
                "Cloudflare token check failed",
                "Check token activity and connectivity.",
            ));
            failed = true;
        }
        if registrar == "godaddy" {
            if !config.get("GDDY_PAT").is_empty() {
                checks.push(check(
                    "godaddy",
                    "skipped",
                    "GoDaddy PAT present; provider access not verified",
                    "Use setup --dry-run to check domain access.",
                ));
            } else if godaddy::auth_available(config) {
                checks.push(check("godaddy", "pass", "GoDaddy authentication available", ""));
            } else {
                checks.push(check(
                    "godaddy",
                    "fail",
                    "GoDaddy authentication unavailable",
                    "Run gddy auth login for the selected environment.",
                ));
                failed = true;
            }
        }
    }
    print_checks("doctor", "cmail doctor", &checks);
    if invalid {
        Err(Error::Exit(3))
    } else if failed {
        Err(Error::Exit(1))
    } else {
        Ok(())
    }
}

fn report(error: &Error) {
    if let Error::Config(message) = error {
        ui::print_config_error(message);
    }
}
