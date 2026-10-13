#!/usr/bin/env python3
"""Timing and terminal contracts for setup, against the loopback API fixture."""
import json
import os
from pathlib import Path
import pty
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(os.environ.get('CMAIL_BIN', ROOT / 'target' / 'debug' / 'cmail'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_server import FixtureServer  # noqa: E402

ZONE, ACCOUNT = 'a' * 32, 'b' * 32


class Timing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('CMAIL_') and k not in
                    ('DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'CF_ZONE_ID', 'CF_ACCOUNT_ID', 'GDDY_PAT', 'REGISTRAR',
                     'CLOUDFLARE_API_TOKEN', 'DRY_RUN', 'ENV_FILE', 'GDDY_ENV', 'NO_COLOR', 'FORCE_COLOR')}
        self.config = self.directory / 'config'
        self.config.write_text('DOMAIN=example.com\nDEST_EMAIL=owner@example.net\nADDRESSES=hello,contact\n'
                               'CLOUDFLARE_API_TOKEN=synthetic-token\nGDDY_ENV=ote\n')
        self.config.chmod(0o600)
        self.env['ENV_FILE'] = str(self.config)
        self.status('active')

    def status(self, state):
        rules = [{'id': 'r-' + a, 'enabled': True, 'matchers': [{'type': 'literal', 'field': 'to', 'value': a + '@example.com'}],
                  'actions': [{'type': 'forward', 'value': ['owner@example.net']}]} for a in ('hello', 'contact')]
        fixtures = {
            '/user/tokens/verify': {'success': True, 'result': {'status': 'active'}},
            '/zones?name=example.com': {'success': True, 'result': [{'id': ZONE, 'name': 'example.com'}]},
            '/zones/' + ZONE: {'success': True, 'result': {'id': ZONE, 'name': 'example.com', 'status': state,
                               'account': {'id': ACCOUNT}, 'name_servers': ['alice.ns.cloudflare.com', 'bob.ns.cloudflare.com']}},
            '/zones/' + ZONE + '/email/routing': {'success': True, 'result': {'enabled': True, 'status': 'ready'}},
            '/accounts/' + ACCOUNT + '/email/routing/addresses?per_page=50&page=1': {
                'success': True, 'result': [{'email': 'owner@example.net', 'verified': '2026-01-01T00:00:00Z'}]},
            '/zones/' + ZONE + '/email/routing/rules?per_page=50&page=1': {'success': True, 'result': rules},
        }
        responses = self.directory / 'responses.json'
        responses.write_text(json.dumps(fixtures))
        if not hasattr(self, 'server'):
            self.server = FixtureServer(str(responses), str(self.directory / 'calls'))
            self.addCleanup(self.server.close)
            self.env['CMAIL_CF_API'] = self.server.url

    def terminal(self, args=(), env=None, timeout=10):
        master, slave = pty.openpty()
        try:
            return subprocess.run([str(BIN), 'setup', *args], stdin=slave, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=dict(self.env, **(env or {})), timeout=timeout)
        finally:
            os.close(master)
            os.close(slave)

    def test_success_includes_elapsed_and_addresses(self):
        result = self.terminal()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('hello@example.com -> owner@example.net', result.stdout)
        self.assertIn('contact@example.com -> owner@example.net', result.stdout)
        self.assertRegex(result.stdout, r'Elapsed time: \d+m \d+s \(\d+ seconds?\)')
        self.assertIn('DIFFERENT mailbox', result.stdout)
        self.assertNotIn('synthetic-token', result.stdout + result.stderr)

    def test_failure_includes_elapsed_and_runtime_exit_code(self):
        self.status('pending')
        result = self.terminal(('--wait-timeout', '1'))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr.count('Setup stopped at:'), 1)
        self.assertIn('Elapsed time:', result.stderr)

    def test_quiet_retains_summary_and_timing(self):
        result = self.terminal(('--quiet',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Elapsed time:', result.stdout)
        self.assertEqual(result.stderr, '')

    def test_setup_requires_terminal_before_writes(self):
        before = self.config.read_bytes()
        result = subprocess.run([str(BIN), 'setup'], stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, env=self.env, timeout=5)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('requires terminal', result.stderr)
        self.assertEqual(self.config.read_bytes(), before)

    def test_interrupt_reports_130_and_elapsed(self):
        self.status('pending')
        master, slave = pty.openpty()
        process = subprocess.Popen([str(BIN), 'setup', '--wait-timeout', '60'], stdin=slave, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, env=self.env, start_new_session=True)
        try:
            time.sleep(.5)
            os.killpg(process.pid, signal.SIGINT)
            out, err = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 130, err)
            self.assertEqual(out, '')
            self.assertIn('Setup stopped at: Waiting for zone activation', err)
            self.assertIn('Elapsed time:', err)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            os.close(master)
            os.close(slave)

    def test_short_activation_wait_is_bounded(self):
        self.status('pending')
        started = time.monotonic()
        result = self.terminal(('--wait-timeout', '1'))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('after 1s', result.stderr)
        self.assertLess(time.monotonic() - started, 3.5)


if __name__ == '__main__':
    unittest.main()
