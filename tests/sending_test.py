#!/usr/bin/env python3
"""`cmail sending enable` through the binary. Cloudflare and public DNS are
loopback fixture servers; credentials are synthetic. Nothing leaves the host."""
import hashlib
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

ZONE, ACCOUNT = 'a' * 32, 'b' * 32
MAIN, SEND = 'synthetic-main-token-111', 'synthetic-sending-token-222'
BASE = ('DOMAIN=example.com\nDEST_EMAIL=owner@example.net\nADDRESSES=hello\nCLOUDFLARE_API_TOKEN=' + MAIN +
        '\nGDDY_ENV=prod\nCF_ZONE_ID=' + ZONE + '\n')
SUBS = '/zones/' + ZONE + '/email/sending/subdomains'
LIST = SUBS + '?per_page=50&page=1'
POST = 'POST ' + SUBS
DNS = SUBS + '/t1/dns'
DOH = '/dns-query?name=_dmarc.example.com&type=TXT'
PRESENT = {'Status': 0, 'Answer': [{'name': '_dmarc.example.com.', 'type': 16, 'data': '"v=DMARC1; p=none;"'}]}
MISSING = {'Status': 3}
RECORDS = [
    {'type': 'MX', 'name': 'cf-bounce.example.com', 'content': 'route1.mx.cloudflare.net', 'priority': 10, 'ttl': 1},
    {'type': 'TXT', 'name': 'cf-bounce.example.com', 'content': 'v=spf1 include:_spf.mx.cloudflare.net ~all'},
    {'type': 'TXT', 'name': 'cf-bounce._domainkey.example.com', 'content': 'v=DKIM1; h=sha256; k=rsa; p=MIIB'},
]
NONE_RECORD = 'Type: TXT   Name: _dmarc   Content: v=DMARC1; p=none;'
UNCONFIRMED = ('the onboarding request was sent but its result could not be confirmed — check Compute > Email '
               'Service > Email Sending (and the _dmarc record) in the Cloudflare dashboard before rerunning')
EXPLANATION = ("Gmail \"Send mail as\" delivers through Google's servers, which can't sign with your domain's "
               "Cloudflare DKIM key, and your SPF only lists Cloudflare.")


def ok(result):
    return {'success': True, 'errors': [], 'messages': [], 'result': result}


def fail(status, *codes, message='failed'):
    return {'_status': status, 'success': False, 'messages': [], 'result': None,
            'errors': [{'code': code, 'message': message} for code in codes]}


def entry(enabled, name='example.com', tag='t1'):
    return {'tag': tag, 'name': name, 'enabled': enabled, 'dkim_selector': 'cf-bounce',
            'return_path_domain': 'cf-bounce.example.com'}


def bearer(token):
    return hashlib.sha256(('Bearer ' + token).encode()).hexdigest()[:16]


