#!/usr/bin/env python3
"""Run a fixture CLI with terminal stdin and captured/inherited result streams."""
import os
import pty
import subprocess
import sys

master, slave = pty.openpty()
try:
    result = subprocess.run(sys.argv[1:], stdin=slave, timeout=10)
    sys.exit(result.returncode)
finally:
    os.close(slave)
    os.close(master)
