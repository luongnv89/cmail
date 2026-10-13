#!/usr/bin/env python3
"""Setup provider flows through the cmail binary: Cloudflare is a loopback
fixture server and gddy is a fake on PATH. Credentials are synthetic."""
import json
import os
from pathlib import Path
import pty
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(os.environ.get('CMAIL_BIN', ROOT / 'target' / 'debug' / 'cmail'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_server import FixtureServer  # noqa: E402

ZONE, ACCOUNT, TOKEN = 'a' * 32, 'b' * 32, 'synthetic-token-123'
NS = ['alice.ns.cloudflare.com', 'bob.ns.cloudflare.com']
BASE = ('DOMAIN=example.com\nDEST_EMAIL=owner@example.net\nADDRESSES=hello,contact\n'
        'CLOUDFLARE_API_TOKEN=' + TOKEN + '\nGDDY_ENV=ote\n')
RULES = '/zones/' + ZONE + '/email/routing/rules?per_page=50&page=1'
DESTS = '/accounts/' + ACCOUNT + '/email/routing/addresses?per_page=50&page=1'

FAKE_GDDY = r'''#!/usr/bin/env bash
printf 'gddy %s\n' "$*" >> "$TEST_CALLS"
reply() { [ "${2:-0}" = 0 ] || exit "$2"; printf '%s\n' "$1"; }
auth='{"data":[{"env":"ote","expired":false}]}'
get='{"data":{"nameServers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com"]}}'
list='{"data":[{"domain":"owned.example"}]}'
case "$1 $2" in
  'auth status') reply "${GDDY_AUTH:-$auth}" ;;
  'auth login') exit "${GDDY_LOGIN_EXIT:-0}" ;;
  'domain get') reply "${GDDY_GET:-$get}" "${GDDY_GET_EXIT:-0}" ;;
  'domain list') reply "${GDDY_LIST:-$list}" "${GDDY_LIST_EXIT:-0}" ;;
  'domain nameservers') exit "${GDDY_SET_EXIT:-0}" ;;
  'domain available') echo available ;;
  'domain quote') reply "${GDDY_QUOTE:-}" "${GDDY_QUOTE_EXIT:-0}" ;;
  'domain purchase') exit 0 ;;
  *) exit 99 ;;
esac
'''


def ok(result):
    return {'success': True, 'result': result}


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.config = self.dir / 'config'
        self.write_config(BASE)
        self.calls = self.dir / 'calls'
        self.payloads = self.dir / 'payloads'
        bin_dir = self.dir / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'gddy').write_text(FAKE_GDDY)
        (bin_dir / 'gddy').chmod(0o700)
        for opener in ('open', 'xdg-open', 'wslview'):
            (bin_dir / opener).write_text('#!/bin/sh\nprintf "browser %s\\n" "$1" >> "$TEST_CALLS"\n')
            (bin_dir / opener).chmod(0o700)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('CMAIL_', 'GDDY_')) and k not in
                    ('DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'CLOUDFLARE_API_TOKEN', 'REGISTRAR', 'CF_ZONE_ID',
                     'CF_ACCOUNT_ID', 'DRY_RUN', 'ENV_FILE', 'NO_COLOR', 'FORCE_COLOR', 'BROWSER')}
        self.env.update(PATH=str(bin_dir) + os.pathsep + self.env['PATH'], ENV_FILE=str(self.config),
                        TEST_CALLS=str(self.calls), CMAIL_TEST_SLEEP_LOG=str(self.calls))
        self.fixtures = {
            '/user/tokens/verify': ok({'status': 'active'}),
            '/zones?name=example.com': ok([{'id': ZONE, 'name': 'example.com'}]),
            '/zones/' + ZONE: ok({'id': ZONE, 'name': 'example.com', 'status': 'active',
                                  'account': {'id': ACCOUNT}, 'name_servers': NS}),
            '/zones/' + ZONE + '/email/routing': ok({'enabled': True, 'status': 'ready'}),
            DESTS: ok([{'email': 'owner@example.net', 'verified': '2026-01-01T00:00:00Z'}]),
            RULES: ok([self.rule('hello'), self.rule('contact')]),
        }
        self.responses = self.dir / 'responses.json'
        self.save()
        self.server = FixtureServer(str(self.responses), str(self.calls), str(self.payloads))
        self.addCleanup(self.server.close)
        self.env['CMAIL_CF_API'] = self.server.url

    def write_config(self, text):
        self.config.write_text(text)
        self.config.chmod(0o600)

    @staticmethod
    def rule(local, dest='owner@example.net', enabled=True):
        return {'id': 'r-' + local, 'enabled': enabled,
                'matchers': [{'type': 'literal', 'field': 'to', 'value': local + '@example.com'}],
                'actions': [{'type': 'forward', 'value': [dest]}]}

    def save(self):
        self.responses.write_text(json.dumps(self.fixtures))

    def setup(self, *args, answer='', env=None, command='setup'):
        """Run cmail with a terminal stdin fed `answer` (Ctrl-D ends input)."""
        settings = dict(self.env, **(env or {}))
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen([str(BIN), *command.split(), *args], stdin=slave, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, env=settings)
            os.write(master, (answer + '\x04').encode())
            out, err = proc.communicate(timeout=20)
        finally:
            os.close(slave)
            os.close(master)
        self.assertNotIn(TOKEN, out + err)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    def log(self):
        return self.calls.read_text() if self.calls.exists() else ''

    def writes(self):
        return [' '.join(l.split()[:2]) for l in self.log().splitlines()
                if l.split()[0] in ('POST', 'PUT', 'DELETE', 'PATCH')]

    def sent(self):
        return [json.loads(l) for l in self.payloads.read_text().splitlines()] if self.payloads.exists() else []

    def expect(self, result, code, *texts):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        for text in texts:
            self.assertIn(text, result.stdout + result.stderr)


