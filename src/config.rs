//! Literal private configuration. User content is parsed, never evaluated.
//!
//! Precedence: CLI options > environment variables > config file > defaults.
//! The file is `KEY=value` lines with shell-style quoting, mode 600, owned by
//! the user, and never a symlink. Writes replace it by a same-directory rename.

use crate::error::{config_error, die, Result};
use crate::ui;
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

pub const KEYS: [&str; 10] = [
    "DOMAIN",
    "DEST_EMAIL",
    "ADDRESSES",
    "CLOUDFLARE_API_TOKEN",
    "REGISTRAR",
    "GDDY_ENV",
    "GDDY_PAT",
    "CF_ZONE_ID",
    "CF_ACCOUNT_ID",
    "DRY_RUN",
];

pub const TEMPLATE: &str = include_str!("../.env.example");

pub fn key_valid(key: &str) -> bool {
    KEYS.contains(&key)
}

pub fn is_secret(key: &str) -> bool {
    matches!(key, "CLOUDFLARE_API_TOKEN" | "GDDY_PAT")
}

/// `--config` > `CMAIL_CONFIG` > `ENV_FILE` > `${XDG_CONFIG_HOME:-~/.config}/cmail/.env`.
/// Relative paths resolve against the working directory. Empty values count as unset.
pub fn resolve_path(cli: Option<&str>) -> PathBuf {
    let nonempty = |key: &str| std::env::var(key).ok().filter(|v| !v.is_empty());
    let chosen = cli.map(str::to_string).or_else(|| nonempty("CMAIL_CONFIG")).or_else(|| nonempty("ENV_FILE"));
    let path = match chosen {
        Some(path) => PathBuf::from(path),
        None => {
            let base = nonempty("XDG_CONFIG_HOME")
                .map(PathBuf::from)
                .filter(|p| p.is_absolute())
                .unwrap_or_else(|| PathBuf::from(nonempty("HOME").unwrap_or_else(|| "/".into())).join(".config"));
            base.join("cmail").join(".env")
        }
    };
    if path.is_absolute() {
        path
    } else {
        std::env::current_dir().map(|dir| dir.join(&path)).unwrap_or(path)
    }
}

/// Values given on the command line (setup, list, forward).
#[derive(Default, Clone, Debug)]
pub struct Overrides {
    pub domain: Option<String>,
    pub destination: Option<String>,
    pub addresses: Option<String>,
    pub registrar: Option<String>,
}

#[derive(Clone, Debug)]
pub struct Config {
    pub path: PathBuf,
    values: HashMap<&'static str, Option<String>>,
}