class Sending(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.config = self.dir / 'config'
        self.write_config(BASE + 'CF_SENDING_TOKEN=' + SEND + '\n')
        self.calls, self.payloads, self.auth = self.dir / 'calls', self.dir / 'payloads', self.dir / 'auth'
        self.doh_calls, self.doh_auth, self.sleeps = self.dir / 'doh-calls', self.dir / 'doh-auth', self.dir / 'sleeps'
        self.fixtures = {LIST: ok([]), POST: ok(entry(True)), DNS: ok(RECORDS)}
        self.dns = {DOH: PRESENT}
        self.responses, self.dns_file = self.dir / 'responses.json', self.dir / 'dns.json'
        self.save()
        self.api = FixtureServer(str(self.responses), str(self.calls), str(self.payloads), auth_log=str(self.auth))
        self.addCleanup(self.api.close)
        self.doh = FixtureServer(str(self.dns_file), str(self.doh_calls), prefix='', auth_log=str(self.doh_auth))
        self.addCleanup(self.doh.close)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('CMAIL_', 'GDDY_')) and k not in
                    ('DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'NOTIFY_FROM', 'CLOUDFLARE_API_TOKEN', 'CF_SENDING_TOKEN',
                     'REGISTRAR', 'CF_ZONE_ID', 'CF_ACCOUNT_ID', 'DRY_RUN', 'ENV_FILE', 'NO_COLOR', 'FORCE_COLOR', 'BROWSER')}
        self.env.update(ENV_FILE=str(self.config), CMAIL_CF_API=self.api.url, CMAIL_DOH_URL=self.doh.url + '/dns-query',
                        CMAIL_TEST_SLEEP_LOG=str(self.sleeps), NO_COLOR='1')

    def write_config(self, text):
        self.config.write_text(text)
        self.config.chmod(0o600)

    def save(self):
        self.responses.write_text(json.dumps(self.fixtures))
        self.dns_file.write_text(json.dumps(self.dns))

    def run_tty(self, *args, answer='', env=None):
        """`cmail --no-browser sending enable ARGS` with a terminal stdin fed `answer` (Ctrl-D ends input)."""
        settings = dict(self.env, **(env or {}))
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen([str(BIN), '--no-browser', 'sending', 'enable', *args], stdin=slave,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=settings)
            os.write(master, (answer + '\x04').encode())
            out, err = proc.communicate(timeout=20)
        finally:
            os.close(slave)
            os.close(master)
        return self.checked(subprocess.CompletedProcess(proc.args, proc.returncode, out, err))

    def run_pipe(self, *args, stdin='', env=None):
        settings = dict(self.env, **(env or {}))
        result = subprocess.run([str(BIN), *args], input=stdin, text=True, capture_output=True, env=settings,
                                timeout=20)
        return self.checked(result)

    def checked(self, result):
        text = result.stdout + result.stderr
        self.assertNotIn(MAIN, text)
        self.assertNotIn(SEND, text)
        self.assertNotIn('panicked', text)
        return result

    def read(self, path):
        return path.read_text().splitlines() if path.exists() else []

    def writes(self):
        return [' '.join(line.split()[:2]) for line in self.read(self.calls) if line.split()[0] != 'GET']

    def sent(self):
        return [json.loads(line)['body'] for line in self.read(self.payloads)]

    def expect(self, result, code, *texts):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        for text in texts:
            self.assertIn(text, result.stdout + result.stderr)


