//! Failure categories map one-to-one onto the documented exit codes.

#[derive(Debug)]
pub enum Error {
    /// Invalid arguments or a command used where it cannot run (exit 2).
    Usage(String),
    /// Invalid or incomplete configuration or input (exit 3).
    Config(String),
    /// Provider, network, or runtime failure (exit 1).
    Fail(String),
    /// Diagnostics were already printed; exit with this code.
    Exit(i32),
}

pub type Result<T> = std::result::Result<T, Error>;

impl Error {
    pub fn code(&self) -> i32 {
        match self {
            Error::Usage(_) => 2,
            Error::Config(_) => 3,
            Error::Fail(_) => 1,
            Error::Exit(code) => *code,
        }
    }
}

/// Runtime failure with an actionable message (the old `die`).
pub fn die<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::Fail(message.into()))
}

pub fn usage<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::Usage(message.into()))
}

pub fn config_error<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::Config(message.into()))
}
