#!/usr/bin/env python3
"""Offline CLI subprocess contracts. Credentials and providers are synthetic."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_server import FixtureServer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# The binary under test; scripts/test.sh builds it and exports CMAIL_BIN.
BIN = Path(os.environ.get('CMAIL_BIN', ROOT / 'target' / 'debug' / 'cmail'))
KEYS = ('DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'CLOUDFLARE_API_TOKEN', 'REGISTRAR', 'GDDY_ENV', 'GDDY_PAT',
        'CF_ZONE_ID', 'CF_ACCOUNT_ID', 'DRY_RUN', 'ENV_FILE', 'NO_COLOR', 'FORCE_COLOR', 'CLICOLOR_FORCE',
        'COLORTERM', 'COLUMNS', 'LC_ALL', 'LC_CTYPE', 'XDG_CONFIG_HOME')
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
        self.env['TERM'] = 'xterm-256color'
        self.env['LANG'] = 'C.UTF-8'
        # No fixture server unless a test calls cloudflare(): any API call fails fast.
        self.env['CMAIL_CF_API'] = 'http://127.0.0.1:9/client/v4'
        self.tool('gddy', "printf '%s\\n' '{\"data\":[{\"env\":\"ote\",\"expired\":false}]}'")

    def tool(self, name, body):
        path = self.mock / name
        path.write_text('#!/usr/bin/env bash\nset -euo pipefail\n' + body + '\n')
        path.chmod(0o700)

    def invoke(self, *args, env=None, input=None):
        settings = dict(self.env)
        settings.update(env or {})
        return subprocess.run([str(BIN), *args], text=True,
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
            '/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1': {'success':True,'result':[]},
        }
        self.fixture_file = self.directory / 'responses.json'
        self.save_responses()
        self.server = FixtureServer(str(self.fixture_file), str(self.calls))
        self.addCleanup(self.server.close)
        self.env['CMAIL_CF_API'] = self.server.url
        self.tool('gddy', r'''printf 'gddy %s\n' "$1 $2" >> "$TEST_CALLS"
case "$1 $2" in
  'auth status') printf '%s\n' '{"data":[{"env":"ote","expired":false}]}' ;;
  'domain get') printf '%s\n' '{"data":{"nameServers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com"]}}' ;;
  *) exit 99 ;;
esac''')

    def save_responses(self):
        self.fixture_file.write_text(json.dumps(self.fixtures))

    def test_help_every_level(self):
        commands = [(), ('setup',), ('status',), ('list',), ('forward',), ('doctor',), ('send-as',), ('config',),
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
                 ('config','wat'), ('config','set','DOMAIN'), ('setup','--registrar','namecheap'),
                 ('setup','--registrar='), ('setup','--registrar'), ('status','--registrar','manual'),
                 ('doctor','--registrar=godaddy'), ('status','--domain','example.org'), ('list','extra'),
                 ('list','--registrar','manual'), ('list','--destination','a@example.net'), ('list','--dry-run'),
                 ('list','--domain='), ('status','--destination','a@example.net'),
                 ('forward','hello'), ('forward','--destination','a@example.net'),
                 ('forward','hello','extra','--destination','a@example.net'),
                 ('forward','hello','--destination','a@example.net','--format','json'),
                 ('forward','hello','--destination','a@example.net','--dry-run'),
                 ('forward','hello','--destination','a@example.net','--addresses','hello'),
                 ('forward','hello','--destination','a@example.net','--wait-timeout','5'),
                 ('forward','hello','--destination','a@example.net','--registrar','manual')]
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

    def styled_status(self, env):
        self.cloudflare()
        return self.invoke('status', env=env)

    def test_piped_output_is_plain(self):
        result=self.styled_status({})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('\x1b',result.stdout)
        self.assertNotIn('╭',result.stdout)

    def test_json_never_styled_even_when_forced(self):
        self.cloudflare()
        result=self.invoke('status','--format=json',env={'FORCE_COLOR':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        json.loads(result.stdout)
        self.assertNotIn('\x1b',result.stdout)

    def test_no_color_wins_over_force_color(self):
        for env,args in (({'FORCE_COLOR':'1','NO_COLOR':'1'},()),({'FORCE_COLOR':'1'},('--no-color',))):
            with self.subTest(env=env):
                self.cloudflare()
                result=self.invoke('status',*args,env=env)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertNotIn('\x1b',result.stdout)
                self.assertIn('╭─┐',result.stdout)

    def test_forced_color_styles_box(self):
        result=self.styled_status({'FORCE_COLOR':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('\x1b[',result.stdout)
        self.assertIn('╭─┐',result.stdout)

    def test_ascii_locale_draws_ascii_box(self):
        result=self.styled_status({'FORCE_COLOR':'1','LANG':'C','NO_COLOR':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(all(ord(c)<0x80 for c in result.stdout),result.stdout)
        self.assertIn('+-[example.com]',result.stdout)

    def test_hostile_provider_text_is_escaped(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result']=[
            {'id':'r','enabled':True,'matchers':[{'type':'literal','field':'to','value':'evil\x1b[2J\there@example.com'}],
             'actions':[{'type':'forward','value':['owner@example.net']}]}]
        self.save_responses()
        for env in ({},{'FORCE_COLOR':'1','NO_COLOR':'1'}):
            result=self.invoke('status',env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('\x1b',result.stdout)
        rule=[l for l in self.invoke('status').stdout.splitlines() if l.startswith('rule')][0]
        self.assertEqual(len(rule.split('\t')),4,rule)

    def test_quiet_keeps_errors_and_results(self):
        result=self.invoke('doctor','--offline','--quiet')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('configuration ready',result.stdout)
        self.assertEqual(result.stderr,'')

    def test_no_browser_keeps_manual_url(self):
        self.cloudflare()
        self.config.write_text(FIXTURE.replace('CLOUDFLARE_API_TOKEN=synthetic-token\n',''))
        for opener in ('open','xdg-open','wslview'):
            self.tool(opener, 'printf "browser\\n" >> "$TEST_CALLS"; exit 99')
        result=self.tty_run('setup','--no-browser',answer='\x04',env={'PATH':self.without_gddy()})
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('Open: https://dash.cloudflare.com/profile/api-tokens',result.stderr)
        self.assertIn('no token input',result.stderr)
        self.assertNotIn('browser',self.calls.read_text() if self.calls.exists() else '')

    def test_status_json_and_text(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result'] = [
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

    def test_status_text_handles_non_forward_rules(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result'] = [
            {'id':'rule-1','enabled':True,'matchers':[{'field':'to','type':'literal','value':'hello@example.com'}],
             'actions':[{'type':'forward','value':['owner@example.net','second@example.org']}]},
            {'id':'rule-2','enabled':True,'matchers':[{'field':'to','type':'literal','value':'bot@example.com'}],
             'actions':[{'type':'worker','value':['parser']}]},
            {'id':'rule-3','enabled':True,'matchers':[{'field':'to','type':'literal','value':'spam@example.com'}],
             'actions':[{'type':'drop'}]},
            {'id':'rule-4','enabled':False,'matchers':[],'actions':[]},
            {'id':'catch-all','enabled':False,'matchers':[{'type':'all'}],'actions':[{'type':'drop'}]}]
        self.save_responses()
        result=self.invoke('status')
        self.assertEqual(result.returncode,0,result.stderr)
        for line in ['rule\thello@example.com\towner@example.net, second@example.org\tenabled',
                     'rule\tbot@example.com\tworker parser\tenabled',
                     'rule\tspam@example.com\tdrop\tenabled',
                     'rule\tcustom matcher\tno action\tdisabled',
                     'rule\tcatch-all\tdrop\tdisabled',
                     'zone\texample.com\tactive', 'routing\tready\tenabled',
                     'destination\towner@example.net\tverified']:
            self.assertIn(line,result.stdout.splitlines())

    def test_status_late_failure_has_no_partial_stdout(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']={
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
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result_info']={'total_pages':2}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=2']={
            'success':True,'result':[{'id':'second-page','enabled':False,'matchers':[],'actions':[]}],
            'result_info':{'total_pages':2}}
        self.save_responses()
        result=self.invoke('status','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['rules'][0]['id'],'second-page')

    def test_status_rule_pagination_full_first_page(self):
        self.cloudflare()
        rule=lambda i:{'id':'rule-%d'%i,'enabled':True,'matchers':[],'actions':[]}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']={
            'success':True,'result':[rule(i) for i in range(50)]}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=2']={
            'success':True,'result':[rule(50)]}
        self.save_responses()
        result=self.invoke('status','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        rules=json.loads(result.stdout)['data']['rules']
        self.assertEqual([r['id'] for r in rules],['rule-%d'%i for i in range(51)])
        self.assertIn('/email/routing/rules?per_page=50&page=1',self.calls.read_text())

    def without_gddy(self):
        (self.mock/'gddy').unlink()
        return os.pathsep.join(d for d in self.env['PATH'].split(os.pathsep)
                               if d and not os.path.exists(os.path.join(d,'gddy')))

    def test_doctor_reports_missing_gddy_binary(self):
        path=self.without_gddy()
        result=self.invoke('doctor','--offline','--format=json',env={'PATH':path,'REGISTRAR':'godaddy'})
        checks={c['name']:c['state'] for c in json.loads(result.stdout)['data']['checks']}
        self.assertEqual(checks['gddy'],'fail',result.stdout)
        self.assertEqual(result.returncode,1,result.stderr)

    def test_doctor_godaddy_mode_from_config_requires_gddy(self):
        path=self.without_gddy()
        self.config.write_text(FIXTURE+'REGISTRAR=godaddy\n')
        result=self.invoke('doctor','--offline',env={'PATH':path})
        self.assertEqual(result.returncode,1,result.stdout)
        self.assertIn('gddy missing',result.stdout)

    def test_doctor_manual_mode_never_requires_gddy(self):
        path=self.without_gddy()
        for extra in ('','REGISTRAR=manual\n'):
            with self.subTest(extra=extra):
                self.config.write_text(FIXTURE+extra)
                result=self.invoke('doctor','--offline','--format=json',env={'PATH':path})
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                checks={c['name']:c['state'] for c in json.loads(result.stdout)['data']['checks']}
                self.assertNotIn('gddy',checks)
                self.assertEqual(checks['registrar'],'pass')
                self.assertTrue(all(state=='pass' for state in checks.values()),checks)
        self.assertFalse(self.calls.exists())

    def test_online_doctor_and_timeouts(self):
        self.cloudflare()
        result=self.invoke('doctor','--format=json','--timeout=7',env={'REGISTRAR':'godaddy'})
        self.assertEqual(result.returncode,0,result.stderr)
        checks=json.loads(result.stdout)['data']['checks']
        self.assertEqual(checks[-1]['state'],'pass')
        self.assertEqual(checks[-1]['name'],'godaddy')
        self.assertIn('GET /user/tokens/verify',self.calls.read_text())
        result=self.invoke('status','--format=json','--timeout=7','--verbose')
        self.assertIn('(timeout 7s)',result.stderr)
        self.assertIn('gddy auth status',self.calls.read_text())

    def test_online_doctor_manual_mode_skips_godaddy(self):
        self.cloudflare()
        result=self.invoke('doctor','--format=json',env={'PATH':self.without_gddy()})
        self.assertEqual(result.returncode,0,result.stderr)
        checks={c['name']:c['state'] for c in json.loads(result.stdout)['data']['checks']}
        self.assertEqual(checks['cloudflare'],'pass')
        self.assertNotIn('godaddy',checks)
        self.assertNotIn('gddy',self.calls.read_text())

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
        result=self.invoke('setup','--dry-run','--format=json', env={'GDDY_PAT':'synthetic-pat','REGISTRAR':'godaddy'})
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)['data']
        self.assertTrue(data['dry_run'])
        self.assertEqual(data['registrar'],'godaddy')
        self.assertIn('gddy domain get',self.calls.read_text())
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
        result=self.invoke('setup','--format=json',env={'DRY_RUN':'1','GDDY_PAT':'synthetic-pat','REGISTRAR':'godaddy'})
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
        data=json.loads(result.stdout)['data']
        self.assertTrue(data['blockers'])
        actions={a['name']:a for a in data['actions']}
        self.assertEqual(actions['nameservers']['state'],'manual')
        self.assertIn('prints the nameservers to set at your registrar',actions['nameservers']['message'])
        self.assertNotIn('POST',self.calls.read_text())
        self.assertNotIn('gddy',self.calls.read_text())

    def manual_preview(self, *args, env=None):
        result=self.invoke('setup','--dry-run','--format=json',*args,env=dict({'PATH':self.without_gddy()},**(env or {})))
        self.assertEqual(result.returncode,0,result.stderr)
        calls=self.calls.read_text()
        self.assertNotIn('gddy',calls)
        self.assertNotIn('POST',calls)
        data=json.loads(result.stdout)['data']
        return data,{a['name']:a for a in data['actions']}

    def test_manual_preview_active_zone_needs_no_registrar(self):
        self.cloudflare()
        data,actions=self.manual_preview()
        self.assertEqual(data['registrar'],'manual')
        self.assertEqual(data['blockers'],[])
        self.assertNotIn('godaddy',actions)
        self.assertEqual(actions['registrar']['state'],'ready')
        self.assertEqual(actions['nameservers']['state'],'ready')
        self.assertIn('no registrar change needed',actions['nameservers']['message'])
        self.assertNotIn('GoDaddy',json.dumps(data['blockers']))

    def test_manual_preview_pending_zone_lists_nameservers(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone]['result']['status']='pending'
        self.save_responses()
        data,actions=self.manual_preview('--registrar','manual',env={'REGISTRAR':'godaddy'})
        self.assertEqual(data['registrar'],'manual')
        self.assertEqual(data['blockers'],[])
        self.assertEqual(actions['nameservers']['state'],'manual')
        self.assertIn('alice.ns.cloudflare.com, bob.ns.cloudflare.com',actions['nameservers']['message'])
        self.assertIn('Update nameservers at your registrar',actions['nameservers']['next'])
        self.assertEqual(actions['activation']['state'],'wait')

    def test_godaddy_preview_is_opt_in_via_option(self):
        self.cloudflare()
        result=self.invoke('setup','--dry-run','--format=json','--registrar=godaddy')
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)['data']
        self.assertEqual(data['registrar'],'godaddy')
        self.assertTrue(any('GoDaddy' in b for b in data['blockers']))

    def tty_setup(self, *args, env=None):
        settings=dict(self.env); settings.update(env or {})
        return subprocess.run([sys.executable,str(ROOT/'tests'/'run_tty.py'),str(BIN),'setup',*args],
                              text=True,capture_output=True,env=settings,timeout=15)

    def ready_rules(self):
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result']=[
            {'id':'r-'+a,'enabled':True,'matchers':[{'type':'literal','field':'to','value':a+'@example.com'}],
             'actions':[{'type':'forward','value':['owner@example.net']}]} for a in ('hello','contact')]
        self.save_responses()

    def test_manual_setup_active_zone_without_gddy(self):
        self.cloudflare()
        self.ready_rules()
        result=self.tty_setup(env={'PATH':self.without_gddy()})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Receiving is set up',result.stdout)
        self.assertIn('no registrar changes needed',result.stderr)
        self.assertNotIn('GoDaddy',result.stderr)
        self.assertNotIn('replace ALL nameservers',result.stderr)
        calls=self.calls.read_text()
        self.assertNotIn('gddy',calls)
        self.assertNotIn('POST',calls)
        self.assertNotIn('synthetic-token',result.stdout+result.stderr)
        self.assertIn("CF_ZONE_ID='"+self.zone+"'",self.config.read_text())
        self.assertNotIn('REGISTRAR',self.config.read_text())

    def test_manual_setup_pending_zone_prints_nameservers_and_polls(self):
        self.cloudflare()
        self.ready_rules()
        zone=self.fixtures['/zones/'+self.zone]
        pending=json.loads(json.dumps(zone)); pending['result']['status']='pending'
        # zone lookup, delegation step, first activation poll: pending; then active.
        self.fixtures['/zones/'+self.zone]={'_sequence':[pending,pending,pending,zone]}
        self.save_responses()
        self.env['CMAIL_TEST_SLEEP_LOG']=str(self.calls)
        result=self.tty_setup('--registrar','manual',env={'PATH':self.without_gddy(),'REGISTRAR':'godaddy'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Receiving is set up',result.stdout)
        for text in ('Registrar nameservers: example.com','alice.ns.cloudflare.com','bob.ns.cloudflare.com',
                     'replace ALL nameservers','DNSSEC','Copy every DNS record','status: pending','zone active'):
            self.assertIn(text,result.stderr)
        self.assertLess(result.stderr.index('replace ALL nameservers'),result.stderr.index('zone active'))
        calls=self.calls.read_text()
        self.assertNotIn('gddy',calls)
        self.assertIn('sleep 20',calls)
        self.assertGreaterEqual(calls.count('GET /zones/'+self.zone+' '),4)
        self.assertIn("REGISTRAR='manual'",self.config.read_text())

    def test_manual_setup_pending_timeout_is_registrar_neutral(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone]['result']['status']='pending'
        self.save_responses()
        self.env['CMAIL_TEST_SLEEP_LOG']=str(self.calls)
        result=self.tty_setup('--wait-timeout','1',env={'PATH':self.without_gddy()})
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('Setup stopped at: Waiting for zone activation',result.stderr)
        self.assertIn('your domain registrar',result.stderr)
        self.assertIn('cmail never changes nameservers in manual registrar mode',result.stderr)
        self.assertNotIn('GoDaddy',result.stderr)
        self.assertNotIn('delegation may already have changed',result.stderr)
        self.assertNotIn('gddy',self.calls.read_text())

    def test_godaddy_setup_option_requires_gddy(self):
        result=self.tty_setup('--registrar','godaddy',env={'PATH':self.without_gddy()})
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('gddy missing',result.stderr)
        self.assertIn('Setup stopped at: Dependencies',result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertNotIn('REGISTRAR',self.config.read_text())

    def test_godaddy_no_browser_guard_is_opt_in(self):
        for registrar,code in (('godaddy',3),('manual',None)):
            with self.subTest(registrar=registrar):
                result=self.tty_setup('--no-browser','--registrar',registrar,'--wait-timeout','1',
                                      env={'PATH':self.without_gddy() if registrar=='manual' else self.env['PATH']})
                if code: self.assertEqual(result.returncode,code,result.stderr)
                self.assertEqual('requires an existing GDDY_PAT' in result.stderr,registrar=='godaddy')

    def test_godaddy_setup_flow_and_persistence(self):
        self.cloudflare()
        self.ready_rules()
        result=self.tty_setup('--registrar','godaddy')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Receiving is set up',result.stdout)
        self.assertIn('GoDaddy authentication (ote)',result.stderr)
        self.assertIn('nameservers already point at Cloudflare',result.stderr)
        self.assertNotIn('Registrar nameservers',result.stderr)
        calls=self.calls.read_text()
        self.assertIn('gddy auth status',calls)
        self.assertIn('gddy domain get',calls)
        self.assertIn("REGISTRAR='godaddy'",self.config.read_text())

    def test_preview_conflicting_rule_is_blocker(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result']=[
            {'enabled':False,'matchers':[{'value':'hello@example.com'}],'actions':[]}]
        self.save_responses()
        result=self.invoke('setup','--dry-run','--format=json',env={'GDDY_PAT':'synthetic-pat','REGISTRAR':'godaddy'})
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
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result_info']={'total_pages':2}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=2']={
            'success':True,'result':[{'enabled':True,'matchers':[{'type':'literal','field':'to','value':'hello@example.com'}],
                    'actions':[{'type':'forward','value':['owner@example.net']}]}],
            'result_info':{'total_pages':2}}
        self.save_responses()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result']=[
            {'enabled':True,'matchers':[{'type':'literal','field':'to','value':'contact@example.com'}],
             'actions':[{'type':'forward','value':['owner@example.net']}]}]
        self.save_responses()
        result=self.tty_setup(env={'PATH':self.without_gddy()})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('hello@example.com already exists',result.stderr)
        self.assertNotIn('POST',self.calls.read_text())

    def test_config_init_private_idempotent(self):
        target=self.directory/'new'/'config'
        result=self.invoke('config','init','--config',str(target))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        self.assertEqual(target.parent.stat().st_mode & 0o777,0o700)
        before=target.read_bytes()
        result=self.invoke('config','init','--config',str(target))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.read_bytes(),before)

    def test_config_show_redacts_and_obeys_precedence(self):
        for fmt in ('text','json'):
            result=self.invoke('config','show','--format',fmt,env={'DOMAIN':'override.example'})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('override.example',result.stdout)
            self.assertNotIn('synthetic-token',result.stdout+result.stderr)
            if fmt=='json':
                self.assertEqual(json.loads(result.stdout)['data']['secrets']['CLOUDFLARE_API_TOKEN'],'set')

    def test_config_show_masks_misplaced_opaque_alias(self):
        result=self.invoke('config','show','--format=json',env={'ADDRESSES':'a'*40})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('a'*40,result.stdout)

    def test_config_check_readiness_and_error_report(self):
        self.assertEqual(self.invoke('config','check').returncode,0)
        result=self.invoke('config','check','--format=json',env={'CLOUDFLARE_API_TOKEN':''})
        self.assertEqual(result.returncode,3)
        self.assertEqual(json.loads(result.stdout)['data']['checks'][0]['state'],'fail')

    def test_config_set_registrar_validation(self):
        for value in ('godaddy','manual'):
            result=self.invoke('config','set','REGISTRAR',value)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(self.invoke('config','show','--format=json').stdout)['data']
            self.assertEqual(data['settings']['REGISTRAR'],value)
            self.assertNotIn('REGISTRAR',data['secrets'])
        before=self.config.read_bytes()
        for value in ('namecheap','GoDaddy','godaddy '):
            with self.subTest(value=value):
                result=self.invoke('config','set','REGISTRAR',value)
                self.assertEqual(result.returncode,3,result.stderr)
                self.assertEqual(self.config.read_bytes(),before)
        self.assertEqual(self.invoke('config','check',env={'REGISTRAR':'namecheap'}).returncode,3)
        self.config.write_text(FIXTURE)
        data=json.loads(self.invoke('config','show','--format=json').stdout)['data']
        self.assertEqual(data['settings']['REGISTRAR'],'manual')
        self.assertIn('REGISTRAR',self.invoke('config','set','--help').stdout)

    def test_config_set_public_and_zone_invalidation(self):
        self.config.write_text(FIXTURE+'CF_ZONE_ID='+('a'*32)+'\n')
        result=self.invoke('config','set','DOMAIN','new.example')
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(self.invoke('config','show','--format=json').stdout)['data']['settings']
        self.assertEqual(data['DOMAIN'],'new.example')
        self.assertEqual(data['CF_ZONE_ID'],'')
        self.assertEqual(self.config.stat().st_mode & 0o777,0o600)

    def test_config_secret_stdin_roundtrip_never_echoes(self):
        value="opaque '$literal"
        result=self.invoke('config','set','GDDY_PAT','--stdin',input=value+'\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn(value,result.stdout+result.stderr)
        result=self.invoke('config','show','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['secrets']['GDDY_PAT'],'set')
        self.assertNotIn(value,result.stdout+result.stderr)

    def test_config_stdin_rejects_controls_and_large_input(self):
        before=self.config.read_bytes()
        for value in ('first\nsecond\n','hello\0world','a'*4097):
            with self.subTest(value=value[:10]):
                result=self.invoke('config','set','GDDY_PAT','--stdin',input=value)
                self.assertEqual(result.returncode,3,result.stderr)
                self.assertEqual(self.config.read_bytes(),before)

    def test_config_stdin_accepts_size_limit_with_optional_newline(self):
        for suffix in ('','\n'):
            result=self.invoke('config','set','GDDY_PAT','--stdin',input='a'*4096+suffix)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_secret_arguments_and_unknown_keys_rejected(self):
        for args in [('GDDY_PAT','never-echo-this'),('UNKNOWN','value')]:
            result=self.invoke('config','set',*args)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertNotIn('never-echo-this',result.stdout+result.stderr)

    def test_config_path_precedence(self):
        chosen=self.directory/'chosen'
        result=self.invoke('config','path',env={'CMAIL_CONFIG':str(chosen)})
        self.assertEqual(result.stdout.strip(),str(chosen))
        result=self.invoke('config','path','--config',str(self.config),env={'CMAIL_CONFIG':str(chosen)})
        self.assertEqual(result.stdout.strip(),str(self.config))

    def list_fixtures(self):
        self.cloudflare()
        rules='/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1'
        literal=lambda value:[{'type':'literal','field':'to','value':value}]
        self.fixtures['/accounts/'+self.account+'/email/routing/addresses?per_page=50&page=1']['result'].append(
            {'email':'pending@example.org','verified':None})
        self.fixtures[rules]['result']=[
            {'id':'r1','name':'fwd hello','enabled':True,'matchers':literal('hello@example.com'),
             'actions':[{'type':'forward','value':['Owner@example.net']}]},
            {'id':'r2','enabled':False,'matchers':literal('contact@example.com'),
             'actions':[{'type':'forward','value':['pending@example.org','ghost@example.io']}]},
            {'id':'r3','enabled':True,'matchers':literal('spam@example.com'),'actions':[{'type':'drop'}]},
            {'id':'r4','enabled':True,'matchers':literal('bot@example.com'),'actions':[{'type':'worker','value':['parser']}]},
            {'id':'ca','enabled':True,'matchers':[{'type':'all'}],'actions':[{'type':'drop'}]}]
        self.fixtures['/zones/'+self.zone+'/email/routing/rules/catch_all']={'success':True,'result':
            {'id':'ca','enabled':False,'matchers':[{'type':'all'}],'actions':[{'type':'forward','value':['owner@example.net']}]}}
        self.save_responses()

    def test_list_json(self):
        self.list_fixtures()
        result=self.invoke('list','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual(data['command'],'list')
        data=data['data']
        self.assertEqual((data['domain'],data['zone_id']),('example.com',self.zone))
        self.assertEqual([a['address'] for a in data['addresses']],
                         ['bot@example.com','contact@example.com','hello@example.com','spam@example.com'])
        contact=data['addresses'][1]
        self.assertFalse(contact['enabled'])
        self.assertEqual(contact['actions'][0]['destinations'],[{'email':'pending@example.org','state':'unverified'},
                                                                {'email':'ghost@example.io','state':'unregistered'}])
        self.assertEqual(data['addresses'][2]['actions'][0]['destinations'][0]['state'],'verified')
        self.assertEqual(data['addresses'][3]['actions'],[{'type':'drop','value':[]}])
        self.assertFalse(data['catch_all']['enabled'])
        self.assertEqual(data['catch_all']['actions'][0]['destinations'][0]['state'],'verified')
        self.assertNotIn('POST',self.calls.read_text())
        self.assertNotIn('synthetic-token',result.stdout+result.stderr)

    def test_list_text(self):
        self.list_fixtures()
        result=self.invoke('list')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,
            'bot@example.com\tworker parser\tenabled\n'
            'contact@example.com\tpending@example.org (unverified), ghost@example.io (unregistered)\tdisabled\n'
            'hello@example.com\tOwner@example.net (verified)\tenabled\n'
            'spam@example.com\tdrop\tenabled\n'
            'catch-all\towner@example.net (verified)\tdisabled\n')
        styled=self.invoke('list',env={'FORCE_COLOR':'1','NO_COLOR':'1','COLUMNS':'200'})
        self.assertIn('example.com addresses',styled.stdout)
        self.assertIn('ghost@example.io (unregistered)',styled.stdout)

    def test_list_empty_domain(self):
        self.cloudflare()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules/catch_all']={'success':True,'result':None}
        self.save_responses()
        result=self.invoke('list')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'catch-all\t\tnot configured\n')

    def test_list_domain_override_uses_zone_lookup(self):
        self.list_fixtures()
        other='c'*32
        self.config.write_text(FIXTURE+'CF_ZONE_ID='+self.zone+'\n')
        self.fixtures['/zones?name=example.org']={'success':True,'result':[{'id':other,'name':'example.org'}]}
        self.fixtures['/zones/'+other]={'success':True,'result':{'id':other,'name':'example.org','status':'active',
                                                                'account':{'id':self.account}}}
        self.fixtures['/zones/'+other+'/email/routing/rules?per_page=50&page=1']={'success':True,'result':[
            {'id':'o1','enabled':True,'matchers':[{'type':'literal','field':'to','value':'sales@example.org'}],
             'actions':[{'type':'forward','value':['owner@example.net']}]}]}
        self.fixtures['/zones/'+other+'/email/routing/rules/catch_all']={'success':True,'result':
            {'enabled':False,'matchers':[{'type':'all'}],'actions':[{'type':'drop'}]}}
        self.save_responses()
        result=self.invoke('list','--domain','Example.ORG','--format','json')
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)['data']
        self.assertEqual((data['domain'],data['zone_id']),('example.org',other))
        self.assertEqual([a['address'] for a in data['addresses']],['sales@example.org'])
        calls=self.calls.read_text()
        self.assertIn('GET /zones?name=example.org',calls)
        self.assertNotIn('/zones/'+self.zone,calls)

    def test_list_rule_pagination(self):
        self.list_fixtures()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=1']['result_info']={'total_pages':2}
        self.fixtures['/zones/'+self.zone+'/email/routing/rules?per_page=50&page=2']={'success':True,'result':[
            {'id':'p2','enabled':True,'matchers':[{'type':'literal','field':'to','value':'apex@example.com'}],
             'actions':[{'type':'forward','value':['owner@example.net']}]}],'result_info':{'total_pages':2}}
        self.save_responses()
        result=self.invoke('list','--format=json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['addresses'][0]['address'],'apex@example.com')

    def test_list_late_failure_has_no_partial_stdout(self):
        self.list_fixtures()
        self.fixtures['/zones/'+self.zone+'/email/routing/rules/catch_all']={
            'success':False,'errors':[{'message':'denied synthetic-token'}],'_status':403}
        self.save_responses()
        result=self.invoke('list')
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,'')
        self.assertIn('HTTP 403',result.stderr)
        self.assertNotIn('synthetic-token',result.stderr)

    def test_list_requires_domain(self):
        self.config.write_text('CLOUDFLARE_API_TOKEN=synthetic-token\n')
        result=self.invoke('list')
        self.assertEqual(result.returncode,3)
        self.assertEqual(result.stdout,'')
        self.assertFalse(self.calls.exists())

    NEW = 'new@example.org'

    def forward_fixtures(self, verified='2026-02-01T00:00:00Z', registered=True):
        self.cloudflare()
        self.rules_path = '/zones/'+self.zone+'/email/routing/rules'
        literal = lambda value: [{'type':'literal','field':'to','value':value}]
        self.rule = {'id':'r1','name':'fwd hello@example.com','enabled':True,'priority':3,
                     'matchers':literal('hello@example.com'),'actions':[{'type':'forward','value':['owner@example.net']}]}
        self.fixtures[self.rules_path+'?per_page=50&page=1']['result'] = [self.rule,
            {'id':'r2','name':'fwd contact@example.com','enabled':True,'priority':4,
             'matchers':literal('contact@example.com'),'actions':[{'type':'forward','value':['owner@example.net']}]}]
        if registered:
            self.fixtures['/accounts/'+self.account+'/email/routing/addresses?per_page=50&page=1']['result'].append(
                {'email':self.NEW,'verified':verified})
        updated = dict(self.rule, actions=[{'type':'forward','value':[self.NEW]}])
        self.fixtures['PUT '+self.rules_path+'/r1'] = {'success':True,'result':updated}
        self.fixtures[self.rules_path+'/r1'] = {'success':True,'result':updated}
        self.fixtures['POST /accounts/'+self.account+'/email/routing/addresses'] = {
            'success':True,'result':{'email':self.NEW,'verified':None}}
        self.payloads = self.directory / 'payloads'
        self.server.payloads = str(self.payloads)
        self.save_responses()

    def tty_forward(self, *args, answer='y\n', env=None):
        return self.tty_run('forward', *args, answer=answer, env=env)

    def tty_run(self, *args, answer='y\n', env=None):
        """Run cmail with terminal stdin fed `answer`; capture both result streams."""
        import pty
        settings = dict(self.env); settings.update(env or {})
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen([str(BIN), *args], stdin=slave,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=settings)
            os.write(master, answer.encode())
            out, err = proc.communicate(timeout=15)
        finally:
            os.close(slave)
            os.close(master)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    def writes(self):
        calls = self.calls.read_text() if self.calls.exists() else ''
        return [line.split(' ')[0]+' '+line.split(' ')[1] for line in calls.splitlines() if not line.startswith('GET ')]

    def sent(self):
        if not self.payloads.exists():
            return []
        return [json.loads(line) for line in self.payloads.read_text().splitlines()]

    def test_forward_verified_destination_updates_rule_and_config(self):
        self.forward_fixtures()
        self.config.write_text(FIXTURE.replace('ADDRESSES=hello,contact', 'ADDRESSES=hello'))
        result = self.tty_forward('hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.writes(), ['PUT '+self.rules_path+'/r1'])
        self.assertEqual(self.sent(), [{'method':'PUT','path':self.rules_path+'/r1','body':{
            'name':'fwd hello@example.com','enabled':True,'priority':3,
            'matchers':[{'type':'literal','field':'to','value':'hello@example.com'}],
            'actions':[{'type':'forward','value':[self.NEW]}]}}])
        calls = self.calls.read_text()
        self.assertGreater(calls.index('GET '+self.rules_path+'/r1 '), calls.index('PUT '+self.rules_path+'/r1 '))
        self.assertIn('hello@example.com: owner@example.net -> new@example.org', result.stderr)
        self.assertIn('hello@example.com now forwards to new@example.org (was owner@example.net)', result.stdout)
        self.assertIn('Test it: from a DIFFERENT mailbox (not new@example.org), send to hello@example.com', result.stdout)
        config = self.config.read_text()
        self.assertIn("DEST_EMAIL='new@example.org'", config)
        self.assertNotIn('owner@example.net', config)
        self.assertIn('ADDRESSES=hello\n', config)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('synthetic-token', result.stdout+result.stderr)

    def test_forward_full_address_and_case_insensitive_match(self):
        self.forward_fixtures()
        self.fixtures['/accounts/'+self.account+'/email/routing/addresses?per_page=50&page=1']['result'][-1]['email'] = 'New@Example.org'
        self.fixtures[self.rules_path+'?per_page=50&page=1']['result'][0]['matchers'][0]['value'] = 'Hello@Example.com'
        self.fixtures[self.rules_path+'/r1']['result']['actions'] = [{'type':'forward','value':['New@Example.org']}]
        self.fixtures[self.rules_path+'/r1']['result']['matchers'][0]['value'] = 'Hello@Example.com'
        self.save_responses()
        result = self.tty_forward('hello@EXAMPLE.com', '--destination', self.NEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.sent()[0]['body']
        self.assertEqual(body['actions'], [{'type':'forward','value':['New@Example.org']}])
        self.assertEqual(body['matchers'][0]['value'], 'Hello@Example.com')

    def test_forward_keeps_dest_email_when_other_addresses_differ(self):
        self.forward_fixtures()
        before = self.config.read_bytes()
        result = self.tty_forward('hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.writes(), ['PUT '+self.rules_path+'/r1'])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn('DEST_EMAIL in the configuration stays owner@example.net because these configured addresses '
                      'forward elsewhere: contact@example.com.',
                      result.stderr)
        self.assertIn('report them as conflicting', result.stderr)

    def test_forward_declined_writes_nothing(self):
        self.forward_fixtures()
        before = self.config.read_bytes()
        result = self.tty_forward('hello', '--destination', self.NEW, answer='n\n')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn('nothing was changed; hello@example.com still forwards to owner@example.net', result.stderr)

    def test_forward_unregistered_destination_registers_and_keeps_rule(self):
        self.forward_fixtures(registered=False)
        before = self.config.read_bytes()
        result = self.tty_forward('hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.writes(), ['POST /accounts/'+self.account+'/email/routing/addresses'])
        self.assertEqual(self.sent()[0]['body'], {'email':self.NEW})
        self.assertEqual(self.config.read_bytes(), before)
        for text in ('Register new@example.org', 'new@example.org registered',
                     'click the Cloudflare verification link', 'check Spam',
                     'rerun: cmail forward hello@example.com --destination new@example.org.',
                     'hello@example.com is unchanged and still forwards to owner@example.net'):
            self.assertIn(text, result.stderr)

    def test_forward_unregistered_destination_declined(self):
        self.forward_fixtures(registered=False)
        result = self.tty_forward('hello', '--destination', self.NEW, answer='n\n')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.writes(), [])
        self.assertIn('still forwards to owner@example.net', result.stderr)

    def test_forward_pending_destination_gives_next_step(self):
        self.forward_fixtures(verified=None)
        before = self.config.read_bytes()
        result = self.tty_forward('hello', '--destination', self.NEW, '--domain', 'example.com')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.config.read_bytes(), before)
        for text in ('new@example.org is registered but not verified yet', 'Destination addresses',
                     'rerun: cmail forward hello@example.com --destination new@example.org --domain example.com.',
                     'hello@example.com is unchanged and still forwards to owner@example.net'):
            self.assertIn(text, result.stderr)

    def test_forward_same_destination_is_noop(self):
        self.forward_fixtures()
        result = self.tty_forward('hello', '--destination', 'OWNER@example.net')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.writes(), [])
        self.assertIn('hello@example.com already forwards to owner@example.net; nothing changed.', result.stdout)

    def test_forward_refuses_missing_or_unsupported_rules(self):
        literal = lambda value: [{'type':'literal','field':'to','value':value}]
        cases = {
            'missing': ([], 'has no forwarding rule'),
            'two rules': ([{'id':'a','enabled':True,'matchers':literal('hello@example.com'),
                            'actions':[{'type':'forward','value':['owner@example.net']}]}]*2, 'Existing rules were not changed'),
            'two destinations': ([{'id':'a','enabled':True,'matchers':literal('hello@example.com'),
                                   'actions':[{'type':'forward','value':['owner@example.net','x@example.net']}]}], 'Existing rules were not changed'),
            'drop action': ([{'id':'a','enabled':True,'matchers':literal('hello@example.com'),
                              'actions':[{'type':'drop'}]}], 'Existing rules were not changed'),
            'worker managed': ([{'id':'a','enabled':True,'source':'wrangler','matchers':literal('hello@example.com'),
                                 'actions':[{'type':'forward','value':['owner@example.net']}]}], 'Existing rules were not changed'),
        }
        for name, (rules, message) in cases.items():
            with self.subTest(case=name):
                self.forward_fixtures()
                self.fixtures[self.rules_path+'?per_page=50&page=1']['result'] = rules
                self.save_responses()
                if self.calls.exists():
                    self.calls.unlink()
                result = self.tty_forward('hello', '--destination', self.NEW)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(self.writes(), [])
                self.assertIn(message, result.stderr)

    def test_forward_refuses_zone_of_another_domain(self):
        self.forward_fixtures()
        self.config.write_text(FIXTURE+'CF_ZONE_ID='+self.zone+'\n')
        self.fixtures['/zones/'+self.zone]['result']['name'] = 'wrong.example'
        self.save_responses()
        result = self.tty_forward('hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.writes(), [])
        self.assertIn('nothing was changed', result.stderr)

    def test_forward_other_domain_never_writes_config(self):
        self.forward_fixtures()
        other = 'c'*32
        rule = {'id':'o1','enabled':True,'matchers':[{'type':'literal','field':'to','value':'sales@example.org'}],
                'actions':[{'type':'forward','value':['owner@example.net']}]}
        self.fixtures['/zones?name=example.org'] = {'success':True,'result':[{'id':other,'name':'example.org'}]}
        self.fixtures['/zones/'+other] = {'success':True,'result':{'id':other,'name':'example.org','status':'active',
                                                                 'account':{'id':self.account}}}
        self.fixtures['/zones/'+other+'/email/routing/rules?per_page=50&page=1'] = {'success':True,'result':[rule]}
        self.fixtures['PUT /zones/'+other+'/email/routing/rules/o1'] = {'success':True,'result':{}}
        self.fixtures['/zones/'+other+'/email/routing/rules/o1'] = {'success':True,'result':
            dict(rule, actions=[{'type':'forward','value':[self.NEW]}])}
        self.save_responses()
        self.config.write_text(FIXTURE.replace('ADDRESSES=hello,contact', 'ADDRESSES=sales'))
        before = self.config.read_bytes()
        result = self.tty_forward('sales@example.org', '--destination', self.NEW, '--domain', 'example.org')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.writes(), ['PUT /zones/'+other+'/email/routing/rules/o1'])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn('configuration not changed', result.stderr)

    def test_forward_rejects_address_on_another_domain(self):
        result = self.tty_forward('hello@example.org', '--destination', self.NEW)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('not on example.com', result.stderr)
        self.assertFalse(self.calls.exists())

    def test_forward_requires_terminal(self):
        self.forward_fixtures()
        result = self.invoke('forward', 'hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('requires terminal input', result.stderr)
        self.assertFalse(self.calls.exists())

    def test_forward_read_back_mismatch_fails(self):
        self.forward_fixtures()
        self.config.write_text(FIXTURE.replace('ADDRESSES=hello,contact', 'ADDRESSES=hello'))
        self.fixtures[self.rules_path+'/r1'] = {'success':True,'result':self.rule}
        self.save_responses()
        before = self.config.read_bytes()
        result = self.tty_forward('hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.writes(), ['PUT '+self.rules_path+'/r1'])
        self.assertIn('does not read back as forwarding to new@example.org', result.stderr)
        self.assertEqual(self.config.read_bytes(), before)

    def test_forward_disabled_rule_stays_disabled(self):
        self.forward_fixtures()
        self.fixtures[self.rules_path+'?per_page=50&page=1']['result'][0]['enabled'] = False
        self.save_responses()
        result = self.tty_forward('hello', '--destination', self.NEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(self.sent()[0]['body']['enabled'], False)
        self.assertIn('is disabled and stays disabled', result.stderr)

    CONTEXTS=[(('',),'setup'),(('config',''),'set'),(('config','set',''),'DOMAIN'),
              (('config','set',''),'REGISTRAR'),(('setup','--'),'--registrar'),
              (('setup','--registrar',''),'godaddy'),(('setup','--registrar','godaddy','--'),'--dry-run'),
              (('--config','somepath','doctor','--'),'--offline'),
              (('status','--format',''),'json'),(('',),'list'),(('list','--'),'--domain'),
              (('',),'forward'),(('forward','--'),'--destination'),(('forward','hello','--'),'--domain')]

    def completion(self, shell):
        result=self.invoke('completion',shell)
        self.assertEqual(result.returncode,0,result.stderr)
        path=self.directory/('cmail.'+shell)
        path.write_text(result.stdout)
        return path

    def test_completion_generation_offline(self):
        for shell in ('bash','zsh','fish'):
            result=self.invoke('completion',shell)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('cmail',result.stdout)
            self.assertNotIn('synthetic-token',result.stdout)
            self.assertNotIn('\x1b',result.stdout)
        self.assertFalse(self.calls.exists())

    def test_bash_completion_contexts(self):
        file=self.completion('bash')
        script='. "$1"; shift; COMP_WORDS=(cmail "$@"); COMP_CWORD=$((${#COMP_WORDS[@]}-1)); _cmail cmail "${COMP_WORDS[COMP_CWORD]}" "${COMP_WORDS[COMP_CWORD-1]}"; printf "%s\\n" "${COMPREPLY[@]}"'
        for words,expected in self.CONTEXTS:
            result=subprocess.run(['bash','-c',script,'probe',str(file),*words],
                                   env=self.env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(expected,result.stdout.split(),words)

    @unittest.skipUnless(shutil.which('zsh'), 'zsh is not installed')
    def test_zsh_completion_syntax(self):
        file=self.completion('zsh')
        syntax=subprocess.run(['zsh','-n',str(file)],text=True,capture_output=True)
        self.assertEqual(syntax.returncode,0,syntax.stderr)
        text=file.read_text()
        for word in ('#compdef cmail','setup','forward','--registrar','--dry-run','--destination','REGISTRAR'):
            self.assertIn(word,text)

    @unittest.skipUnless(shutil.which('fish'), 'fish is not installed')
    def test_fish_completion_contexts(self):
        file=self.completion('fish')
        syntax=subprocess.run(['fish','--no-config','-n',str(file)],text=True,capture_output=True)
        self.assertEqual(syntax.returncode,0,syntax.stderr)
        for words,expected in self.CONTEXTS:
            command='cmail '+' '.join(words)
            result=subprocess.run(['fish','--no-config','-c','source $argv[1]; complete -C $argv[2]',str(file),command],
                                   env=self.env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(expected,[line.split('\t')[0] for line in result.stdout.splitlines()],command)

if __name__ == '__main__':
    unittest.main()