class Rules(Flow):
    def test_creates_missing_rules_with_increasing_priority(self):
        self.fixtures[RULES] = ok([])
        self.fixtures['POST /zones/' + ZONE + '/email/routing/rules'] = ok({})
        self.save()
        result = self.setup()
        self.expect(result, 0, 'hello@example.com -> owner@example.net', 'Receiving is set up')
        bodies = [p['body'] for p in self.sent()]
        self.assertEqual([b['priority'] for b in bodies], [0, 1])
        self.assertEqual(bodies[1], {'name': 'fwd contact@example.com', 'enabled': True, 'priority': 1,
                                     'matchers': [{'type': 'literal', 'field': 'to', 'value': 'contact@example.com'}],
                                     'actions': [{'type': 'forward', 'value': ['owner@example.net']}]})

    def test_existing_rules_are_never_overwritten(self):
        for name, rules, text in [
            ('disabled', [self.rule('hello', enabled=False)], 'enable/correct it'),
            ('other destination', [self.rule('hello', dest='x@example.org')], 'Existing rules were not overwritten'),
            ('duplicate', [self.rule('hello'), self.rule('hello')], 'Existing rules were not overwritten')]:
            with self.subTest(name):
                self.fixtures[RULES] = ok(rules)
                self.save()
                self.calls.unlink(missing_ok=True)
                self.expect(self.setup(), 1, text, 'Setup stopped at: Forwarding addresses')
                self.assertEqual(self.writes(), [])

    def test_rule_errors(self):
        for name, fixture, text in [
            ('denied', {'success': False, 'errors': [{'message': 'Rules access denied'}], '_status': 403},
             'Email Routing Rules > Edit'),
            ('malformed', {'success': True, 'result': {'not': 'a list'}}, 'invalid forwarding rules')]:
            with self.subTest(name):
                self.fixtures[RULES] = fixture
                self.save()
                self.expect(self.setup(), 1, text)
                self.assertEqual(self.writes(), [])

    def test_rule_creation_error_details(self):
        self.fixtures[RULES] = ok([])
        self.fixtures['POST /zones/' + ZONE + '/email/routing/rules'] = {
            'success': False, 'errors': [{'message': 'Invalid rule'}], '_status': 422}
        self.save()
        self.expect(self.setup(), 1, 'Invalid rule', 'HTTP 422')