class Onboarding(Sending):
    def test_already_enabled_makes_no_post(self):
        self.fixtures[LIST] = ok([entry(False, 'other.example'), entry(True, 'Example.COM')])
        self.save()
        result = self.run_tty()
        self.expect(result, 0, 'sending already enabled for example.com')
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.read(self.calls)[0], 'GET ' + LIST + ' ')

    def test_absent_domain_is_previewed_then_posted_once_after_yes(self):
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        result = self.run_tty(answer='y\n')
        self.expect(result, 0, 'Email Sending enabled for example.com', 'policy p=none',
                    'Cloudflare keeps an existing DMARC record unchanged', 'route1.mx.cloudflare.net (priority 10)',
                    'v=DKIM1; h=sha256; k=rsa; p=MIIB', 'cmail notify')
        preview = result.stderr.index('MX    cf-bounce.example.com')
        for text in ('v=spf1 include:_spf.mx.cloudflare.net ~all', 'TXT   cf-bounce._domainkey.example.com',
                     'DMARC: _dmarc.example.com exists'):
            self.assertLess(preview, result.stderr.index(text))
            self.assertLess(result.stderr.index(text), result.stderr.index('Onboard example.com'))
        self.assertEqual(self.writes(), [POST])
        self.assertEqual(self.sent(), [{'name': 'example.com'}])
        calls = self.read(self.calls)
        self.assertEqual(calls[0], 'GET ' + LIST + ' ')
        self.assertEqual(calls[-1], 'GET ' + DNS + ' ')

    def test_declining_the_question_writes_nothing(self):
        result = self.run_tty(answer='n\n')
        self.expect(result, 1, 'cancelled — nothing was changed')
        self.assertEqual(self.writes(), [])

    def test_disabled_entry_is_posted(self):
        self.fixtures[LIST] = {'_sequence': [ok([entry(False)]), ok([entry(True)])]}
        self.save()
        self.expect(self.run_tty(answer='y\n'), 0, 'Email Sending enabled for example.com')
        self.assertEqual(self.writes(), [POST])

    def test_post_error_is_success_only_when_read_back_is_enabled(self):
        self.fixtures[POST] = fail(409, 1000, message='already exists')
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        self.expect(self.run_tty(answer='y\n'), 0, 'HTTP 409', 'now reads back as enabled',
                    'Email Sending enabled for example.com')
        for read_back in (ok([]), ok([entry(False)])):
            with self.subTest(read_back=read_back):
                self.calls.unlink()
                self.fixtures[LIST] = {'_sequence': [ok([]), read_back]}
                self.save()
                self.api.counts.clear()
                result = self.run_tty(answer='y\n')
                self.expect(result, 1, 'HTTP 409 with error code 1000', 'Cloudflare API error: POST ' + SUBS)
                self.assertNotIn('Email Sending enabled', result.stdout + result.stderr)

    def test_success_without_enabled_read_back_is_an_error(self):
        self.fixtures[LIST] = ok([])
        self.save()
        self.expect(self.run_tty(answer='y\n'), 1, 'does not read back as enabled for sending')

    def test_id_or_tag_selects_the_dns_read_back(self):
        by_id = dict(entry(True), id='abc123')
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([by_id])]}
        self.fixtures[SUBS + '/abc123/dns'] = ok(RECORDS)
        self.save()
        self.expect(self.run_tty(answer='y\n'), 0, 'route1.mx.cloudflare.net')
        self.assertIn('GET ' + SUBS + '/abc123/dns ', self.read(self.calls))
        # An unusable id (here a number) falls back to the documented tag.
        self.calls.unlink()
        self.api.counts.clear()
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([dict(entry(True), id=123)])]}
        self.save()
        self.expect(self.run_tty(answer='y\n'), 0, 'route1.mx.cloudflare.net')
        self.assertEqual(self.read(self.calls)[-1], 'GET ' + DNS + ' ')


