//! Command tree, option rules, help text, and usage errors (exit 2).
//! Parsing happens before configuration, dependency checks, or provider access.

use crate::config::KEYS;
use crate::style::{Mode, Tier};
use clap::builder::styling::{AnsiColor, Ansi256Color, Color, RgbColor, Style, Styles};
use clap::builder::{NonEmptyStringValueParser, PossibleValuesParser};
use clap::{Args, ColorChoice, CommandFactory, FromArgMatches, Parser, Subcommand, ValueEnum};

const START_HERE: &str = "\
Start here:
  cmail config init
  cmail doctor --offline
  cmail setup

Options go before or after the command. Use -- to end option parsing.
Exit codes: 0 success, 1 provider or runtime failure, 2 invalid arguments,
3 invalid configuration or input, 130 interrupted.";

const SETUP_ABOUT: &str = "\
Configure receiving for a domain at any registrar. Run in a terminal.
By default you update nameservers at your registrar yourself; cmail prints them.
Elapsed time includes user input, provider requests, and verification waits.";

const FORWARD_ABOUT: &str = "\
Change where an existing address forwards. Run in a terminal; asks before writing.
ADDRESS is a local part (hello) or LOCAL@DOMAIN. The address and its rule are kept;
only the forwarding destination changes.

DEST_EMAIL in the configuration is updated only when every configured address
on the configured domain then forwards to EMAIL.";

#[derive(Parser, Debug)]
#[command(
    name = "cmail",
    version,
    about = "cmail — free custom-domain email with Cloudflare Email Routing",
    after_help = START_HERE,
    propagate_version = true,
    max_term_width = 100
)]
pub struct Cli {
    #[command(flatten)]
    pub global: Global,
    #[command(subcommand)]
    pub command: Option<Command>,
}

#[derive(Args, Debug)]
#[command(next_help_heading = "Global options")]
pub struct Global {
    /// Select private configuration (default: CMAIL_CONFIG, ENV_FILE, then ~/.config/cmail/.env)
    #[arg(short = 'c', long, global = true, value_name = "PATH", value_parser = NonEmptyStringValueParser::new())]
    pub config: Option<String>,
    /// Report format (default: CMAIL_FORMAT or text)
    #[arg(short = 'f', long, global = true, value_enum, value_name = "FORMAT")]
    pub format: Option<Format>,
    /// Additional redacted diagnostics
    #[arg(short = 'v', long, global = true, conflicts_with = "quiet")]
    pub verbose: bool,
    /// Suppress routine progress; keep results and errors
    #[arg(short = 'q', long, global = true)]
    pub quiet: bool,
    /// Disable color (also respects NO_COLOR)
    #[arg(long, global = true)]
    pub no_color: bool,
    /// Print links for manual opening instead of launching a browser
    #[arg(long, global = true)]
    pub no_browser: bool,
    /// HTTP request timeout (default: CMAIL_TIMEOUT or 30)
    #[arg(long, global = true, value_name = "SECONDS", value_parser = clap::value_parser!(u32).range(1..=999_999))]
    pub timeout: Option<u32>,
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum Format {
    Text,
    Json,
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum Registrar {
    Manual,
    Godaddy,
}

impl Registrar {
    pub fn as_str(self) -> &'static str {
        match self {
            Registrar::Manual => "manual",
            Registrar::Godaddy => "godaddy",
        }
    }
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum Shell {
    Bash,
    Zsh,
    Fish,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    /// Configure receiving with a guided workflow
    #[command(long_about = SETUP_ABOUT)]
    Setup(SetupArgs),
    /// Inspect zone, routing, destinations, and rules
    #[command(long_about = "Read-only Cloudflare zone, routing, destination, and rule report.\nUse --format json for scripts.")]
    Status,
    /// List a domain's addresses and where each forwards
    #[command(
        long_about = "Read-only list of every address on a domain, where it forwards, and the catch-all rule.\nUse --format json for scripts."
    )]
    List {
        /// Domain to list (default: DOMAIN setting); uses the configured token
        #[arg(long, value_name = "DOMAIN", value_parser = NonEmptyStringValueParser::new())]
        domain: Option<String>,
    },
    /// Change where an existing address forwards
    #[command(long_about = FORWARD_ABOUT)]
    Forward(ForwardArgs),
    /// Check configuration, tools, and authentication
    #[command(long_about = "Read-only configuration, tool, and authentication checks. Never installs tools.")]
    Doctor {
        /// Check local tools and configuration without contacting providers
        #[arg(long)]
        offline: bool,
    },
    /// Optional Gmail sending guide: cmail send-as
    #[command(long_about = "Optional manual Gmail sending guide. Requires a terminal and configured receiving.")]
    SendAs,
    /// Manage private configuration
    Config {
        #[command(subcommand)]
        command: Option<ConfigCommand>,
    },
    /// Print bash, zsh, or fish completions
    #[command(
        long_about = "Print a completion script.\n  bash: cmail completion bash > ~/.local/share/bash-completion/completions/cmail\n  zsh:  cmail completion zsh > \"${fpath[1]}/_cmail\"\n  fish: cmail completion fish > ~/.config/fish/completions/cmail.fish"
    )]
    Completion {
        #[arg(value_enum)]
        shell: Shell,
    },
}