class Routing(Flow):
    DNS = 'POST /zones/' + ZONE + '/email/routing/dns'

    def disabled(self, response):
        self.fixtures['/zones/' + ZONE + '/email/routing'] = ok({'enabled': False})
        self.fixtures[self.DNS] = response
        self.save()

    def test_disabled_routing_uses_dns_activation(self):
        self.disabled(ok({'enabled': True}))
        self.expect(self.setup(), 0, 'email routing enabled (Cloudflare routing DNS records added and locked)')
        self.assertEqual(self.writes(), [self.DNS])
        self.assertEqual(self.sent()[0]['body'], {})

    def test_enabled_routing_skips_mutation(self):
        self.expect(self.setup(), 0, 'email routing already enabled')
        self.assertEqual(self.writes(), [])

    def test_activation_failures(self):
        for name, response, texts in [
            ('permission', {'success': False, 'errors': [{'message': 'Authentication error'}], '_status': 403},
             ['Authentication error', 'Zone Settings > Edit', 'conflicting MX/TXT']),
            ('empty', {'_body': '', '_status': 500}, ['empty response body', 'Cloudflare service error']),
            ('html', {'_body': '<html>Bad Gateway</html>', '_status': 502}, ['<html>Bad Gateway</html>']),
            ('api error', {'success': False, 'errors': [{'message': 'activation rejected'}]}, ['activation rejected']),
            ('malformed', {'_body': 'not json'}, ['non-JSON response']),
            ('unconfirmed', ok({'enabled': False}), ['did not confirm Email Routing is enabled'])]:
            with self.subTest(name):
                self.disabled(response)
                self.calls.unlink(missing_ok=True)
                self.expect(self.setup(), 1, *texts)
                self.assertEqual(self.writes(), [self.DNS], 'activation is never retried')


class Destination(Flow):
    REGISTER = 'POST /accounts/' + ACCOUNT + '/email/routing/addresses'
    VERIFIED = {'email': 'owner@example.net', 'verified': '2026-01-01T00:00:00Z'}
    PENDING = {'email': 'owner@example.net', 'verified': None}

    def test_absent_destination_is_registered_then_verified(self):
        self.fixtures[DESTS] = {'_sequence': [ok([]), ok([self.PENDING]), ok([self.VERIFIED])]}
        self.fixtures[self.REGISTER] = ok(self.PENDING)
        self.save()
        result = self.setup()
        self.expect(result, 0, 'verification email sent to owner@example.net', 'still unverified', 'owner@example.net verified')
        self.assertEqual(self.writes(), [self.REGISTER])
        self.assertEqual(self.sent()[0]['body'], {'email': 'owner@example.net'})
        self.assertIn('sleep 15', self.log())

    def test_pending_destination_is_not_recreated(self):
        self.fixtures[DESTS] = {'_sequence': [ok([self.PENDING]), ok([self.VERIFIED])]}
        self.save()
        self.expect(self.setup(), 0, 'already registered but unverified', 'owner@example.net verified')
        self.assertEqual(self.writes(), [])

    def test_destination_on_second_page_is_found(self):
        filler = [{'email': 'u%d@example.org' % i, 'verified': None} for i in range(50)]
        self.fixtures[DESTS] = ok(filler)
        self.fixtures[DESTS.replace('page=1', 'page=2')] = ok([self.VERIFIED])
        self.save()
        self.expect(self.setup(), 0, 'owner@example.net verified')
        self.assertEqual(self.writes(), [])

    def test_failures_never_claim_success(self):
        for name, fixtures, code, texts, writes in [
            ('list denied', {DESTS: {'success': False, 'errors': [{'message': 'Address access denied'}], '_status': 403}},
             1, ['Email Routing Addresses > Edit'], []),
            ('creation rejected', {DESTS: ok([]), self.REGISTER: {'success': False, 'errors': [{'message': 'Address creation rejected'}], '_status': 400}},
             1, ['Address creation rejected'], [self.REGISTER]),
            ('invalid create result', {DESTS: ok([]), self.REGISTER: ok({'email': 'other@example.net'})},
             1, ['did not confirm destination registration'], [self.REGISTER]),
            ('verification timeout', {DESTS: ok([self.PENDING])},
             1, ['not verified after 1s', 'The pending destination is kept'], []),
            ('missing zone account', {'/zones/' + ZONE: ok({'id': ZONE, 'name': 'example.com', 'status': 'active', 'name_servers': NS})},
             1, ['missing its account ID'], [])]:
            with self.subTest(name):
                self.setUp()
                self.fixtures.update(fixtures)
                self.save()
                result = self.setup('--wait-timeout', '1')
                self.expect(result, code, *texts)
                self.assertNotIn('verification email sent', result.stderr)
                self.assertEqual(self.writes(), writes)

    def test_gmail_destination_opens_mailbox(self):
        self.write_config(BASE.replace('owner@example.net', 'owner@gmail.com'))
        self.fixtures[DESTS] = {'_sequence': [ok([{'email': 'owner@gmail.com', 'verified': None}]),
                                              ok([{'email': 'owner@gmail.com', 'verified': '2026-01-01T00:00:00Z'}])]}
        self.fixtures[RULES] = ok([self.rule('hello', 'owner@gmail.com'), self.rule('contact', 'owner@gmail.com')])
        self.save()
        self.expect(self.setup(), 0, 'Open: https://mail.google.com/')
        self.assertIn('browser https://mail.google.com/', self.log())