class Responses(Sending):
    def test_unknown_error_code_is_reported_with_status_and_code(self):
        self.fixtures[LIST] = fail(400, 10999)
        self.save()
        self.expect(self.run_tty(), 1, 'HTTP 400 with error code 10999', 'does not recognise')

    def test_sending_hints_follow_the_error_table(self):
        cases = [
            (fail(403, 10102), 'sending token lacks permission — grant Email Sending · Edit for the account that '
                               'owns example.com, with Zone Resources including example.com'),
            (fail(401, 10101), 'sending token rejected — replace CF_SENDING_TOKEN'),
            (fail(429, 10004), 'Cloudflare sending limit reached (rate or daily quota)'),
            (fail(503, 10100), 'Cloudflare service error'),
            (fail(403, 10777), 'grants Email Sending · Edit'),
        ]
        for response, hint in cases:
            with self.subTest(hint=hint):
                self.fixtures[LIST] = response
                self.save()
                result = self.run_tty()
                self.expect(result, 1, hint)
                self.assertNotIn('cmail setup', result.stderr)
                self.assertNotIn('Zone > Zone > Read', result.stderr)

    def test_both_tokens_are_redacted_from_errors(self):
        self.fixtures[LIST] = fail(403, 10102, message='bad ' + SEND + ' and ' + MAIN)
        self.save()
        self.expect(self.run_tty(), 1, 'bad [redacted] and [redacted]')

    def test_missing_fields_give_clear_messages(self):
        cases = [
            ({'success': True}, 1, 'no sending-subdomain list (missing result)'),
            (ok([{'tag': 't1', 'enabled': True}]), 1, 'sending subdomain without a name'),
            (ok([{'tag': 't1', 'name': 'example.com'}]), 1, 'without a valid enabled state'),
        ]
        for response, code, text in cases:
            with self.subTest(text=text):
                self.fixtures[LIST] = response
                self.save()
                self.expect(self.run_tty(answer='y\n'), code, text)
        self.assertEqual(self.writes(), [])

    def test_malformed_read_back_after_the_post_never_claims_nothing_changed(self):
        cases = [
            ({'success': True}, 'no sending-subdomain list (missing result)'),
            (ok([{'tag': 't1', 'enabled': True}]), 'sending subdomain without a name'),
            (ok([{'tag': 't1', 'name': 'example.com'}]), 'without a valid enabled state'),
        ]
        for read_back, text in cases:
            with self.subTest(text=text):
                self.fixtures[LIST] = {'_sequence': [ok([]), read_back]}
                self.save()
                self.api.counts.clear()
                self.calls.unlink(missing_ok=True)
                result = self.run_tty(answer='y\n')
                self.expect(result, 1, text, UNCONFIRMED)
                self.assertNotIn('nothing was changed', result.stdout + result.stderr)
                self.assertNotIn('Email Sending enabled', result.stdout + result.stderr)
                self.assertEqual(self.writes(), [POST])

    def test_failed_read_back_after_the_post_says_the_request_was_sent(self):
        cases = [
            # Probe D3 (review r1): the POST fails with an unknown code, then the read-back is rate limited.
            (fail(400, 1234), fail(429, 971),
             ['Cloudflare sending limit reached', 'GET ' + LIST + ' (HTTP 429)',
              'the onboarding POST itself answered HTTP 400 with error code 1234']),
            (ok(entry(True)), fail(503, 10002), ['Cloudflare service error', 'GET ' + LIST + ' (HTTP 503)']),
            (ok(entry(True)), {'_drop': True},
             ['check your connection', 'Cloudflare request failed: GET ' + LIST]),
        ]
        for posted, read_back, texts in cases:
            with self.subTest(read_back=read_back):
                self.fixtures[POST] = posted
                self.fixtures[LIST] = {'_sequence': [ok([]), read_back]}
                self.save()
                self.api.counts.clear()
                self.calls.unlink(missing_ok=True)
                result = self.run_tty(answer='y\n')
                self.expect(result, 1, UNCONFIRMED, *texts)
                text = result.stdout + result.stderr
                self.assertNotIn('nothing was changed', text)
                self.assertNotIn('Email Sending enabled', text)
                if '_status' not in posted:
                    self.assertNotIn('onboarding POST itself', text)
                self.assertEqual(self.writes(), [POST])

    def test_dns_read_failure_after_confirmed_onboarding_only_warns(self):
        for dns in (fail(500, 10002), {'_drop': True}):
            with self.subTest(dns=dns):
                self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
                self.fixtures[DNS] = dns
                self.save()
                self.api.counts.clear()
                self.expect(self.run_tty(answer='y\n'), 0, 'Email Sending enabled for example.com',
                            'could not read the DNS records Cloudflare manages for sending')

    def test_missing_read_back_id_or_dns_fields_skip_with_a_message(self):
        untagged = {'name': 'example.com', 'enabled': True}
        cases = [
            (ok([untagged]), ok(RECORDS), 'no usable subdomain id — skipping the DNS record read-back'),
            (ok([entry(True)]), {'success': True}, 'no DNS record list'),
            (ok([entry(True)]), ok([{'type': 'MX'}, {}]), '  ?     ?  ?'),
        ]
        for read_back, dns, text in cases:
            with self.subTest(text=text):
                self.fixtures[LIST] = {'_sequence': [ok([]), read_back]}
                self.fixtures[DNS] = dns
                self.save()
                self.api.counts.clear()
                self.expect(self.run_tty(answer='y\n'), 0, 'Email Sending enabled for example.com', text)

    def test_list_pages_until_the_domain_is_found(self):
        page = [entry(True, 'n%d.example' % i, 'x%d' % i) for i in range(50)]
        self.fixtures[LIST] = ok(page)
        self.fixtures[SUBS + '?per_page=50&page=2'] = ok([entry(True)])
        self.save()
        self.expect(self.run_tty(), 0, 'sending already enabled for example.com')
        self.assertEqual(self.writes(), [])