fn exists_or_link(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

fn printable(byte: u8) -> bool {
    (0x20..=0x7e).contains(&byte)
}

/// One raw assignment word to its literal value, with shell quoting rules but
/// no expansions, commands, or unquoted shell syntax.
pub fn literal(raw: &[u8], number: usize) -> Result<String> {
    #[derive(PartialEq)]
    enum Quote {
        None,
        Single,
        Double,
    }
    let unsupported = || config_error(format!("line {number}: unsupported character"));
    let mut state = Quote::None;
    let mut out = Vec::new();
    let mut i = 0;
    while i < raw.len() {
        let ch = raw[i];
        i += 1;
        if !(printable(ch) || ch == b'\t') {
            return unsupported();
        }
        if state == Quote::Single {
            if ch == b'\'' {
                state = Quote::None;
            } else {
                out.push(ch);
            }
            continue;
        }
        match ch {
            b'\\' => {
                let Some(&next) = raw.get(i) else {
                    return config_error(format!("line {number}: dangling escape"));
                };
                i += 1;
                if !(printable(next) || next == b'\t') {
                    return unsupported();
                }
                if state == Quote::Double && !matches!(next, b'\\' | b'"' | b'$' | b'`') {
                    out.push(b'\\');
                }
                out.push(next);
            }
            b'"' => state = if state == Quote::Double { Quote::None } else { Quote::Double },
            b'\'' => {
                if state == Quote::Double {
                    out.push(ch);
                } else {
                    state = Quote::Single;
                }
            }
            b'$' | b'`' => {
                return config_error(format!(
                    "line {number}: expansions/commands are not allowed; use literal KEY=value assignments"
                ))
            }
            _ => {
                if state == Quote::None && b" \t;&|<>()~*?[]{}".contains(&ch) {
                    return config_error(format!(
                        "line {number}: quote spaces and remove shell syntax; use literal KEY=value assignments"
                    ));
                }
                out.push(ch);
            }
        }
    }
    if state != Quote::None {
        return config_error(format!("line {number}: invalid quoting; check shell assignment syntax"));
    }
    Ok(String::from_utf8(out).expect("printable ASCII"))
}

/// Check the file is private, then parse every assignment (no evaluation).
pub fn read_file(path: &Path) -> Result<Vec<(String, String)>> {
    let meta = fs::symlink_metadata(path);
    let owned = meta.as_ref().is_ok_and(|m| m.file_type().is_file() && m.uid() == unsafe { libc::geteuid() });
    let bytes = if owned { fs::read(path).ok() } else { None };
    let Some(bytes) = bytes else {
        return config_error("selected config must be a readable user-owned regular file, not a symlink");
    };
    let mode = meta.map(|m| m.mode() & 0o7777).unwrap_or(0);
    if mode != 0o600 {
        return config_error("selected config must have mode 600 (chmod 600 on the selected file)");
    }
    if bytes.len() > 65536 {
        return config_error("selected config exceeds 64 KiB");
    }
    if bytes.contains(&0) {
        return config_error("selected config contains unsupported controls");
    }
    let mut seen = Vec::new();
    let mut assignments = Vec::new();
    let text = bytes.strip_suffix(b"\n").unwrap_or(&bytes);
    if bytes.is_empty() {
        return Ok(assignments);
    }
    for (index, line) in text.split(|&b| b == b'\n').enumerate() {
        let number = index + 1;
        if line.iter().any(|&b| b != b'\t' && (b < 0x20 || b == 0x7f)) {
            return config_error(format!("line {number}: unsupported controls"));
        }
        let start = line.iter().position(|&b| b != b' ' && b != b'\t').unwrap_or(line.len());
        let end = line.iter().rposition(|&b| b != b' ' && b != b'\t').map_or(start, |p| p + 1);
        let line = &line[start..end.max(start)];
        if line.is_empty() || line[0] == b'#' {
            continue;
        }
        let eq = line.iter().position(|&b| b == b'=');
        let key_ok = eq.is_some_and(|eq| {
            let key = &line[..eq];
            !key.is_empty()
                && (key[0].is_ascii_uppercase() || key[0] == b'_')
                && key.iter().all(|&b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
        });
        let Some(eq) = eq.filter(|_| key_ok) else {
            return config_error(format!("line {number}: use NAME=value, no spaces around '='"));
        };
        let key = String::from_utf8_lossy(&line[..eq]).to_string();
        if !key_valid(&key) {
            return config_error(format!("line {number}: unsupported key"));
        }
        if seen.contains(&key) {
            return config_error(format!("line {number}: duplicate {key} assignment"));
        }
        let value = literal(&line[eq + 1..], number)?;
        seen.push(key.clone());
        assignments.push((key, value));
    }
    Ok(assignments)
}

pub fn domain_valid(value: &str) -> bool {
    if value.len() > 253 || !value.contains('.') || value.ends_with('.') {
        return false;
    }
    let labels: Vec<&str> = value.split('.').collect();
    let label_ok = |l: &&str| {
        let b = l.as_bytes();
        !b.is_empty()
            && b.len() <= 63
            && b[0].is_ascii_alphanumeric()
            && b[b.len() - 1].is_ascii_alphanumeric()
            && b.iter().all(|c| c.is_ascii_alphanumeric() || *c == b'-')
    };
    let last = labels.last().unwrap();
    labels.iter().all(label_ok) && (2..=63).contains(&last.len()) && last.bytes().all(|c| c.is_ascii_alphabetic())
}

pub fn local_valid(value: &str) -> bool {
    let b = value.as_bytes();
    !b.is_empty()
        && b.len() <= 64
        && b[0].is_ascii_alphanumeric()
        && b.iter().all(|c| c.is_ascii_alphanumeric() || b"._+-".contains(c))
}

/// Split ADDRESSES into trimmed local parts (spaces only, as the setup always did).
pub fn address_list(value: &str) -> Vec<String> {
    value.split(',').map(|item| item.trim_matches(' ').to_string()).filter(|item| !item.is_empty()).collect()
}

pub fn field_valid(key: &str, value: &str) -> bool {
    match key {
        "DOMAIN" => domain_valid(value),
        "DEST_EMAIL" => value.split_once('@').is_some_and(|(local, domain)| local_valid(local) && domain_valid(domain)),
        "ADDRESSES" => {
            if value.starts_with(',') || value.ends_with(',') || value.contains(",,") {
                return false;
            }
            let items: Vec<&str> = value.split(',').map(|i| i.trim_matches(' ')).collect();
            let mut seen = Vec::new();
            for item in &items {
                if !local_valid(item) || seen.contains(item) {
                    return false;
                }
                seen.push(item);
            }
            !items.is_empty()
        }
        "REGISTRAR" => matches!(value, "manual" | "godaddy"),
        "GDDY_ENV" => matches!(value, "prod" | "ote"),
        "CF_ACCOUNT_ID" | "CF_ZONE_ID" => value.len() == 32 && value.bytes().all(|c| c.is_ascii_hexdigit()),
        "DRY_RUN" => matches!(value, "0" | "1"),
        "CLOUDFLARE_API_TOKEN" | "GDDY_PAT" => value.bytes().all(printable),
        _ => false,
    }
}

impl Config {
    /// Merge environment > file > defaults, then apply CLI overrides. Only file
    /// problems fail here; field checks are in [`Config::validate`].
    pub fn read(path: PathBuf, overrides: &Overrides) -> Result<Config> {
        let mut values: HashMap<&'static str, Option<String>> = HashMap::new();
        for key in KEYS {
            values.insert(key, std::env::var_os(key).map(|v| v.to_string_lossy().into_owned()));
        }
        let mut file_domain = String::new();
        if exists_or_link(&path) {
            for (key, value) in read_file(&path)? {
                let key = KEYS.iter().find(|k| **k == key).copied().unwrap();
                if key == "DOMAIN" {
                    file_domain = value.clone();
                }
                values.entry(key).and_modify(|v| {
                    if v.is_none() {
                        *v = Some(value.clone());
                    }
                });
            }
        }
        let mut config = Config { path, values };
        for (key, default) in [("GDDY_ENV", "prod"), ("ADDRESSES", "hello"), ("DRY_RUN", "0")] {
            if !config.is_set(key) {
                config.put(key, default);
            }
        }
        if config.get("REGISTRAR").is_empty() {
            config.put("REGISTRAR", "manual");
        }
        for (key, value) in [
            ("REGISTRAR", &overrides.registrar),
            ("DOMAIN", &overrides.domain),
            ("DEST_EMAIL", &overrides.destination),
            ("ADDRESSES", &overrides.addresses),
        ] {
            if let Some(value) = value.as_ref().filter(|v| !v.is_empty()) {
                config.put(key, value);
            }
        }
        // A domain override must never reuse a zone ID belonging to the saved domain.
        let domain = config.get("DOMAIN").to_ascii_lowercase();
        if !domain.is_empty() {
            config.put("DOMAIN", &domain);
        }
        let file_domain = file_domain.to_ascii_lowercase();
        if !file_domain.is_empty() && domain != file_domain {
            config.put("CF_ZONE_ID", "");
        }
        Ok(config)
    }

    /// Read and validate (the old `config_load`).
    pub fn load(path: PathBuf, overrides: &Overrides) -> Result<Config> {
        let config = Config::read(path, overrides)?;
        config.validate()?;
        Ok(config)
    }

    pub fn get(&self, key: &str) -> &str {
        self.values.get(key).and_then(|v| v.as_deref()).unwrap_or("")
    }

    pub fn is_set(&self, key: &str) -> bool {
        self.values.get(key).is_some_and(Option::is_some)
    }

    pub fn put(&mut self, key: &str, value: &str) {
        if let Some(slot) = self.values.iter_mut().find(|(k, _)| **k == key).map(|(_, v)| v) {
            *slot = Some(value.to_string());
        }
    }

    pub fn registrar(&self) -> &str {
        match self.get("REGISTRAR") {
            "" => "manual",
            other => other,
        }
    }

    pub fn addresses(&self) -> Vec<String> {
        address_list(self.get("ADDRESSES"))
    }

    /// Empty fields are allowed while setup collects input.
    pub fn validate(&self) -> Result<()> {
        for key in KEYS {
            let value = self.get(key);
            if !value.is_empty() && !field_valid(key, value) {
                return config_error(format!("{key} has an invalid value"));
            }
        }
        Ok(())
    }

    pub fn ready(&self) -> Result<()> {
        self.validate()?;
        for key in ["DOMAIN", "DEST_EMAIL", "ADDRESSES", "CLOUDFLARE_API_TOKEN", "GDDY_ENV"] {
            if self.get(key).is_empty() {
                return config_error(format!("{key} is required"));
            }
        }
        Ok(())
    }

    /// Atomically replace one setting in the file, keeping comments and other
    /// lines; values are never printed.
    pub fn set(&mut self, key: &str, value: &str) -> Result<()> {
        if !key_valid(key) || (!value.is_empty() && !field_valid(key, value)) {
            return config_error("invalid configuration update");
        }
        if key == "DOMAIN" && self.get("DOMAIN") != value {
            self.set("CF_ZONE_ID", "")?;
        }
        if read_file(&self.path).is_err() {
            return config_error(format!("could not save {key}; check file permissions"));
        }
        write_setting(&self.path, key, value).or_else(|_| {
            die(format!(
                "could not save {key} in config — check file/directory permissions and disk space, then re-run cmail setup; do not share secret values"
            ))
        })?;
        self.put(key, value);
        Ok(())
    }
}

fn temp_path(dir: &Path) -> PathBuf {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.subsec_nanos()).unwrap_or(0);
    dir.join(format!(".cmail-config.{:08x}{:x}", nanos ^ std::process::id().rotate_left(16), std::process::id()))
}

fn write_setting(path: &Path, key: &str, value: &str) -> std::io::Result<()> {
    let current = fs::read(path)?;
    let dir = path.parent().unwrap_or(Path::new("/"));
    let tmp = temp_path(dir);
    let result = (|| {
        let mut file = fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&tmp)?;
        let body = current.strip_suffix(b"\n").unwrap_or(&current);
        if !current.is_empty() {
            for line in body.split(|&b| b == b'\n') {
                let trimmed = line.iter().position(|&b| b != b' ' && b != b'\t').map_or(&line[..0], |p| &line[p..]);
                let assigns = trimmed.starts_with(key.as_bytes()) && trimmed.get(key.len()) == Some(&b'=');
                if !assigns {
                    file.write_all(line)?;
                    file.write_all(b"\n")?;
                }
            }
        }
        writeln!(file, "{key}='{}'", value.replace('\'', "'\\''"))?;
        file.sync_all()?;
        fs::set_permissions(&tmp, fs::Permissions::from_mode(0o600))?;
        fs::rename(&tmp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    result
}

fn create_private_dir(dir: &Path) -> std::io::Result<()> {
    fs::DirBuilder::new().recursive(true).mode(0o700).create(dir)
}

fn create_from_template(path: &Path) -> std::io::Result<()> {
    let mut file = fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(path)?;
    file.write_all(TEMPLATE.as_bytes())
}

/// `cmail config init`: create a private template; keep an existing file.
pub fn init(path: &Path) -> Result<String> {
    if exists_or_link(path) {
        read_file(path)?;
        return Ok(format!("Configuration already exists: {}", path.display()));
    }
    let parent = path.parent().unwrap_or(Path::new("/"));
    if fs::symlink_metadata(parent).is_ok_and(|m| m.file_type().is_symlink()) {
        return config_error("configuration parent must not be a symlink");
    }
    if create_private_dir(parent).is_err() {
        return die("could not create configuration directory; check permissions");
    }
    if create_from_template(path).is_err() {
        return die("could not create configuration; check the selected path and directory permissions");
    }
    Ok(format!("Created private configuration: {}\nNext: cmail setup", path.display()))
}

/// Setup-only creation and permission repair (the old `env_init`).
pub fn ensure_file(path: &Path) -> Result<()> {
    if !exists_or_link(path) {
        let created = path.parent().map_or(Ok(()), create_private_dir).and_then(|_| create_from_template(path));
        if created.is_err() {
            return die(format!(
                "could not create config at {} — check the parent directory is writable, or create it with cmail config init, then re-run cmail setup",
                path.display()
            ));
        }
        ui::log(&format!("created {}", path.display()));
    }
    let meta = fs::symlink_metadata(path);
    if !meta.as_ref().is_ok_and(|m| m.file_type().is_file() && m.uid() == unsafe { libc::geteuid() }) {
        return die("config must be a user-owned regular file, not a symlink");
    }
    if fs::set_permissions(path, fs::Permissions::from_mode(0o600)).is_err() {
        return die(format!(
            "could not secure config at {} — check file ownership/permissions, set chmod 600, then re-run cmail setup",
            path.display()
        ));
    }
    Ok(())
}

/// Display value of a public setting: long opaque aliases and anything that
/// contains a secret are shown only as redacted.
pub fn public_value(config: &Config, key: &str) -> String {
    let value = config.get(key);
    let opaque = key == "ADDRESSES" && {
        let mut run = 0;
        value.bytes().any(|b| {
            run = if b.is_ascii_alphanumeric() || b"_+-".contains(&b) { run + 1 } else { 0 };
            run >= 32
        })
    };
    let leaks = ["CLOUDFLARE_API_TOKEN", "GDDY_PAT"].iter().any(|secret| {
        let token = config.get(secret);
        !token.is_empty() && value.contains(token)
    });
    if opaque || leaks {
        "<redacted>".into()
    } else {
        value.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lit(raw: &str) -> std::result::Result<String, String> {
        literal(raw.as_bytes(), 1).map_err(|e| format!("{e:?}"))
    }

    #[test]
    fn literal_quoting_matches_shell_rules() {
        assert_eq!(lit("plain").unwrap(), "plain");
        assert_eq!(lit("'a b'").unwrap(), "a b");
        assert_eq!(lit("\"a b\"").unwrap(), "a b");
        assert_eq!(lit("'it'\\''s'").unwrap(), "it's");
        assert_eq!(lit("\"a\\nb\"").unwrap(), "a\\nb");
        assert_eq!(lit("\"a\\\"b\"").unwrap(), "a\"b");
        assert_eq!(lit("\"it's\"").unwrap(), "it's");
        assert_eq!(lit("a\\ b").unwrap(), "a b");
        assert_eq!(lit("'$(x)'").unwrap(), "$(x)");
    }

    #[test]
    fn literal_refuses_shell_syntax() {
        for raw in ["$(touch x)", "`id`", "\"$HOME\"", "a b", "a;b", "a|b", "~", "*", "'open", "end\\", "a\u{7f}"] {
            assert!(lit(raw).is_err(), "{raw}");
        }
    }

    #[test]
    fn field_validation() {
        assert!(field_valid("DOMAIN", "example.com"));
        assert!(field_valid("DOMAIN", "sub.Example.co"));
        for bad in ["example", "example.", ".example.com", "a..b.com", "-a.com", "a.c0m", "http://a.com", "a.com/x"] {
            assert!(!field_valid("DOMAIN", bad), "{bad}");
        }
        assert!(field_valid("DEST_EMAIL", "me+tag@example.net"));
        assert!(!field_valid("DEST_EMAIL", "me@@example.net"));
        assert!(field_valid("ADDRESSES", "hello, contact"));
        for bad in [",a", "a,", "a,,b", "a,a", "a b"] {
            assert!(!field_valid("ADDRESSES", bad), "{bad}");
        }
        assert!(field_valid("CF_ZONE_ID", &"a".repeat(32)));
        assert!(!field_valid("CF_ZONE_ID", &"g".repeat(32)));
        assert!(!field_valid("GDDY_PAT", "a\tb"));
        assert!(!field_valid("REGISTRAR", "GoDaddy"));
    }

    fn private(dir: &Path, body: &str) -> PathBuf {
        let path = dir.join("config");
        fs::write(&path, body).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        path
    }

    #[test]
    fn read_file_rules() {
        let dir = tempfile::tempdir().unwrap();
        let path = private(dir.path(), "# comment\n  DOMAIN=example.com  \nADDRESSES='a, b'");
        let values = read_file(&path).unwrap();
        assert_eq!(values, vec![("DOMAIN".into(), "example.com".into()), ("ADDRESSES".into(), "a, b".into())]);
        for body in ["DOMAIN = x\n", "UNKNOWN=1\n", "DOMAIN=a.com\nDOMAIN=b.com\n", "DOMAIN=a.com\r\n", "lower=1\n"] {
            let path = private(dir.path(), body);
            assert!(read_file(&path).is_err(), "{body:?}");
        }
        let path = private(dir.path(), "DOMAIN=example.com\n");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(read_file(&path).is_err());
    }

    #[test]
    fn set_rewrites_one_key_privately() {
        let dir = tempfile::tempdir().unwrap();
        let path = private(
            dir.path(),
            "# keep\nDOMAIN=example.com\nCF_ZONE_ID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nADDRESSES=hello",
        );
        let mut config = Config { path: path.clone(), values: HashMap::new() };
        for key in KEYS {
            config.values.insert(key, None);
        }
        config.put("DOMAIN", "example.com");
        config.set("GDDY_PAT", "it's secret").unwrap();
        config.set("DOMAIN", "new.example").unwrap();
        let text = fs::read_to_string(&path).unwrap();
        assert!(text.starts_with("# keep\nADDRESSES=hello\n"), "{text}");
        assert!(text.contains("GDDY_PAT='it'\\''s secret'\n"));
        assert!(text.contains("CF_ZONE_ID=''\n"));
        assert!(text.ends_with("DOMAIN='new.example'\n"));
        assert_eq!(fs::metadata(&path).unwrap().mode() & 0o777, 0o600);
        let reread = read_file(&path).unwrap();
        assert!(reread.contains(&("GDDY_PAT".into(), "it's secret".into())));
    }

    #[test]
    fn redaction() {
        let mut config = Config { path: PathBuf::new(), values: HashMap::new() };
        for key in KEYS {
            config.values.insert(key, None);
        }
        config.put("ADDRESSES", &"a".repeat(40));
        assert_eq!(public_value(&config, "ADDRESSES"), "<redacted>");
        config.put("CLOUDFLARE_API_TOKEN", "tok123");
        config.put("DOMAIN", "tok123.example.com");
        assert_eq!(public_value(&config, "DOMAIN"), "<redacted>");
    }
}
