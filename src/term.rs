//! Terminal state, hidden input, interrupts, and test-observable sleeping.

use std::io::{self, BufRead, Read, Write};
use std::sync::Mutex;
use std::time::Duration;

static SAVED_TERMIOS: Mutex<Option<libc::termios>> = Mutex::new(None);

pub fn stdin_is_tty() -> bool {
    unsafe { libc::isatty(0) == 1 }
}

pub fn fd_is_tty(fd: i32) -> bool {
    unsafe { libc::isatty(fd) == 1 }
}

/// Columns of the terminal on `fd`, if it is one.
pub fn fd_columns(fd: i32) -> Option<usize> {
    let mut size: libc::winsize = unsafe { std::mem::zeroed() };
    let ok = unsafe { libc::ioctl(fd, libc::TIOCGWINSZ, &mut size) } == 0;
    (ok && size.ws_col > 0).then_some(size.ws_col as usize)
}

fn restore_echo() {
    if let Ok(mut saved) = SAVED_TERMIOS.lock() {
        if let Some(original) = saved.take() {
            unsafe { libc::tcsetattr(0, libc::TCSANOW, &original) };
        }
    }
}

/// Read one line from stdin. `None` means end of input.
pub fn read_line() -> Option<String> {
    let mut line = String::new();
    match io::stdin().lock().read_line(&mut line) {
        Ok(0) | Err(_) => None,
        Ok(_) => {
            if line.ends_with('\n') {
                line.pop();
            }
            Some(line)
        }
    }
}

/// Read one line without echo (like `read -rs`); echo is restored even on interrupt.
pub fn read_secret() -> Option<String> {
    let mut original: libc::termios = unsafe { std::mem::zeroed() };
    let have_tty = unsafe { libc::tcgetattr(0, &mut original) } == 0;
    if have_tty {
        *SAVED_TERMIOS.lock().unwrap() = Some(original);
        let mut hidden = original;
        hidden.c_lflag &= !libc::ECHO;
        unsafe { libc::tcsetattr(0, libc::TCSANOW, &hidden) };
    }
    let line = read_line();
    if have_tty {
        restore_echo();
    }
    line
}

/// Read all of stdin up to `limit` bytes (more is reported by a longer result).
pub fn read_stdin_bytes(limit: usize) -> Vec<u8> {
    let mut buffer = Vec::new();
    let _ = io::stdin().lock().take(limit as u64).read_to_end(&mut buffer);
    buffer
}

/// Sleep, or with the test hook `CMAIL_TEST_SLEEP_LOG` record the delay and return at once.
pub fn sleep(seconds: u64) {
    if let Some(path) = std::env::var_os("CMAIL_TEST_SLEEP_LOG") {
        if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(file, "sleep {seconds}");
        }
        return;
    }
    std::thread::sleep(Duration::from_secs(seconds));
}

/// What to print when an interrupt arrives (setup prints its recovery guide).
pub type InterruptHook = fn();
static INTERRUPT_HOOK: Mutex<Option<InterruptHook>> = Mutex::new(None);

pub fn set_interrupt_hook(hook: Option<InterruptHook>) {
    *INTERRUPT_HOOK.lock().unwrap() = hook;
}

/// SIGINT exits 130 and SIGTERM 143, after restoring echo and running the hook.
pub fn install_signal_handlers() {
    use signal_hook::consts::{SIGINT, SIGTERM};
    let Ok(mut signals) = signal_hook::iterator::Signals::new([SIGINT, SIGTERM]) else {
        return;
    };
    std::thread::spawn(move || {
        if let Some(signal) = signals.forever().next() {
            restore_echo();
            let hook = INTERRUPT_HOOK.lock().ok().and_then(|hook| *hook);
            if let Some(hook) = hook {
                hook();
            }
            let _ = io::stderr().flush();
            std::process::exit(if signal == SIGINT { 130 } else { 143 });
        }
    });
}
