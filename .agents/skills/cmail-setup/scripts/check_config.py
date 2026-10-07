#!/usr/bin/env python3
"""Read-only validation of cmail's literal assignment configuration.

Default mode prints no values. --summary prints well-formed non-secret values
only (anything else shows as <invalid>) and reports secrets as set/empty/absent,
so an agent can plan without seeing them. --summary exits 0 when READY, else 3.
"""
import os
import re
import stat
import sys

REQUIRED = ("DOMAIN", "DEST_EMAIL", "ADDRESSES", "CLOUDFLARE_API_TOKEN", "GDDY_ENV")
SECRETS = ("CLOUDFLARE_API_TOKEN", "GDDY_PAT")
PUBLIC = ("DOMAIN", "DEST_EMAIL", "ADDRESSES", "GDDY_ENV", "CF_ACCOUNT_ID", "CF_ZONE_ID", "DRY_RUN")
ALLOWED = set(REQUIRED) | set(SECRETS) | set(PUBLIC)
DOMAIN = re.compile(r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}\Z")
LOCAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")
# Keys whose format check alone admits an arbitrary opaque string, so --summary
# must also screen the value for a token shape before echoing it. Addresses are
# any comma-separated local parts, so a misplaced credential can pass is_addresses.
PERMISSIVE = ("ADDRESSES",)
# An unbroken run of token-alphabet characters this long is treated as a possible
# credential (e.g. a 40-character Cloudflare token) rather than an alias. Real
# cmail local parts are short, so --summary shows <invalid> instead of echoing it.
TOKEN_LIKE = re.compile(r"[A-Za-z0-9_+-]{32,}")


class ConfigError(ValueError):
    """Messages contain only fixed field names/line numbers, never values."""


def literal(raw, number):
    """Decode one restricted Bash assignment word, never evaluating shell code."""
    result = []
    quote = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if quote == "'":
            if char == "'":
                quote = None
            else:
                result.append(char)
        elif char == "\\" and quote != "'":
            index += 1
            if index == len(raw):
                raise ConfigError(f"line {number}: dangling escape; correct quoting locally")
            escaped = raw[index]
            # Bash keeps backslashes before ordinary characters in double quotes.
            if quote == '"' and escaped not in '\\"':
                result.append("\\")
            result.append(escaped)
        elif quote == '"':
            if char == '"':
                quote = None
            else:
                result.append(char)
        elif char in "'\"":
            quote = char
        elif char.isspace() or char in ";&|<>()~*?[]{}":
            raise ConfigError(f"line {number}: not a single literal value; quote spaces and remove shell syntax locally")
        else:
            result.append(char)
        index += 1
    if quote is not None:
        raise ConfigError(f"line {number}: invalid quoting; correct quotes locally")
    return "".join(result)


def parse(text):
    # Bash separates commands only at LF, unlike splitlines()/Unicode strip.
    # Reject other controls/separators even in comments before interpretation.
    if any(not char.isprintable() and char not in "\n\t" for char in text):
        raise ConfigError("selected config contains unsupported controls or line separators; use LF-only text locally")
    values = {}
    for number, line in enumerate(text.split("\n"), 1):
        line = line.strip(" \t")
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_][A-Z0-9_]*)=(.*)", line)
        if not match or "$" in line or "`" in line or "\x00" in line or (match and match.group(2).startswith("~")):
            raise ConfigError(f"line {number}: use literal KEY=value assignments; remove commands/expansions locally")
        key, raw = match.groups()
        if not raw.isascii():
            raise ConfigError(f"line {number}: non-ASCII characters (such as smart quotes); retype the value locally")
        if key not in ALLOWED:
            raise ConfigError(f"line {number}: unsupported key; use only documented cmail keys and review extra settings locally")
        if key in values:
            raise ConfigError(f"line {number}: duplicate assignment; remove the duplicate locally")
        values[key] = literal(raw, number)
    return values


def is_email(value):
    parts = value.split("@")
    return len(parts) == 2 and bool(LOCAL.fullmatch(parts[0])) and bool(DOMAIN.fullmatch(parts[1]))


def is_addresses(value):
    addresses = [item.strip() for item in value.split(",")]
    return all(LOCAL.fullmatch(item) for item in addresses) and len(set(addresses)) == len(addresses)


# Format checks for every non-secret key; set_config.py reuses them.
FIELDS = {
    "DOMAIN": (lambda v: bool(DOMAIN.fullmatch(v)), "use a domain name without scheme/path"),
    "DEST_EMAIL": (is_email, "use a full receiving email address"),
    "ADDRESSES": (is_addresses, "use unique comma-separated local parts only"),
    "GDDY_ENV": (lambda v: v in ("prod", "ote"), "set prod or ote"),
    "CF_ACCOUNT_ID": (lambda v: bool(re.fullmatch(r"[0-9a-fA-F]{32}", v)), "use the intended 32-character hex ID"),
    "CF_ZONE_ID": (lambda v: bool(re.fullmatch(r"[0-9a-fA-F]{32}", v)), "use the intended 32-character hex ID"),
    "DRY_RUN": (lambda v: v in ("0", "1"), "set 0 or 1; this controls nameserver preview only"),
}


def check_field(key, value):
    valid, hint = FIELDS[key]
    if not valid(value):
        raise ConfigError(f"{key}: {hint}; correct it locally")


def validate(values):
    for key in REQUIRED:
        if not values.get(key):
            raise ConfigError(f"{key}: required field missing/empty; fill it locally")
    for key in PUBLIC:
        if values.get(key):
            check_field(key, values[key])


def read_private(path):
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
        return raw.decode("utf-8")
    except UnicodeError:
        raise ConfigError("selected config is not UTF-8 text; correct its encoding locally") from None


def check(path):
    validate(parse(read_private(path)))


def summary(path):
    values = parse(read_private(path))
    lines = []
    for key in PUBLIC:
        if key not in values:
            lines.append(f"{key} absent")
        elif values[key] and not FIELDS[key][0](values[key]):
            lines.append(f"{key}=<invalid>")  # never echo a misplaced secret
        elif key in PERMISSIVE and TOKEN_LIKE.search(values[key]):
            lines.append(f"{key}=<invalid>")  # format admits opaque tokens; never echo one
        else:
            lines.append(f"{key}={values[key]}")
    for key in SECRETS:
        state = "absent" if key not in values else ("set" if values[key] else "empty")
        lines.append(f"{key} {state}")
    try:
        validate(values)
        lines.append("READY: required fields present and well-formed")
        ready = True
    except ConfigError as exc:
        lines.append(f"NOT READY: {exc}")
        ready = False
    return "\n".join(lines), ready


def main(argv):
    show = len(argv) == 3 and argv[1] == "--summary"
    if len(argv) != 2 and not show:
        print("Error: expected one config path. Run: python3 check_config.py [--summary] <selected-config-file>", file=sys.stderr)
        return 2
    try:
        if show:
            text, ready = summary(argv[2])
            print(text)
            return 0 if ready else 3
        check(argv[1])
    except ConfigError as exc:
        print(f"Error: {exc}. Re-run this check after repair; secret values are never displayed.", file=sys.stderr)
        return 1
    except OSError:
        print("Error: cannot safely open selected config. Check existence, read access and non-symlink path locally, then re-run.", file=sys.stderr)
        return 1
    print("PASS: private literal config and required fields verified; provider access and mail delivery NOT checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