class Zone(Flow):
    def no_zone(self, accounts):
        self.fixtures['/zones?name=example.com'] = ok([])
        self.fixtures['/accounts'] = accounts
        self.fixtures['POST /zones'] = ok({'id': ZONE})
        self.save()

    def test_zone_creation_in_the_only_account(self):
        self.no_zone(ok([{'id': ACCOUNT, 'name': 'Main'}]))
        self.expect(self.setup(), 0, 'creating zone example.com in account ' + ACCOUNT, 'nameservers: ' + ' '.join(NS))
        self.assertEqual(self.sent()[0]['body'], {'name': 'example.com', 'account': {'id': ACCOUNT}})
        self.assertIn("CF_ZONE_ID='" + ZONE + "'", self.config.read_text())

    def test_explicit_account_skips_listing(self):
        self.no_zone({'success': False, '_status': 403})
        self.write_config(BASE + 'CF_ACCOUNT_ID=' + 'c' * 32 + '\n')
        self.expect(self.setup(), 0, 'creating zone example.com in account ' + 'c' * 32)
        self.assertNotIn('GET /accounts ', self.log())

    def test_account_problems_stop_before_writes(self):
        for name, accounts, texts in [
            ('none', ok([]), ['no Cloudflare account visible', 'To unlock account discovery']),
            ('several', ok([{'id': ACCOUNT, 'name': 'A'}, {'id': 'c' * 32, 'name': 'B'}]),
             ['refusing to choose one automatically', 'A: ' + ACCOUNT, 'set CF_ACCOUNT_ID']),
            ('denied', {'success': False, 'errors': [{'message': 'denied ' + TOKEN}], '_status': 403},
             ['HTTP 403', 'To unlock account discovery', '[redacted]']),
            ('outage', {'success': False, '_status': 503}, ['Cloudflare service error']),
            ('name instead of id', ok([{'id': 'Main account', 'name': 'Main'}]), ['32-character account ID']),
            ('malformed', {'success': True, 'result': 'x'}, ['invalid account list'])]:
            with self.subTest(name):
                self.setUp()
                self.no_zone(accounts)
                self.expect(self.setup(), 1, *texts, 'Setup stopped at: Cloudflare zone: example.com')
                self.assertEqual(self.writes(), [])

    def test_zone_without_nameservers(self):
        self.fixtures['/zones/' + ZONE]['result']['name_servers'] = ['only.one']
        self.save()
        self.expect(self.setup(), 1, 'no nameserver change applied')

    def test_transport_failure_is_not_a_token_problem(self):
        result = self.setup(env={'CMAIL_CF_API': 'http://127.0.0.1:9/client/v4'})
        self.expect(result, 1, 'not evidence of an invalid token', 'Cloudflare request failed: GET /user/tokens/verify')

    def test_token_rejected_and_inactive(self):
        self.fixtures['/user/tokens/verify'] = {'success': False, 'errors': [{'message': 'Invalid token'}], '_status': 401}
        self.save()
        self.expect(self.setup(), 1, 'replace CLOUDFLARE_API_TOKEN', 'HTTP 401')
        self.fixtures['/user/tokens/verify'] = ok({'status': 'disabled'})
        self.save()
        result = self.setup('--no-browser')
        self.expect(result, 1, "token is 'disabled'", 'Custom token', 'no token input')
        self.assertNotIn('browser', self.log())

    def test_pasted_token_is_verified_and_saved(self):
        self.write_config(BASE.replace('CLOUDFLARE_API_TOKEN=' + TOKEN + '\n', ''))
        result = self.setup('--no-browser', answer=TOKEN + '\n')
        self.expect(result, 0, 'Cloudflare token verified and saved to .env', 'permissions are checked')
        self.assertIn("CLOUDFLARE_API_TOKEN='" + TOKEN + "'", self.config.read_text())

    def test_activation_wait(self):
        self.fixtures['/zones/' + ZONE]['result']['status'] = 'moved'
        self.save()
        self.expect(self.setup('--registrar', 'godaddy'), 1, "zone status 'moved' needs attention")
        self.fixtures['/zones/' + ZONE]['result']['status'] = 'pending'
        self.save()
        self.write_config(BASE)
        result = self.setup('--wait-timeout', '40')
        self.expect(result, 1, 'replace ALL nameservers', 'alice.ns.cloudflare.com', "zone still 'pending' after 40s",
                    '24–48 hours', 'cmail never changes nameservers in manual registrar mode')
        self.assertEqual(self.log().count('sleep 20'), 2)


