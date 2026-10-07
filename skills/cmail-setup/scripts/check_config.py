#!/usr/bin/env python3
"""Read-only, value-free validation of cmail's literal assignment configuration."""
import os
import re
import shlex
import stat
import sys

REQUIRED = ("DOMAIN", "DEST_EMAIL", "ADDRESSES", "CLOUDFLARE_API_TOKEN", "GDDY_ENV")
ALLOWED = set(REQUIRED) | {"GDDY_PAT", "CF_ACCOUNT_ID", "CF_ZONE_ID", "DRY_RUN"}
DOMAIN = re.compile(r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}\Z")
LOCAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")


class ConfigError(ValueError):
    """Messages contain only fixed field names/line numbers, never values."""


def parse(text):
    values = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_][A-Z0-9_]*)=(.*)", line)
        if not match or "$" in line or "`" in line or "\x00" in line or (match and match.group(2).startswith("~")):
            raise ConfigError(f"line {number}: use literal KEY=value assignments; remove commands/expansions locally")
        key, raw = match.groups()
        if key not in ALLOWED:
            raise ConfigError(f"line {number}: unsupported key; use only documented cmail keys and review extra settings locally")
        if key in values:
            raise ConfigError(f"line {number}: duplicate assignment; remove the duplicate locally")
        lexer = shlex.shlex(raw, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        try:
            tokens = list(lexer)
        except ValueError:
            raise ConfigError(f"line {number}: invalid quoting; correct quotes locally") from None
        if len(tokens) > 1 or (tokens and all(c in ";&|<>()" for c in tokens[0])):
            raise ConfigError(f"line {number}: not a single literal value; quote spaces and remove commands locally")
        values[key] = tokens[0] if tokens else ""
    return values


def validate(values):
    for key in REQUIRED:
        if not values.get(key):
            raise ConfigError(f"{key}: required field missing/empty; fill it locally")
    if not DOMAIN.fullmatch(values["DOMAIN"]):
        raise ConfigError("DOMAIN: use a domain name without scheme/path; correct it locally")
    email = values["DEST_EMAIL"]
    parts = email.split("@")
    if len(parts) != 2 or not LOCAL.fullmatch(parts[0]) or not DOMAIN.fullmatch(parts[1]):
        raise ConfigError("DEST_EMAIL: use a full receiving email address; correct it locally")
    addresses = [item.strip() for item in values["ADDRESSES"].split(",")]
    if not all(LOCAL.fullmatch(item) for item in addresses) or len(set(addresses)) != len(addresses):
        raise ConfigError("ADDRESSES: use unique comma-separated local parts only; correct it locally")
    if values["GDDY_ENV"] not in ("prod", "ote"):
        raise ConfigError("GDDY_ENV: set prod or ote locally")
    for key in ("CF_ACCOUNT_ID", "CF_ZONE_ID"):
        if values.get(key) and not re.fullmatch(r"[0-9a-fA-F]{32}", values[key]):
            raise ConfigError(f"{key}: use the intended 32-character hex ID; correct it locally")
    if values.get("DRY_RUN", "0") not in ("0", "1"):
        raise ConfigError("DRY_RUN: set 0 or 1 locally; this controls nameserver preview only")


def check(path):
    # Open without following the final symlink and check the opened file, not a
    # separate stat result. Parent directories still must be trusted by the user.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ConfigError("selected config must be a user-owned regular file with mode 600; fix ownership/permissions locally")
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ConfigError("selected config exceeds 64 KiB; review and reduce it locally")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise ConfigError("selected config is not UTF-8 text; correct its encoding locally") from None
    validate(parse(text))


def main(argv):
    if len(argv) != 2:
        print("Error: expected one config path. Run: python3 check_config.py <selected-config-file>", file=sys.stderr)
        return 2
    try:
        check(argv[1])
    except ConfigError as exc:
        print(f"Error: {exc}. Re-run this check after repair; values are never displayed.", file=sys.stderr)
        return 1
    except OSError:
        print("Error: cannot safely open selected config. Check existence, read access and non-symlink path locally, then re-run.", file=sys.stderr)
        return 1
    print("PASS: private literal config and required fields verified; provider access and mail delivery NOT checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