#[derive(Args, Debug, Default)]
pub struct SetupArgs {
    /// Domain name (default: DOMAIN setting)
    #[arg(long, value_name = "DOMAIN", value_parser = NonEmptyStringValueParser::new())]
    pub domain: Option<String>,
    /// Registrar handling (default: REGISTRAR setting, else manual). godaddy opts in to gddy
    /// automation: nameserver changes need confirmation; domain purchase is offered only in
    /// this mode and needs the domain typed at a terminal
    #[arg(long, value_enum, value_name = "REGISTRAR")]
    pub registrar: Option<Registrar>,
    /// Receiving inbox (default: DEST_EMAIL setting)
    #[arg(long, value_name = "EMAIL", value_parser = NonEmptyStringValueParser::new())]
    pub destination: Option<String>,
    /// Unique comma-separated local parts (default: ADDRESSES setting)
    #[arg(long, value_name = "LIST", value_parser = NonEmptyStringValueParser::new())]
    pub addresses: Option<String>,
    /// Read-only plan; requires existing credentials, never writes
    #[arg(long)]
    pub dry_run: bool,
    /// Limit each activation/verification wait
    #[arg(long, value_name = "SECONDS", default_value_t = 1200, value_parser = clap::value_parser!(u64).range(1..=999_999))]
    pub wait_timeout: u64,
}

#[derive(Args, Debug)]
pub struct ForwardArgs {
    /// Local part (hello) or LOCAL@DOMAIN
    pub address: String,
    /// New receiving inbox (required). If Cloudflare has not verified it yet, nothing
    /// changes: cmail offers to send the verification email; rerun after clicking it
    #[arg(long, value_name = "EMAIL", required = true, value_parser = NonEmptyStringValueParser::new())]
    pub destination: String,
    /// Domain of the address (default: DOMAIN setting)
    #[arg(long, value_name = "DOMAIN", value_parser = NonEmptyStringValueParser::new())]
    pub domain: Option<String>,
}

#[derive(Subcommand, Debug)]
pub enum ConfigCommand {
    /// Create a private mode-600 template; preserve an existing configuration
    Init,
    /// Show effective public settings and secret presence, never secret values
    Show,
    /// Check required settings and readiness; incomplete/invalid input exits 3
    Check,
    /// Update one documented setting atomically; secret keys require --stdin
    Set {
        /// Setting to update
        #[arg(value_name = "KEY", value_parser = PossibleValuesParser::new(KEYS))]
        key: String,
        /// Literal value; mutually exclusive with --stdin
        #[arg(value_name = "VALUE", conflicts_with = "stdin")]
        value: Option<String>,
        /// Read one value from standard input without echoing it
        #[arg(long)]
        stdin: bool,
    },
    /// Print the selected configuration path without creating it
    Path,
}

/// Everything commands need from the command line, after cross-option checks.
#[derive(Debug)]
pub struct Invocation {
    pub cli: Cli,
    pub json: bool,
    pub timeout: u32,
    pub verbose: bool,
    pub quiet: bool,
    pub command_path: String,
}

fn rgb(mode: &Mode, rgb: (u8, u8, u8), basic: AnsiColor) -> Option<Color> {
    match mode.tier {
        Tier::True => Some(Color::Rgb(RgbColor(rgb.0, rgb.1, rgb.2))),
        Tier::C256 => Some(Color::Ansi256(Ansi256Color(crate::style::to_256(rgb)))),
        Tier::C16 => Some(Color::Ansi(basic)),
        Tier::None => None,
    }
}

/// Help uses the accent role for flags and commands and the title role for headings.
fn styles(mode: &Mode) -> Styles {
    let accent = Style::new().bold().fg_color(rgb(mode, (0xb5, 0x40, 0x40), AnsiColor::BrightRed));
    Styles::styled()
        .header(Style::new().bold())
        .usage(Style::new().bold())
        .literal(accent)
        .placeholder(Style::new().dimmed())
        .valid(accent)
        .invalid(Style::new().bold().fg_color(rgb(mode, (0xdc, 0x4c, 0x4c), AnsiColor::BrightRed)))
        .error(Style::new().bold().fg_color(rgb(mode, (0xdc, 0x4c, 0x4c), AnsiColor::BrightRed)))
}

pub fn command(stdout: &Mode) -> clap::Command {
    let colored = stdout.styled && stdout.tier != Tier::None;
    Cli::command().styles(styles(stdout)).color(if colored { ColorChoice::Always } else { ColorChoice::Never })
}

fn strip_ansi(text: &str) -> String {
    let mut out = String::new();
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            for n in chars.by_ref() {
                if n.is_ascii_alphabetic() {
                    break;
                }
            }
        } else {
            out.push(c);
        }
    }
    out
}