class GoDaddy(Flow):
    def godaddy(self, answer='', **env):
        return self.setup('--registrar', 'godaddy', answer=answer, env=env)

    def gddy_calls(self):
        return [l for l in self.log().splitlines() if l.startswith('gddy ')]

    def test_matching_nameservers_skip_update(self):
        mixed = '{"data":{"nameServers":["BOB.ns.cloudflare.com.","alice.ns.cloudflare.com"]}}'
        self.expect(self.godaddy(GDDY_GET=mixed), 0, 'skipping update', 'GoDaddy authentication (ote)')
        self.assertFalse(any('nameservers set' in c for c in self.gddy_calls()))

    def test_nameserver_replacement(self):
        other = '{"data":{"nameServers":["ns1.registrar.example","alice.ns.cloudflare.com"]}}'
        result = self.godaddy('y\n', GDDY_GET=other)
        self.expect(result, 0, 'replaces ALL nameservers', 'current nameservers:', 'nameservers set:')
        sets = [c for c in self.gddy_calls() if 'nameservers set' in c]
        self.assertEqual(sets, ['gddy domain nameservers set --nameserver alice.ns.cloudflare.com --nameserver '
                                'bob.ns.cloudflare.com example.com --env ote --timeout 30s'])
        self.assertIn("REGISTRAR='godaddy'", self.config.read_text())

    def test_nameserver_failures(self):
        other = '{"data":{"nameServers":["ns1.registrar.example"]}}'
        for name, answer, env, texts, wrote in [
            ('declined', 'n\n', {'GDDY_GET': other}, ['aborted before nameserver change'], False),
            ('update failed', 'y\n', {'GDDY_GET': other, 'GDDY_SET_EXIT': '1'}, ['nameserver update failed', 'may still have applied'], True),
            ('lookup failed', '', {'GDDY_GET_EXIT': '1'}, ['could not verify current nameservers'], False),
            ('bad response', '', {'GDDY_GET': '{"data":{}}'}, ['could not read current nameservers'], False)]:
            with self.subTest(name):
                self.calls.unlink(missing_ok=True)
                result = self.godaddy(answer, **env)
                self.expect(result, 1, *texts, 'Setup stopped at: GoDaddy: point')
                self.assertEqual(any('nameservers set' in c for c in self.gddy_calls()), wrote)
                if name != 'declined':
                    self.assertIn('delegation may already have changed', result.stderr)

    def test_authentication(self):
        expired = '{"data":[{"env":"ote","expired":true}]}'
        self.expect(self.godaddy(GDDY_AUTH=expired, GDDY_LOGIN_EXIT='1'), 1, 'gddy auth login --env ote', 'renew/recreate')
        login = [c for c in self.gddy_calls() if 'auth login' in c]
        self.assertTrue(login[0].endswith('--timeout 1200s'), login)
        self.write_config(BASE + 'GDDY_PAT=private-pat\n')
        result = self.godaddy()
        self.expect(result, 0, 'using PAT')
        self.assertNotIn('private-pat', result.stdout + result.stderr)

    def test_domain_selection_and_purchase_guards(self):
        self.write_config(BASE.replace('DOMAIN=example.com\n', ''))
        self.expect(self.godaddy(GDDY_LIST_EXIT='1'), 1, 'could not list GoDaddy domains', 'gddy domain list --env ote --json')
        self.expect(self.godaddy(GDDY_LIST='{"bad":1}'), 1, 'could not read GoDaddy domain list')
        self.expect(self.godaddy(), 1, 'Your GoDaddy domains:', 'owned.example', 'domain input unavailable')
        self.expect(self.godaddy('bad/domain\n'), 3, 'DOMAIN must be a domain name')
        quote = json.dumps({'data': {'domain': 'new.example', 'available': True, 'price': '12.00', 'currency': 'USD',
                                     'requiredAgreements': [{'title': 'Terms', 'url': 'https://example.com/t'}],
                                     'quoteToken': 'quote-token'}})
        self.calls.unlink(missing_ok=True)
        result = self.godaddy('new.example\ny\nwrong phrase\n', GDDY_GET_EXIT='1', GDDY_QUOTE=quote)
        self.expect(result, 1, 'charges your GoDaddy account', 'Type new.example to approve', 'purchase declined')
        self.assertFalse(any('purchase' in c and 'quote-token' in c for c in self.gddy_calls()))
        self.expect(self.godaddy('new.example\ny\n', GDDY_GET_EXIT='1', GDDY_QUOTE_EXIT='1'), 1, 'quote failed', 'before retrying any purchase')

    def test_owned_domain_is_saved(self):
        self.write_config(BASE.replace('DOMAIN=example.com\n', ''))
        self.fixtures['/zones?name=owned.example'] = ok([])
        self.fixtures['/accounts'] = ok([])
        self.save()
        self.godaddy('owned.example\n')
        self.assertIn("DOMAIN='owned.example'", self.config.read_text())


