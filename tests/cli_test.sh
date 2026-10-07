#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMAIL_TEST_BASH="${CMAIL_TEST_BASH:-$BASH}" PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tests/cli_test.py"