class Dmarc(Sending):
    def test_none_mode_never_onboards_while_dmarc_is_missing(self):
        self.dns[DOH] = MISSING
        self.save()
        result = self.run_tty('--dmarc', 'none', '--wait-timeout', '30', answer='y\n')
        self.expect(result, 3, NONE_RECORD, EXPLANATION, 'add the record, then rerun cmail sending enable',
                    'never onboards while _dmarc is missing')
        self.assertEqual(self.read(self.sleeps), ['sleep 15', 'sleep 15'])
        self.assertEqual(len(self.read(self.doh_calls)), 3)
        self.assertEqual(self.writes(), [])
        # The rerun after the user added the record onboards once.
        self.dns[DOH] = PRESENT
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        self.expect(self.run_tty('--dmarc', 'none', answer='y\n'), 0, 'Email Sending enabled for example.com')
        self.assertEqual(self.writes(), [POST])

    def test_none_mode_onboards_once_the_record_appears_during_the_wait(self):
        self.dns[DOH] = {'_sequence': [MISSING, MISSING, PRESENT]}
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        result = self.run_tty('--dmarc', 'none', answer='y\n')
        self.expect(result, 0, NONE_RECORD, '_dmarc.example.com found', 'Email Sending enabled for example.com')
        self.assertEqual(self.read(self.sleeps), ['sleep 15', 'sleep 15'])
        self.assertEqual(self.writes(), [POST])

    def test_wait_timeout_one_still_rechecks_once(self):
        self.dns[DOH] = MISSING
        self.save()
        result = self.run_tty('--dmarc', 'none', '--wait-timeout', '1', answer='y\n')
        self.expect(result, 3, 'add the record, then rerun cmail sending enable')
        self.assertEqual(self.read(self.sleeps), ['sleep 1'])
        self.assertEqual(len(self.read(self.doh_calls)), 2)
        self.assertEqual(self.writes(), [])

    def test_none_mode_wait_rides_out_transient_dns_errors(self):
        blip = {'_status': 500, '_body': 'oops'}
        # Three consecutive unreadable answers are tolerated; the record then appears and onboarding runs.
        self.dns[DOH] = {'_sequence': [MISSING, blip, blip, blip, PRESENT]}
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        result = self.run_tty('--dmarc', 'none', answer='y\n')
        self.expect(result, 0, '(HTTP 500) (1/3) — retrying', '(HTTP 500) (3/3) — retrying',
                    '_dmarc.example.com found', 'Email Sending enabled for example.com')
        self.assertNotIn('no time left to retry', result.stderr)
        self.assertEqual(self.writes(), [POST])
        # A fourth in a row, or an unreadable final re-check, fails closed: no write, never "found".
        # The final re-check at the deadline promises no retry it cannot make.
        for answers, args, last in (([MISSING, blip, blip, blip, blip], [], '(3/3) — retrying'),
                                    ([MISSING, MISSING, blip], ['--wait-timeout', '30'],
                                     '(HTTP 500) (1/3) — no time left to retry')):
            with self.subTest(answers=answers):
                self.calls.unlink()
                self.doh.counts.clear()
                self.api.counts.clear()
                self.dns[DOH] = {'_sequence': answers}
                self.save()
                result = self.run_tty('--dmarc', 'none', *args, answer='y\n')
                self.expect(result, 1, 'could not read _dmarc.example.com from public DNS (HTTP 500)',
                            'nothing was changed', last)
                if 'no time left' in last:
                    self.assertNotIn('— retrying', result.stderr)
                self.assertNotIn('found', result.stderr)
                self.assertEqual(self.writes(), [])

    def test_auto_mode_asks_about_send_as(self):
        self.dns[DOH] = MISSING
        self.save()
        result = self.run_tty('--wait-timeout', '15', answer='y\n')
        self.expect(result, 3, 'Do you send as @example.com from Gmail (cmail send-as) or any other service?',
                    NONE_RECORD, EXPLANATION)
        # The spike's order: the cf-bounce records come before the Send-as (DMARC) question.
        question = result.stderr.index('Do you send as')
        for record in ('MX    cf-bounce.example.com', 'v=spf1 include:_spf.mx.cloudflare.net ~all',
                       'TXT   cf-bounce._domainkey.example.com'):
            self.assertLess(result.stderr.index(record), question)
        self.assertEqual(self.writes(), [])
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        result = self.run_tty(answer='n\ny\n')
        self.expect(result, 0, 'Cloudflare will add TXT _dmarc v=DMARC1; p=reject;', 'will then bounce')
        self.assertEqual(self.writes(), [POST])

    def test_reject_mode_states_the_bounce_risk(self):
        self.dns[DOH] = MISSING
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        result = self.run_tty('--dmarc', 'reject', answer='y\n')
        self.expect(result, 0, 'Cloudflare will add TXT _dmarc v=DMARC1; p=reject;',
                    'Mail that other services send as @example.com (such as Gmail Send-as) will then bounce',
                    'Cloudflare adds v=DMARC1; p=reject;')
        self.assertEqual(self.writes(), [POST])

    def test_existing_record_is_reported_and_kept_in_every_mode(self):
        self.dns[DOH] = {'Status': 0, 'Answer': [{'type': 16, 'data': '"v=DMARC1; " "p=quarantine; rua=x"'}]}
        self.save()
        for mode in ('auto', 'none', 'reject'):
            with self.subTest(mode=mode):
                self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
                self.save()
                self.api.counts.clear()
                result = self.run_tty('--dmarc', mode, answer='y\n')
                self.expect(result, 0, 'policy p=quarantine', 'keeps an existing DMARC record unchanged')
                self.assertNotIn('Do you send as', result.stderr)
                self.assertNotIn('p=reject;', result.stderr)

    def test_doh_failures_fail_closed(self):
        for answer in ({'_status': 500, '_body': 'oops'}, {'Status': 2}, {'_body': '<html>'},
                       {'Status': 0, 'Answer': [{'type': 16, 'data': '"v=DMARC1; p=none"'},
                                                {'type': 16, 'data': '"v=DMARC1; p=reject"'}]}):
            for mode in ('none', 'reject', 'auto'):
                with self.subTest(answer=answer, mode=mode):
                    self.dns[DOH] = answer
                    self.save()
                    result = self.run_tty('--dmarc', mode, answer='y\ny\n')
                    self.expect(result, 1, 'could not read _dmarc.example.com from public DNS', 'nothing was changed')
        self.assertEqual(self.writes(), [])

    def test_doh_override_is_loopback_only(self):
        for url in ('http://127.0.0.1:1@evil.example/dns-query', 'https://cloudflare-dns.com/dns-query',
                    'http://example.com:80/dns-query', 'http://127.0.0.1/dns-query', 'http://127.0.0.1:x/'):
            with self.subTest(url=url):
                result = self.run_tty('--dmarc', 'none', answer='y\n', env={'CMAIL_DOH_URL': url})
                self.expect(result, 3, 'CMAIL_DOH_URL must be a loopback http:// URL')
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.read(self.doh_calls), [])

    def test_lookup_sends_no_credential(self):
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        self.expect(self.run_tty(answer='y\n'), 0)
        self.assertEqual(self.read(self.doh_auth), ['GET ' + DOH + ' none'])