class Workflow(Flow):
    def test_config_problems(self):
        self.write_config('DOMAIN=$(touch /tmp/x)\n')
        self.expect(self.setup(), 3, 'expansions/commands are not allowed', 'could not load config')
        self.write_config(BASE)
        self.config.chmod(0o644)
        self.expect(self.setup(), 3, 'mode 600')
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o644, 'setup never repairs before loading')

    def test_prompts(self):
        self.write_config('CLOUDFLARE_API_TOKEN=' + TOKEN + '\n')
        self.expect(self.setup(answer='\n'), 1, 'DEST_EMAIL is required', 'private config')
        self.expect(self.setup(), 1, 'DEST_EMAIL input unavailable', 'interactive terminal')
        # ADDRESSES defaults to hello, so only DEST_EMAIL and DOMAIN are asked.
        self.expect(self.setup(answer='me@example.net\nhttps://example.com/x\n'), 3, 'DOMAIN must be a domain name')
        result = self.setup(answer='Example.COM\n', env={'PATH': '/usr/bin:/bin'})
        text = self.config.read_text()
        self.assertIn("DEST_EMAIL='me@example.net'", text)
        self.assertIn("DOMAIN='example.com'", text)
        # The new inbox is not a Cloudflare destination in the fixture, so setup stops there.
        self.expect(result, 1, 'Setup stopped at: Destination address: me@example.net')

    def test_missing_config_is_created_privately(self):
        target = self.dir / 'new' / 'config.env'
        result = self.setup('--domain', 'example.com', '--destination', 'owner@example.net', '--addresses', 'hello,contact',
                            env={'ENV_FILE': str(target), 'CLOUDFLARE_API_TOKEN': TOKEN})
        self.expect(result, 0, 'created ' + str(target), 'Receiving is set up')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
        self.assertIn("ADDRESSES='hello,contact'", target.read_text())

    def test_send_as_guide(self):
        result = self.setup('--no-browser', answer='\n', command='send-as')
        self.expect(result, 0, 'Receiving already', 'App passwords unavailable', 'Work/school policy', 'SMTP rejected',
                    'Confirmation missing', 'DIFFERENT mailbox', 'Send from Gmail', 'not automatically verified',
                    'hello@example.com', 'Open: https://myaccount.google.com/apppasswords')
        result = self.setup(command='send-as')
        self.expect(result, 1, 'Gmail guide paused without input', 'cmail send-as')


if __name__ == '__main__':
    unittest.main()
