#!/usr/bin/env python3
"""Offline CLI subprocess contracts. Credentials and providers are synthetic."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'CLOUDFLARE_API_TOKEN', 'GDDY_ENV', 'GDDY_PAT',
        'CF_ZONE_ID', 'CF_ACCOUNT_ID', 'DRY_RUN', 'ENV_FILE', 'NO_COLOR')
FIXTURE = "DOMAIN=example.com\nDEST_EMAIL=owner@example.net\nADDRESSES=hello,contact\nCLOUDFLARE_API_TOKEN=synthetic-token\nGDDY_ENV=ote\n"

class CLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.config = self.directory / 'private config.env'
        self.config.write_text(FIXTURE)
        self.config.chmod(0o600)
        self.mock = self.directory / 'bin'
        self.mock.mkdir()
        self.calls = self.directory / 'calls'
        self.env = {k: v for k, v in os.environ.items() if k not in KEYS and not k.startswith('CMAIL_')}
        self.env['PATH'] = str(self.mock) + os.pathsep + self.env['PATH']
        self.env['ENV_FILE'] = str(self.config)
        self.env['TEST_CALLS'] = str(self.calls)
        self.shell = os.environ.get('CMAIL_TEST_BASH', 'bash')
        self.tool('gddy', "printf '%s\\n' '{\"data\":[{\"env\":\"ote\",\"expired\":false}]}'")
        self.tool('curl', 'printf "curl\\n" >> "$TEST_CALLS"; exit 99')

    def tool(self, name, body):
        path = self.mock / name
        path.write_text('#!/usr/bin/env bash\nset -euo pipefail\n' + body + '\n')
        path.chmod(0o700)

    def invoke(self, *args, env=None, input=None):
        settings = dict(self.env)
        settings.update(env or {})
        return subprocess.run([self.shell, str(ROOT / 'cmail'), *args], text=True,
                              input=input, capture_output=True, env=settings, timeout=5)

    def test_help_every_level(self):
        commands = [(), ('setup',), ('status',), ('doctor',), ('send-as',), ('config',),
                    ('completion',), ('help',)] + [('config', name) for name in ('init','show','check','set','path')]
        for command in commands:
            with self.subTest(command=command):
                result = self.invoke(*command, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Usage:', result.stdout)
                self.assertEqual(result.stderr, '')

    def test_help_command_path(self):
        self.assertEqual(self.invoke('help', 'config', 'set').stdout,
                         self.invoke('config', 'set', '--help').stdout)

    def test_no_command_help(self):
        self.assertIn('Start here:', self.invoke().stdout)

    def test_version_without_config(self):
        result = self.invoke('--version', env={'ENV_FILE': '/does/not/exist'})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'cmail ' + (ROOT / 'VERSION').read_text().strip() + '\n')

    def test_help_never_loads_config(self):
        sentinel = self.directory / 'executed'
        self.config.write_text(f'touch {sentinel}\n')
        self.assertEqual(self.invoke('setup', '--help').returncode, 0)
        self.assertFalse(sentinel.exists())

    def test_usage_errors_stderr_only(self):
        cases = [('typo',), ('status','extra'), ('setup','--wat'), ('--format','csv','status'),
                 ('--timeout','0','status'), ('--timeout','status'), ('doctor','--wait-timeout','1200'),
                 ('status','--offline'), ('status','--dry-run'), ('status','--stdin'),
                 ('-v','-q','status'), ('--quiet=yes','status'), ('completion','powershell'),
                 ('config','wat'), ('config','set','DOMAIN')]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertIn('cmail:', result.stderr)
        self.assertFalse(self.calls.exists())

    def test_config_path_has_no_side_effects(self):
        target = self.directory / 'absent'
        result = self.invoke('config','path','--config',str(target))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), str(target))
        self.assertFalse(target.exists())

    def test_global_options_on_either_side(self):
        first = self.invoke('--config',str(self.config),'config','path')
        second = self.invoke('config','--config='+str(self.config),'path')
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.returncode, 0)

    def test_offline_doctor_is_read_only(self):
        before = self.config.stat()
        result = self.invoke('doctor','--offline')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('configuration ready', result.stdout)
        after = self.config.stat()
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
        self.assertEqual(before.st_mode, after.st_mode)
        self.assertFalse(self.calls.exists())

    def test_missing_config_not_created_by_doctor(self):
        target = self.directory / 'absent'
        result = self.invoke('doctor','--offline','--config',str(target))
        self.assertEqual(result.returncode, 3)
        self.assertFalse(target.exists())
        self.assertFalse(self.calls.exists())

    def test_doctor_refuses_executable_config(self):
        sentinel = self.directory / 'executed'
        self.config.write_text(f'DOMAIN=$(touch {sentinel})\n')
        result = self.invoke('doctor','--offline')
        self.assertEqual(result.returncode, 3)
        self.assertFalse(sentinel.exists())
        self.assertNotIn('synthetic-token', result.stdout + result.stderr)

    def test_doctor_does_not_repair_permissions(self):
        self.config.chmod(0o644)
        result = self.invoke('doctor','--offline')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o644)

if __name__ == '__main__':
    unittest.main()