class Tokens(Sending):
    def test_main_token_never_reaches_sending_routes(self):
        self.fixtures[LIST] = {'_sequence': [ok([]), ok([entry(True)])]}
        self.save()
        self.expect(self.run_tty(answer='y\n'), 0, 'Email Sending enabled for example.com')
        lines = self.read(self.auth)
        sending = [line for line in lines if '/email/sending/' in line]
        self.assertEqual(len(sending), len(lines))
        self.assertGreaterEqual(len(sending), 4)
        for line in sending:
            self.assertTrue(line.endswith(' ' + bearer(SEND)), line)
            self.assertNotIn(bearer(MAIN), line)

    def test_same_token_for_both_keys_is_refused(self):
        self.write_config(BASE + 'CF_SENDING_TOKEN=' + MAIN + '\n')
        self.expect(self.run_tty(answer='y\n'), 3, 'CF_SENDING_TOKEN must be a separate sending-only token')
        self.assertEqual(self.read(self.calls), [])

    def test_guided_token_shows_one_permission_row_and_verifies(self):
        self.write_config(BASE)
        self.fixtures[LIST] = {'_sequence': [fail(403, 10102), ok([entry(True)])]}
        self.save()
        result = self.run_tty(answer=MAIN + '\nwrong-token\n' + SEND + '\n')
        self.expect(result, 0, 'that is CLOUDFLARE_API_TOKEN', 'sending token lacks permission',
                    'sending token verified and saved', 'sending already enabled for example.com',
                    'https://dash.cloudflare.com/profile/api-tokens')
        rows = result.stderr.split('Permissions (one row):\n')[1].split('\n  3.')[0]
        self.assertEqual([row.strip() for row in rows.splitlines() if row.strip()], ['Email Sending · Edit'])
        self.assertIn('Account Resources: Include -> <the account that owns example.com>', result.stderr)
        self.assertIn('Zone Resources:    Include -> Specific zone -> example.com', result.stderr)
        self.assertIn("CF_SENDING_TOKEN='" + SEND + "'", self.config.read_text())
        self.assertIn('CLOUDFLARE_API_TOKEN=' + MAIN, self.config.read_text())
        for line in self.read(self.auth):
            self.assertNotIn(bearer(MAIN), line)
        self.assertEqual([line.split()[-1] for line in self.read(self.auth)],
                         [bearer('wrong-token'), bearer(SEND), bearer(SEND)])


