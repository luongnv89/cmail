#!/usr/bin/env python3
"""Timing and terminal contracts; setup orchestration uses fixture providers."""
import os
from pathlib import Path
import pty
import re
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Timing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.shell = os.environ.get('CMAIL_TEST_BASH', 'bash')
        self.env = {k:v for k,v in os.environ.items() if not k.startswith('CMAIL_') and k not in
                    ('DOMAIN','DEST_EMAIL','ADDRESSES','CF_ZONE_ID','CF_ACCOUNT_ID','GDDY_PAT',
                     'CLOUDFLARE_API_TOKEN','DRY_RUN','ENV_FILE','GDDY_ENV','NO_COLOR')}
        shutil.copy(ROOT/'cmail',self.directory/'cmail')
        shutil.copy(ROOT/'VERSION',self.directory/'VERSION')
        shutil.copy(ROOT/'.env.example',self.directory/'.env.example')
        shutil.copytree(ROOT/'lib',self.directory/'lib')
        self.config=self.directory/'config'
        self.config.write_text('DOMAIN=example.com\nDEST_EMAIL=owner@example.net\nADDRESSES=hello,contact\nCLOUDFLARE_API_TOKEN=synthetic-token\nGDDY_ENV=ote\n')
        self.config.chmod(0o600)
        self.env['ENV_FILE']=str(self.config)
        (self.directory/'lib/deps.sh').write_text('ensure_deps() { :; }\n')
        (self.directory/'lib/godaddy.sh').write_text('gddy_ensure_auth() { :; }\ngddy_pick_domain() { :; }\ngddy_set_nameservers() { :; }\n')
        (self.directory/'lib/cloudflare.sh').write_text('''cf_ensure_token() { :; }
cf_zone_ensure() { CF_ZONE_ID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; CF_NS=(alice bob); }
cf_zone_wait_active() { step "Waiting for zone activation"; sleep "${TEST_SLEEP:-1}"; [ "${TEST_FAIL:-0}" = 0 ] || return 7; }
cf_email_enable() { :; }
cf_dest_ensure() { :; }
cf_rules_ensure() { :; }
''')

    def terminal(self, args=(), env=None):
        master,slave=pty.openpty()
        try:
            result=subprocess.run([self.shell,str(self.directory/'cmail'),'setup',*args],stdin=slave,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(self.env,**(env or {})),timeout=5)
            return result
        finally:
            os.close(master); os.close(slave)

    def test_success_includes_elapsed_and_addresses(self):
        result=self.terminal()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('hello@example.com -> owner@example.net',result.stdout)
        self.assertIn('contact@example.com -> owner@example.net',result.stdout)
        seconds=int(re.search(r'\((\d+) seconds\)',result.stdout).group(1))
        self.assertGreaterEqual(seconds,1)
        self.assertIn('DIFFERENT mailbox',result.stdout)
        self.assertNotIn('synthetic-token',result.stdout+result.stderr)

    def test_failure_includes_elapsed_and_runtime_exit_code(self):
        result=self.terminal(env={'TEST_FAIL':'1'})
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual(result.stdout,'')
        self.assertEqual(result.stderr.count('Setup stopped at:'),1)
        self.assertIn('Elapsed time:',result.stderr)

    def test_quiet_retains_summary_and_timing(self):
        result=self.terminal(('--quiet',),{'TEST_SLEEP':'0'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Elapsed time:',result.stdout)
        self.assertEqual(result.stderr,'')

    def test_setup_requires_terminal_before_writes(self):
        before=self.config.read_bytes()
        result=subprocess.run([self.shell,str(self.directory/'cmail'),'setup'],stdin=subprocess.DEVNULL,
            capture_output=True,text=True,env=self.env,timeout=3)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('requires terminal',result.stderr)
        self.assertEqual(self.config.read_bytes(),before)

    def test_interrupt_reports_130_and_elapsed(self):
        master,slave=pty.openpty()
        try:
            process=subprocess.Popen([self.shell,str(self.directory/'cmail'),'setup'],stdin=slave,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                env=dict(self.env,TEST_SLEEP='10'),start_new_session=True)
            time.sleep(.25)
            os.killpg(process.pid,signal.SIGINT)
            out,err=process.communicate(timeout=3)
            self.assertEqual(process.returncode,130,err)
            self.assertEqual(out,'')
            self.assertIn('Elapsed time:',err)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL); process.wait()
            os.close(master); os.close(slave)

    def test_short_activation_wait_is_bounded(self):
        script='''set -euo pipefail
. "$1/lib/ui.sh"
. "$1/lib/cloudflare.sh"
cf_routing_request() { printf '%s\\n' '{"success":true,"result":{"status":"pending"}}'; }
CMAIL_WAIT_TIMEOUT=1
cf_zone_wait_active test-zone
'''
        started=time.monotonic()
        result=subprocess.run([self.shell,'-c',script,'probe',str(ROOT)],env=self.env,
                              text=True,capture_output=True,timeout=3)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('after 1s',result.stderr)
        self.assertLess(time.monotonic()-started,2.5)

    def test_elapsed_format(self):
        script='. "$1/lib/output.sh"; output_elapsed 134'
        result=subprocess.run([self.shell,'-c',script,'probe',str(ROOT)],text=True,capture_output=True)
        self.assertEqual(result.stdout,'2m 14s (134 seconds)')

if __name__ == '__main__':
    unittest.main()
