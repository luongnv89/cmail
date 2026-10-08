#!/usr/bin/env python3
"""Run a command with a terminal stdin fed from this script's stdin; exit with its status."""
import os
import pty
import subprocess
import sys

data = sys.stdin.buffer.read()
master, slave = pty.openpty()
try:
    proc = subprocess.Popen(sys.argv[1:], stdin=slave, stdout=subprocess.DEVNULL)
    os.write(master, data)
    sys.exit(proc.wait(timeout=10))
finally:
    os.close(slave)
    os.close(master)