class Modes(Sending):
    def test_without_a_terminal_it_refuses_before_any_call(self):
        for args in ([], ['--dmarc', 'auto'], ['--dmarc', 'none'], ['--dmarc', 'reject']):
            for stdin in ('', 'y\n'):
                with self.subTest(args=args, stdin=stdin):
                    result = self.run_pipe('sending', 'enable', *args, stdin=stdin)
                    self.expect(result, 2, 'requires terminal')
                    if args in ([], ['--dmarc', 'auto']):
                        self.assertIn('pass --dmarc none or --dmarc reject', result.stderr)
                    else:
                        # The mode is already chosen; only the confirmation needs a terminal.
                        self.assertIn('run it in a terminal, or add --dry-run', result.stderr)
                        self.assertNotIn('pass --dmarc', result.stderr)
        self.write_config(BASE)
        self.expect(self.run_pipe('sending', 'enable'), 2, 'requires terminal')
        self.assertEqual(self.read(self.calls), [])
        self.assertEqual(self.read(self.doh_calls), [])

    def test_dry_run_makes_no_writes_and_supports_json(self):
        self.dns[DOH] = MISSING
        self.save()
        result = self.run_pipe('sending', 'enable', '--dry-run')
        self.expect(result, 0, 'dmarc', 'a real run asks whether you send as @example.com elsewhere')
        result = self.run_pipe('--format', 'json', 'sending', 'enable', '--dry-run', '--dmarc', 'none')
        self.expect(result, 0)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope['command'], 'sending enable')
        data = envelope['data']
        self.assertTrue(data['dry_run'])
        self.assertEqual(data['dmarc']['state'], 'missing')
        self.assertEqual([a['name'] for a in data['actions']], ['token', 'sending', 'records', 'dmarc'])
        self.assertEqual(data['actions'][3]['state'], 'blocked')
        self.assertEqual(len(data['blockers']), 1)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.read(self.sleeps), [])

    def test_dry_run_without_a_token_checks_dns_only(self):
        self.write_config(BASE + 'DRY_RUN=1\n')
        result = self.run_pipe('--format', 'json', 'sending', 'enable')
        self.expect(result, 0)
        data = json.loads(result.stdout)['data']
        self.assertEqual(data['actions'][0]['state'], 'blocked')
        self.assertEqual(data['dmarc']['state'], 'present')
        self.assertEqual(self.read(self.calls), [])

    def test_json_needs_dry_run_and_setup_values(self):
        self.expect(self.run_pipe('--format', 'json', 'sending', 'enable'), 2, 'requires --dry-run')
        self.write_config(BASE.replace('CF_ZONE_ID=' + ZONE + '\n', '') + 'CF_SENDING_TOKEN=' + SEND + '\n')
        self.expect(self.run_pipe('sending', 'enable', '--dry-run'), 0, 'CF_ZONE_ID is not set.',
                    'Run cmail setup first.')
        self.expect(self.run_tty(), 3, 'run cmail setup first')
        self.assertEqual(self.read(self.calls), [])

    def test_dry_run_reports_missing_setup_values_as_blocked(self):
        self.write_config(BASE.replace('CF_ZONE_ID=' + ZONE + '\n', '') + 'CF_SENDING_TOKEN=' + SEND + '\n')
        result = self.run_pipe('--format', 'json', 'sending', 'enable', '--dry-run')
        self.expect(result, 0)
        data = json.loads(result.stdout)['data']
        actions = {a['name']: a for a in data['actions']}
        self.assertEqual(actions['config']['state'], 'blocked')
        self.assertIn('CF_ZONE_ID is not set.', data['blockers'])
        self.assertEqual(actions['sending']['state'], 'manual')
        self.assertEqual(data['domain'], 'example.com')
        self.assertEqual(data['dmarc']['state'], 'present')
        self.assertEqual(self.read(self.calls), [])
        self.doh_calls.unlink()
        self.write_config('CLOUDFLARE_API_TOKEN=' + MAIN + '\n')
        result = self.run_pipe('--format', 'json', 'sending', 'enable', '--dry-run')
        self.expect(result, 0)
        data = json.loads(result.stdout)['data']
        self.assertIsNone(data['domain'])
        self.assertEqual(sorted(data['blockers']), ['CF_SENDING_TOKEN is not set.', 'DOMAIN and CF_ZONE_ID are not set.'])
        self.assertEqual({a['name']: a['state'] for a in data['actions']},
                         {'config': 'blocked', 'token': 'blocked', 'sending': 'manual', 'dmarc': 'manual'})
        self.assertEqual(self.read(self.calls), [])
        self.assertEqual(self.read(self.doh_calls), [])