/// The failing command's path, from clap's usage line ("Usage: cmail config set ...").
fn usage_path(rendered: &str) -> String {
    rendered
        .lines()
        .find_map(|l| l.trim().strip_prefix("Usage: cmail"))
        .map(|rest| {
            rest.split_whitespace()
                .take_while(|w| w.chars().all(|c| c.is_ascii_lowercase() || c == '-') && !w.starts_with('-'))
                .collect::<Vec<_>>()
                .join(" ")
        })
        .unwrap_or_default()
}

pub enum Parsed {
    Run(Box<Invocation>),
    /// Help or version printed, or a usage error: (exit code, error message, command path).
    Done(i32, Option<(String, String)>),
}

fn bool_env(key: &str) -> Result<bool, String> {
    match std::env::var(key).unwrap_or_default().as_str() {
        "" | "0" => Ok(false),
        "1" => Ok(true),
        _ => Err("--verbose and --quiet are mutually exclusive boolean settings".into()),
    }
}

pub fn parse(args: Vec<std::ffi::OsString>, stdout: &Mode) -> Parsed {
    let mut cmd = command(stdout);
    // `cmail help --help` documents the help command itself.
    let words: Vec<String> = args.iter().skip(1).map(|a| a.to_string_lossy().into_owned()).collect();
    if words.first().is_some_and(|w| w == "help") && words.iter().any(|w| w == "--help" || w == "-h") {
        cmd.build();
        let _ = cmd.find_subcommand_mut("help").expect("help subcommand").print_help();
        return Parsed::Done(0, None);
    }
    let matches = match cmd.try_get_matches_from_mut(args) {
        Ok(matches) => matches,
        Err(error) => {
            use clap::error::ErrorKind::*;
            if matches!(error.kind(), DisplayHelp | DisplayVersion) {
                let _ = error.print();
                return Parsed::Done(0, None);
            }
            let rendered = strip_ansi(&error.render().to_string());
            let message = rendered.lines().next().unwrap_or("invalid arguments").trim_start_matches("error: ").to_string();
            return Parsed::Done(2, Some((message, usage_path(&rendered))));
        }
    };
    let cli = match Cli::from_arg_matches(&matches) {
        Ok(cli) => cli,
        Err(error) => return Parsed::Done(2, Some((strip_ansi(&error.to_string()), String::new()))),
    };
    let mut path = Vec::new();
    let mut current = &matches;
    while let Some((name, sub)) = current.subcommand() {
        path.push(name.to_string());
        current = sub;
    }
    let command_path = path.join(" ");
    let fail = |message: &str| Parsed::Done(2, Some((message.to_string(), command_path.clone())));

    let Some(command) = &cli.command else {
        let _ = cmd.print_help();
        return Parsed::Done(0, None);
    };
    if let Command::Config { command: None } = command {
        let _ = cmd.find_subcommand_mut("config").expect("config").print_help();
        return Parsed::Done(0, None);
    }

    let json = match cli.global.format {
        Some(format) => format == Format::Json,
        None => match std::env::var("CMAIL_FORMAT").unwrap_or_default().as_str() {
            "" | "text" => false,
            "json" => true,
            _ => return fail("--format must be text or json"),
        },
    };
    let timeout = match cli.global.timeout {
        Some(timeout) => timeout,
        None => match std::env::var("CMAIL_TIMEOUT").ok().filter(|v| !v.is_empty()) {
            None => 30,
            Some(value) => match value.parse::<u32>() {
                Ok(t) if (1..=999_999).contains(&t) && !value.starts_with('0') => t,
                _ => return fail("--timeout must be a positive integer (at most 999999 seconds)"),
            },
        },
    };
    let (env_verbose, env_quiet) = match (bool_env("CMAIL_VERBOSE"), bool_env("CMAIL_QUIET")) {
        (Ok(v), Ok(q)) if !(v && q) => (v, q),
        _ => return fail("--verbose and --quiet are mutually exclusive boolean settings"),
    };
    let verbose = cli.global.verbose || (env_verbose && !cli.global.quiet);
    let quiet = cli.global.quiet || (env_quiet && !cli.global.verbose);

    if let Command::Config { command: Some(ConfigCommand::Set { value, stdin, .. }) } = command {
        if !stdin && value.is_none() {
            return fail("config set needs KEY and VALUE, or KEY --stdin");
        }
    }
    if json {
        let allowed = matches!(
            command,
            Command::Status
                | Command::List { .. }
                | Command::Doctor { .. }
                | Command::Setup(_)
                | Command::Config { command: Some(ConfigCommand::Show | ConfigCommand::Check) }
        );
        if !allowed {
            return fail("JSON is available for status, list, doctor, config show/check, and setup --dry-run");
        }
    }
    Parsed::Run(Box::new(Invocation { cli, json, timeout, verbose, quiet, command_path }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_tree_is_consistent() {
        Cli::command().debug_assert();
    }

    #[test]
    fn usage_path_from_rendered_error() {
        assert_eq!(usage_path("error: x\n\nUsage: cmail config set <KEY> [VALUE]\n"), "config set");
        assert_eq!(usage_path("Usage: cmail [OPTIONS] [COMMAND]"), "");
    }

    #[test]
    fn strip_ansi_removes_sgr() {
        assert_eq!(strip_ansi("\x1b[1merror:\x1b[0m x"), "error: x");
    }
}
