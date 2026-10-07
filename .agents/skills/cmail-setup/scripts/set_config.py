#!/usr/bin/env python3
"""Set non-secret keys in a private cmail config without reading secrets out.

Usage: python3 set_config.py [--replace] <selected-config-file> KEY=value ...
Secret keys are refused: the user enters tokens in their own editor. A key that
already holds a different non-empty value is refused unless --replace is given.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_config as config  # noqa: E402


def updates_from(args):
    updates = {}
    for arg in args:
        key, sep, value = arg.partition("=")
        if not sep or key not in config.ALLOWED:
            raise config.ConfigError("unsupported argument; use KEY=value with a documented non-secret cmail key")
        if key in config.SECRETS:
            raise config.ConfigError(f"{key}: secret keys are never set by this helper; the user enters them in a local editor")
        if key in updates:
            raise config.ConfigError(f"{key}: given twice; pass each key once")
        config.check_field(key, value)
        # Validated values never contain quotes, so single quotes are exact.
        updates[key] = value
    if not updates:
        raise config.ConfigError("no KEY=value given; pass at least one non-secret key")
    return updates


def conflicts(values, updates):
    return [key for key, value in updates.items() if values.get(key) and values[key] != value]


def apply(text, updates):
    lines = text.split("\n")
    pending = dict(updates)
    for index, line in enumerate(lines):
        match = re.match(r"[ \t]*([A-Z_][A-Z0-9_]*)=", line)
        if match and match.group(1) in pending:
            key = match.group(1)
            lines[index] = f"{key}='{pending.pop(key)}'"
    if lines and lines[-1] == "":
        lines.pop()
    lines.extend(f"{key}='{value}'" for key, value in pending.items())
    return "\n".join(lines) + "\n"


def write_private(path, text):
    # Replace atomically from a mode-600 temporary file in the same directory.
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".cmail-config.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv):
    replace = len(argv) > 1 and argv[1] == "--replace"
    args = argv[2:] if replace else argv[1:]
    if len(args) < 2:
        print("Error: expected a config path and KEY=value pairs. Run: python3 set_config.py [--replace] <selected-config-file> KEY=value ...", file=sys.stderr)
        return 2
    path = args[0]
    try:
        updates = updates_from(args[1:])
        text = config.read_private(path)
        values = config.parse(text)  # refuse to rewrite a file outside the literal subset
        held = conflicts(values, updates)
        if held and not replace:
            raise config.ConfigError(", ".join(held) + ": already set to a different value; confirm the change, then pass --replace")
        result = apply(text, updates)
        config.parse(result)
        write_private(path, result)
    except config.ConfigError as exc:
        print(f"Error: {exc}. Nothing was written; secret values are never displayed.", file=sys.stderr)
        return 1
    except OSError:
        print("Error: cannot safely update selected config. Check it exists, is a non-symlink you own with mode 600 and its directory is writable, then re-run.", file=sys.stderr)
        return 1
    print("UPDATED: " + ", ".join(updates) + "; other lines unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