class ReceiveHints(Sending):
    """The Cf::request split keeps the receive-token hints byte-identical."""

    def status(self, **fixtures):
        self.fixtures = {
            '/zones/' + ZONE: ok({'id': ZONE, 'name': 'example.com', 'status': 'active', 'account': {'id': ACCOUNT}}),
            '/zones/' + ZONE + '/email/routing': ok({'enabled': True, 'status': 'ready'}),
            '/accounts/' + ACCOUNT + '/email/routing/addresses?per_page=50&page=1': ok([]),
            '/zones/' + ZONE + '/email/routing/rules?per_page=50&page=1': ok([]),
        }
        self.fixtures.update(fixtures)
        self.save()
        return self.run_pipe('status')

    def test_rate_limit_service_and_permission_hints(self):
        zone = '/zones/' + ZONE
        self.expect(self.status(**{zone: fail(429, 10000)}), 1,
                    'Cloudflare rate limit reached — wait before rerunning cmail setup')
        self.expect(self.status(**{zone: fail(503, 10000)}), 1,
                    'Cloudflare service error — check https://www.cloudflarestatus.com/ and retry later; inspect '
                    'the dashboard first if a write was attempted')
        self.expect(self.status(**{zone + '/email/routing/rules?per_page=50&page=1': fail(403, 10000)}), 1,
                    'check token access to this zone and grant Zone > Email Routing Rules > Edit',
                    'Cloudflare API error: GET ' + zone + '/email/routing/rules?per_page=50&page=1 (HTTP 403)')

    def test_transport_failure_hint(self):
        result = self.run_pipe('status', env={'CMAIL_CF_API': 'http://127.0.0.1:9/client/v4'})
        self.expect(result, 1, 'check your connection, DNS, proxy and https://www.cloudflarestatus.com/; this is '
                               'not evidence of an invalid token', 'Cloudflare request failed: GET /zones/' + ZONE)


if __name__ == '__main__':
    unittest.main()
