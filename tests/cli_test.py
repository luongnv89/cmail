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

    def cloudflare(self):
        self.zone = 'a' * 32
        self.account = 'b' * 32
        self.fixtures = {
            '/user/tokens/verify': {'success': True, 'result': {'status': 'active'}},
            '/zones?name=example.com': {'success': True, 'result': [{'id': self.zone, 'name':'example.com'}]},
            '/zones/'+self.zone: {'success': True, 'result': {'id':self.zone, 'name':'example.com', 'status':'active',
                    'account':{'id':self.account}, 'name_servers':['alice.ns.cloudflare.com','bob.ns.cloudflare.com']}},
            '/zones/'+self.zone+'/email/routing': {'success': True, 'result': {'enabled':True,'status':'ready'}},
            '/accounts/'+self.account+'/email/routing/addresses?per_page=50&page=1': {
                    'success':True,'result':[{'email':'owner@example.net','verified':'2026-01-01T00:00:00Z'}]},
            '/zones/'+self.zone+'/email/routing/rules': {'success':True,'result':[]},
        }
        self.fixture_file = self.directory / 'responses.json'
        self.save_responses()
        script = ROOT / 'tests' / 'mock_curl.py'
        self.tool('curl', 'exec '+str(__import__('sys').executable)+' '+str(script)+' "$@"')
        self.env['TEST_RESPONSES'] = str(self.fixture_file)
        self.tool('gddy', r'''printf 'gddy %s\n' "$1 $2" >> "$TEST_CALLS"
case "$1 $2" in
  'auth status') printf '%s\n' '{"data":[{"env":"ote","expired":false}]}' ;;
  'domain get') printf '%s\n' '{"data":{"nameServers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com"]}}' ;;
  *) exit 99 ;;
esac''')

    def save_responses(self):
        self.fixture_file.write_text(json.dumps(self.fixtures))

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

    def test_offline_doctor_json(self):
        result = self.invoke('doctor', '--offline', '--format=json')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['schema_version'], 1)
        self.assertEqual(data['command'], 'doctor')
        self.assertTrue(all(item['state']=='pass' for item in data['data']['checks']))
        self.assertNotIn('synthetic-token', result.stdout+result.stderr)

    def test_diagnostic_json_survives_input_error(self):
        self.config.write_text('DOMAIN=invalid/domain\n')
        result = self.invoke('doctor', '--offline', '--format=json')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)['data']['checks'][-1]['state'], 'fail')

    def test_ui_streams_quiet_and_color(self):
        script = '. "$1/lib/ui.sh"; log progress; ok ready; warn attention; note detail; step phase'
        for quiet in ('0', '1'):
            env=dict(self.env, CMAIL_QUIET=quiet, NO_COLOR='')
            result=subprocess.run([self.shell,'-c',script,'probe',str(ROOT)], env=env,
                                  text=True,capture_output=True)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout,'')
            self.assertIn('attention',result.stderr)
            self.assertNotIn('\x1b',result.stderr)
            self.assertEqual('progress' in result.stderr,quiet=='0')

    def test_no_browser_keeps_manual_url(self):
        script='. "$1/lib/ui.sh"; open_url https://example.com/'
        self.tool('open', 'printf "browser\\n" >> "$TEST_CALLS"; exit 99')
        result=subprocess.run([self.shell,'-c',script,'probe',str(ROOT)],
                              env=dict(self.env,CMAIL_NO_BROWSER='1',CMAIL_QUIET='1'),
                              text=True,capture_output=True)
        self.assertEqual(result.returncode,0)
        self.assertIn('https://example.com/',result.stderr)
        self.assertFalse(self.calls.exists())

    def test_status_json_and_text(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules']['result'] = [
            {'id':'rule-1','enabled':True,'matchers':[{'field':'to','type':'literal','value':'hello@example.com'}],
             'actions':[{'type':'forward','value':['owner@example.net']}]}]
        self.save_responses()
        for fmt in ('text','json'):
            result=self.invoke('status','--format',fmt)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('owner@example.net',result.stdout)
            if fmt=='json':
                data=json.loads(result.stdout)
                self.assertEqual(data['command'],'status')
                self.assertEqual(data['data']['zone']['name'],'example.com')
                self.assertEqual(len(data['data']['rules']),1)
            self.assertNotIn('synthetic-token',result.stdout+result.stderr)
        self.assertNotIn('POST',self.calls.read_text())

    def test_status_late_failure_has_no_partial_stdout(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules']={
            'success':False,'errors':[{'message':'denied synthetic-token'}], '_status':403}
        self.save_responses()
        result=self.invoke('status','--format=json')
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,'')
        self.assertIn('HTTP 403',result.stderr)
        self.assertNotIn('synthetic-token',result.stderr)

    def test_status_refuses_wrong_zone(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone]['result']['name']='wrong.example'
        self.save_responses()
        result=self.invoke('status')
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,'')

    def test_status_rule_pagination(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules']['result_info']={'total_pages':2}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=2']={
            'success':True,'result':[{'id':'second-page','enabled':False,'matchers':[],'actions':[]}],
            'result_info':{'total_pages':2}}
        self.save_responses()
        result=self.invoke('status','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['rules'][0]['id'],'second-page')

    def test_online_doctor_and_timeouts(self):
        self.cloudflare()
        result=self.invoke('doctor','--format=json','--timeout=7')
        self.assertEqual(result.returncode,0,result.stderr)
        checks=json.loads(result.stdout)['data']['checks']
        self.assertEqual(checks[-1]['state'],'pass')
        self.assertIn('max-time=7',self.calls.read_text())

    def test_verbose_status_diagnostics_stderr(self):
        self.cloudflare()
        result=self.invoke('status','--verbose','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        json.loads(result.stdout)
        self.assertIn('Request: Cloudflare GET',result.stderr)
        self.assertNotIn('synthetic-token',result.stderr)

    def test_full_dry_run_never_writes(self):
        self.cloudflare()
        before=self.config.read_bytes()
        result=self.invoke('setup','--dry-run','--format=json', env={'GDDY_PAT':'synthetic-pat'})
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)['data']
        self.assertTrue(data['dry_run'])
        self.assertEqual(data['blockers'],[])
        self.assertIsInstance(data['elapsed_seconds'],int)
        self.assertEqual(self.config.read_bytes(),before)
        calls=self.calls.read_text()
        self.assertNotIn('POST',calls)
        self.assertNotIn('purchase',calls)
        self.assertNotIn('auth login',calls)
        self.assertNotIn('synthetic-pat',result.stdout+result.stderr)

    def test_legacy_dry_run_is_complete_preview(self):
        self.cloudflare()
        result=self.invoke('setup','--format=json',env={'DRY_RUN':'1','GDDY_PAT':'synthetic-pat'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['data']['dry_run'])
        self.assertNotIn('POST',self.calls.read_text())

    def test_preview_missing_zone_and_account_never_creates(self):
        self.cloudflare()
        self.fixtures['/zones?name=example.com']['result']=[]
        self.fixtures['/accounts']={'success':True,'result':[]}
        self.save_responses()
        result=self.invoke('setup','--dry-run','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['data']['blockers'])
        self.assertNotIn('POST',self.calls.read_text())
        self.assertNotIn('gddy',self.calls.read_text())

    def test_preview_conflicting_rule_is_blocker(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules']['result']=[
            {'enabled':False,'matchers':[{'value':'hello@example.com'}],'actions':[]}]
        self.save_responses()
        result=self.invoke('setup','--dry-run','--format=json',env={'GDDY_PAT':'synthetic-pat'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['data']['blockers'])
        self.assertNotIn('POST',self.calls.read_text())

    def test_send_as_requires_terminal_without_writes(self):
        before=self.config.read_bytes()
        result=self.invoke('send-as')
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('requires terminal',result.stderr)
        self.assertEqual(before,self.config.read_bytes())
        self.assertFalse(self.calls.exists())

    def test_existing_rule_on_second_page_is_not_recreated(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules']['result_info']={'total_pages':2}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=2']={
            'success':True,'result':[{'enabled':True,'matchers':[{'type':'literal','field':'to','value':'hello@example.com'}],
                    'actions':[{'type':'forward','value':['owner@example.net']}]}],
            'result_info':{'total_pages':2}}
        self.save_responses()
        script='set -euo pipefail; CMAIL_DIR="$1"; . "$1/lib/ui.sh"; . "$1/lib/env.sh"; . "$1/lib/cloudflare.sh"; config_load; ADDRESSES=hello; cf_rules_ensure "$2"'
        result=subprocess.run([self.shell,'-c',script,'probe',str(ROOT),self.zone],env=self.env,
                              text=True,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('POST',self.calls.read_text())

if __name__ == '__main__':
    unittest.main()
