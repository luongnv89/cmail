#!/usr/bin/env python3
"""`cmail notify` through the binary. Cloudflare is a loopback fixture server and the
credentials are synthetic. Nothing leaves the host."""
import json
import os
from pathlib import Path
import pty
import socket
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_server import FixtureServer  # noqa: E402
from sending_test import ACCOUNT, BIN, MAIN, SEND, ZONE, bearer, entry, fail, ok  # noqa: E402

SETTINGS = {'DOMAIN': 'example.com', 'DEST_EMAIL': 'owner@example.net', 'ADDRESSES': 'hello',
            'CLOUDFLARE_API_TOKEN': MAIN, 'CF_SENDING_TOKEN': SEND, 'GDDY_ENV': 'prod', 'CF_ZONE_ID': ZONE}
SCRUB = ('DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'NOTIFY_FROM', 'CLOUDFLARE_API_TOKEN', 'CF_SENDING_TOKEN', 'REGISTRAR',
         'GDDY_ENV', 'GDDY_PAT', 'CF_ZONE_ID', 'CF_ACCOUNT_ID', 'DRY_RUN', 'ENV_FILE', 'NO_COLOR', 'FORCE_COLOR',
         'BROWSER')
OTHER_ACCOUNT = 'c' * 32
ZONE_PATH = '/zones/' + ZONE
LOOKUP = '/zones?name=example.com'
ADDRESSES = '/accounts/' + ACCOUNT + '/email/routing/addresses?per_page=50&page=1'
LIST = '/zones/' + ZONE + '/email/sending/subdomains?per_page=50&page=1'
SEND_PATH = '/accounts/' + ACCOUNT + '/email/sending/send'
SEND_KEY = 'POST ' + SEND_PATH
VERIFIED = '2026-01-01T00:00:00Z'
DELIVERED = {'message_id': 'msg-1', 'delivered': ['owner@example.net'], 'permanent_bounces': [], 'queued': [],
             'suppressed_recipients': []}
FREE_PLAN = 'On the Workers Free plan Cloudflare sends only to verified destination addresses'
LEGACY = "using Cloudflare's legacy routing path; run cmail sending enable"
ONBOARD = 'onboard first: cmail sending enable'


def destination(email='owner@example.net', verified=VERIFIED):
    return {'id': 'd1', 'email': email, 'verified': verified, 'created': VERIFIED, 'modified': VERIFIED}


class Notify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.config = self.dir / 'config'
        self.write_config()
        self.calls, self.payloads, self.auth = self.dir / 'calls', self.dir / 'payloads', self.dir / 'auth'
        self.fixtures = {
            ZONE_PATH: ok({'id': ZONE, 'name': 'example.com', 'status': 'active', 'account': {'id': ACCOUNT}}),
            LOOKUP: ok([{'id': ZONE, 'name': 'example.com'}]),
            ADDRESSES: ok([destination()]),
            LIST: ok([entry(True)]),
            SEND_KEY: ok(DELIVERED),
        }
        self.responses = self.dir / 'responses.json'
        self.save()
        self.api = FixtureServer(str(self.responses), str(self.calls), str(self.payloads), auth_log=str(self.auth))
        self.addCleanup(self.api.close)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('CMAIL_', 'GDDY_')) and k not in SCRUB}
        self.env.update(ENV_FILE=str(self.config), CMAIL_CF_API=self.api.url, NO_COLOR='1',
                        CMAIL_DOH_URL='http://127.0.0.1:9/dns-query')

    def write_config(self, **changes):
        """The default settings with `changes` applied; None drops a key."""
        settings = dict(SETTINGS, **changes)
        self.config.write_text(''.join('%s=%s\n' % (k, v) for k, v in settings.items() if v is not None))
        self.config.chmod(0o600)

    def save(self):
        self.responses.write_text(json.dumps(self.fixtures))

    def run_notify(self, *args, stdin='', env=None, options=()):
        """`cmail OPTIONS notify ARGS` without a terminal, as cron runs it. Bytes stdin is passed raw."""
        settings = dict(self.env, **(env or {}))
        data = stdin if isinstance(stdin, bytes) else stdin.encode()
        result = subprocess.run([str(BIN), *options, 'notify', *args], input=data, capture_output=True,
                                env=settings, timeout=20)
        return self.checked(subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(),
                                                        result.stderr.decode()))

    def run_json(self, *args):
        return self.run_notify(*args, options=('--format', 'json'))

    def checked(self, result):
        text = result.stdout + result.stderr
        self.assertNotIn(MAIN, text)
        self.assertNotIn(SEND, text)
        self.assertNotIn('panicked', text)
        return result

    def read(self, path):
        return path.read_text().splitlines() if path.exists() else []

    def requests(self):
        return [line.strip() for line in self.read(self.calls)]

    def posts(self):
        return [line for line in self.requests() if not line.startswith('GET ')]

    def sent(self):
        return [json.loads(line)['body'] for line in self.read(self.payloads)]

    def expect(self, result, code, *texts):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        for text in texts:
            self.assertIn(text, result.stdout + result.stderr)

    def refused_before_any_request(self, result, code, *texts):
        self.expect(result, code, *texts)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.requests(), [])


class Success(Notify):
    def test_sends_the_default_subject_and_no_hostname(self):
        result = self.run_notify('it works')
        self.expect(result, 0)
        self.assertEqual(result.stdout, 'sent (message_id msg-1) to owner@example.net\n')
        self.assertEqual(self.sent(), [{'from': 'hello@example.com', 'to': ['owner@example.net'],
                                        'subject': 'cmail notification', 'text': 'it works'}])
        self.assertEqual(self.posts(), [SEND_KEY])
        self.assertNotIn(socket.gethostname(), self.payloads.read_text())

    def test_json_reports_message_id_delivered_and_queued(self):
        self.fixtures[SEND_KEY] = ok(dict(DELIVERED, queued=['later@example.net']))
        self.save()
        result = self.run_json('it works')
        self.expect(result, 0)
        self.assertEqual(json.loads(result.stdout), {
            'schema_version': 1, 'command': 'notify',
            'data': {'message_id': 'msg-1', 'delivered': ['owner@example.net'], 'queued': ['later@example.net']}})

    def test_the_test_command_sending_enable_prints_works(self):
        # sending enable ends with: test with cmail notify --subject "cmail test" "it works"
        self.expect(self.run_notify('--subject', 'cmail test', 'it works'), 0, 'sent (message_id msg-1)')
        self.assertEqual(self.sent()[0]['subject'], 'cmail test')
        self.assertEqual(self.sent()[0]['text'], 'it works')

    def test_stdin_body_drops_only_one_trailing_newline(self):
        body = 'backup done: 3 files\n"quoted" <b>markup</b> & héllo ✓\n'
        self.expect(self.run_notify('--stdin', stdin=body + '\n'), 0, 'sent (message_id msg-1)')
        self.assertEqual(self.sent()[0]['text'], body)

    def test_stdin_body_drops_a_trailing_crlf_as_a_unit(self):
        self.expect(self.run_notify('--stdin', stdin=b'a\r\nb\r\n'), 0, 'sent (message_id msg-1)')
        self.assertEqual(self.sent()[0]['text'], 'a\r\nb')

    def test_stdin_body_at_the_size_limit_is_sent(self):
        body = 'a' * (256 * 1024)
        for ending in ('\n', '\r\n'):
            with self.subTest(ending=ending):
                self.payloads.unlink(missing_ok=True)
                self.expect(self.run_notify('--stdin', stdin=body + ending), 0)
                self.assertEqual(self.sent()[0]['text'], body)

    def test_subject_may_contain_a_tab(self):
        self.expect(self.run_notify('--subject', 'backup\tok', 'hi'), 0)
        self.assertEqual(self.sent()[0]['subject'], 'backup\tok')

    def test_subject_at_the_length_limit_is_sent(self):
        self.expect(self.run_notify('--subject', 'é' * 998, 'hi'), 0)
        self.assertEqual(self.sent()[0]['subject'], 'é' * 998)

    def test_to_overrides_dest_email_and_matches_case_insensitively(self):
        self.fixtures[ADDRESSES] = ok([destination(), destination('OTHER@example.org')])
        self.save()
        self.expect(self.run_notify('--to', 'Other@Example.org', 'hi'), 0, 'to Other@Example.org')
        self.assertEqual(self.sent()[0]['to'], ['Other@Example.org'])

    def test_from_flag_beats_notify_from_beats_first_address(self):
        cases = [({'ADDRESSES': 'contact,hello'}, [], 'contact@example.com'),
                 ({'ADDRESSES': 'contact,hello', 'NOTIFY_FROM': 'alerts'}, [], 'alerts@example.com'),
                 ({'ADDRESSES': 'contact,hello', 'NOTIFY_FROM': 'alerts'}, ['--from', 'ops'], 'ops@example.com')]
        for settings, args, sender in cases:
            with self.subTest(sender=sender):
                self.payloads.unlink(missing_ok=True)
                self.write_config(**settings)
                self.expect(self.run_notify(*args, 'hi'), 0)
                self.assertEqual(self.sent()[0]['from'], sender)
        # NOTIFY_FROM from the environment overrides the file, like every other key.
        self.payloads.unlink()
        self.expect(self.run_notify('hi', env={'NOTIFY_FROM': 'cron'}), 0)
        self.assertEqual(self.sent()[0]['from'], 'cron@example.com')


class Recipient(Notify):
    def test_unregistered_recipient_is_refused_before_any_send(self):
        self.fixtures[ADDRESSES] = ok([destination('someone@example.org')])
        self.save()
        result = self.run_notify('hi')
        self.expect(result, 3, 'owner@example.net is not a Cloudflare destination address', FREE_PLAN,
                    'cmail forward or cmail setup')
        self.assertEqual(self.posts(), [])
        self.assertEqual(result.stdout, '')

    def test_unverified_recipient_is_refused_before_any_send(self):
        self.fixtures[ADDRESSES] = ok([destination(verified=None)])
        self.save()
        result = self.run_notify('hi')
        self.expect(result, 3, 'owner@example.net is registered but not verified yet', FREE_PLAN,
                    'verification link')
        self.assertEqual(self.posts(), [])

    def test_mixed_case_entries_match_and_the_last_one_wins(self):
        self.fixtures[ADDRESSES] = ok([destination('OWNER@Example.NET')])
        self.save()
        self.expect(self.run_notify('hi'), 0)
        self.fixtures[ADDRESSES] = ok([destination(), destination('Owner@example.net', None)])
        self.save()
        self.expect(self.run_notify('hi'), 3, 'registered but not verified yet')
        self.assertEqual(self.posts(), [SEND_KEY])

    def test_destination_list_failure_sends_nothing(self):
        self.fixtures[ADDRESSES] = fail(403, 10000)
        self.save()
        self.expect(self.run_notify('hi'), 1, 'Email Routing Addresses', 'HTTP 403')
        self.assertEqual(self.posts(), [])

    def test_without_the_main_token_the_check_is_skipped_with_a_warning(self):
        self.write_config(CLOUDFLARE_API_TOKEN=None, CF_ACCOUNT_ID=ACCOUNT)
        result = self.run_notify('hi')
        self.expect(result, 0, "CLOUDFLARE_API_TOKEN is not set, so cmail can't check that owner@example.net is a "
                               'verified destination address', '10208')
        self.assertEqual(result.stdout, 'sent (message_id msg-1) to owner@example.net\n')
        for line in self.requests():
            self.assertNotIn('/email/routing/', line)
            self.assertFalse(line.split()[1].startswith('/zones?') or line.split()[1] == ZONE_PATH, line)
        self.assertEqual(self.posts(), [SEND_KEY])


class Account(Notify):
    def test_saved_account_id_skips_the_zone_read(self):
        self.write_config(CF_ACCOUNT_ID=OTHER_ACCOUNT)
        self.fixtures['/accounts/' + OTHER_ACCOUNT + '/email/routing/addresses?per_page=50&page=1'] = ok([destination()])
        self.fixtures['POST /accounts/' + OTHER_ACCOUNT + '/email/sending/send'] = ok(DELIVERED)
        self.save()
        self.expect(self.run_notify('hi'), 0)
        self.assertNotIn('GET ' + ZONE_PATH, self.requests())
        self.assertEqual(self.posts(), ['POST /accounts/' + OTHER_ACCOUNT + '/email/sending/send'])

    def test_account_comes_from_the_zone_with_the_main_token(self):
        self.expect(self.run_notify('hi'), 0)
        self.assertIn('GET ' + ZONE_PATH + ' ' + bearer(MAIN), self.read(self.auth))
        self.assertEqual(self.posts(), [SEND_KEY])

    def test_zone_without_an_account_id_sends_nothing(self):
        self.fixtures[ZONE_PATH] = ok({'id': ZONE, 'name': 'example.com', 'status': 'active'})
        self.save()
        self.expect(self.run_notify('hi'), 1, 'Cloudflare zone is missing its account ID — nothing was sent')
        self.assertEqual(self.posts(), [])

    def test_only_the_sending_token_reaches_sending_routes(self):
        # Zone lookup by name, zone read, destination list, sending list and the send, in one run.
        self.write_config(CF_ZONE_ID='')
        self.expect(self.run_notify('hi'), 0)
        lines = self.read(self.auth)
        self.assertEqual([' '.join(line.split()[:2]) for line in lines],
                         ['GET ' + LOOKUP, 'GET ' + ZONE_PATH, 'GET ' + ADDRESSES, 'GET ' + LIST, SEND_KEY])
        for line in lines:
            token = SEND if '/email/sending/' in line else MAIN
            self.assertTrue(line.endswith(' ' + bearer(token)), line)


class Onboarding(Notify):
    def test_not_onboarded_warns_about_the_legacy_path_and_still_sends(self):
        for entries in ([], [entry(False)], [entry(True, 'other.example')]):
            with self.subTest(entries=entries):
                self.calls.unlink(missing_ok=True)
                self.fixtures[LIST] = ok(entries)
                self.save()
                result = self.run_notify('hi')
                self.expect(result, 0, 'example.com is not onboarded to Email Sending — ' + LEGACY)
                self.assertEqual(self.posts(), [SEND_KEY])

    def test_onboarded_domain_gets_no_warning(self):
        result = self.run_notify('hi')
        self.expect(result, 0)
        self.assertEqual(result.stderr, '')

    def test_not_onboarded_then_403_or_404_says_onboard_first(self):
        self.fixtures[LIST] = ok([])
        for response in (fail(403, 10999), fail(404, 10000)):
            with self.subTest(status=response['_status']):
                self.fixtures[SEND_KEY] = response
                self.save()
                self.expect(self.run_notify('hi'), 1, LEGACY, ONBOARD, 'HTTP %d' % response['_status'])

    def test_onboard_hint_needs_a_known_missing_entry(self):
        self.fixtures[SEND_KEY] = fail(403, 10102)
        for listing in (ok([entry(True)]), fail(500, 10002)):
            with self.subTest(listing=listing):
                self.fixtures[LIST] = listing
                self.save()
                result = self.run_notify('hi')
                self.expect(result, 1, 'sending token lacks permission')
                self.assertNotIn(ONBOARD, result.stderr)
        self.fixtures[LIST] = ok([])
        self.fixtures[SEND_KEY] = fail(429, 10004)
        self.save()
        self.assertNotIn(ONBOARD, self.run_notify('hi').stderr)

    def test_documented_403_codes_never_add_onboard_first(self):
        # Not onboarded, but Cloudflare's own code explains the refusal: its hint alone is the answer.
        self.fixtures[LIST] = ok([])
        cases = [(10208, 'owner@example.net is not a verified destination address'),
                 (10102, 'sending token lacks permission'),
                 (10105, 'not entitled to Email Sending')]
        for code, hint in cases:
            with self.subTest(code=code):
                self.fixtures[SEND_KEY] = fail(403, code)
                self.save()
                result = self.run_notify('hi')
                self.expect(result, 1, LEGACY, hint, 'HTTP 403 with error code %d' % code)
                self.assertNotIn(ONBOARD, result.stderr)

    def test_unreadable_sending_list_warns_and_still_sends(self):
        cases = [(ok([{'tag': 't1', 'enabled': True}]), 'sending subdomain without a name — trying the send anyway'),
                 (ok([{'tag': 't1', 'name': 'example.com'}]), 'without a valid enabled state'),
                 ({'success': True}, 'missing result'),
                 (fail(403, 10102), "couldn't read the Email Sending list (GET " + LIST +
                  ': HTTP 403 with error code 10102) — trying the send anyway'),
                 ({'_drop': True}, "couldn't read the Email Sending list (GET " + LIST)]
        for listing, text in cases:
            with self.subTest(text=text):
                self.calls.unlink(missing_ok=True)
                self.fixtures[LIST] = listing
                self.save()
                result = self.run_notify('hi')
                self.expect(result, 0, text, 'sent (message_id msg-1)')
                self.assertNotIn(LEGACY, result.stderr)
                self.assertEqual(self.posts(), [SEND_KEY])

    def test_without_a_zone_or_main_token_it_still_sends_with_warnings(self):
        self.write_config(CF_ZONE_ID='', CLOUDFLARE_API_TOKEN=None, CF_ACCOUNT_ID=ACCOUNT)
        result = self.run_notify('hi')
        self.expect(result, 0, "CF_ZONE_ID is not set, so cmail can't check whether example.com is onboarded",
                    "can't check that owner@example.net is a verified destination address")
        self.assertEqual(self.requests(), [SEND_KEY])
        self.assertNotIn('//', self.requests()[0])


class Errors(Notify):
    def send_fails(self, response):
        self.fixtures[SEND_KEY] = response
        self.save()
        return self.run_notify('hi')

    def test_each_documented_code_gets_its_message(self):
        cases = [
            (fail(401, 10101), 'sending token rejected — replace CF_SENDING_TOKEN'),
            (fail(401, 10103), "Cloudflare says this token type can't send"),
            (fail(403, 10102), 'sending token lacks permission — grant Email Sending · Edit for the account that '
                               'owns example.com'),
            (fail(403, 10105), 'not entitled to Email Sending'),
            (fail(403, 10203), 'sending is disabled or paused'),
            (fail(403, 10207), 'sending is disabled or paused'),
            (fail(403, 10208), 'owner@example.net is not a verified destination address. On the Workers Free plan '
                               'Cloudflare only sends to verified destinations'),
            (fail(429, 10004), 'Cloudflare sending limit reached (rate or daily quota) — retry later'),
            (fail(400, 10001, message='Recipient is suppressed'),
             'Cloudflare suppressed owner@example.net after a bounce or complaint — check Compute > Email Service > '
             'Email Sending > Suppressions; hard bounces expire after 7 days'),
            (fail(503, 10100), 'Cloudflare service error — check https://www.cloudflarestatus.com/ and retry later'),
        ]
        for response, hint in cases:
            with self.subTest(hint=hint):
                status, code = response['_status'], response['errors'][0]['code']
                result = self.send_fails(response)
                self.expect(result, 1, hint, 'Cloudflare API error: POST %s (HTTP %d with error code %d)'
                            % (SEND_PATH, status, code))
                self.assertEqual(result.stdout, '')
                self.assertNotIn('cmail setup', result.stderr)

    def test_unknown_code_shows_the_status_and_code(self):
        result = self.send_fails(fail(418, 99999))
        self.expect(result, 1, 'Cloudflare answered HTTP 418 with error code 99999, which cmail does not recognise')

    def test_a_bare_400_is_not_called_a_suppression(self):
        result = self.send_fails(fail(400, 10001, message='email.sending.error.invalid_request_schema'))
        self.expect(result, 1, 'HTTP 400 with error code 10001')
        self.assertNotIn('suppressed', result.stderr)

    def test_dropped_connection_is_a_failure_with_unknown_outcome(self):
        result = self.send_fails({'_drop': True})
        self.expect(result, 1, 'Cloudflare request failed: POST ' + SEND_PATH, 'write outcome is unknown')

    def test_both_tokens_are_redacted(self):
        result = self.send_fails(fail(403, 10102, message='bad ' + SEND + ' and ' + MAIN))
        self.expect(result, 1, 'bad [redacted] and [redacted]')


class Answers(Notify):
    def answer(self, result, *args):
        self.fixtures[SEND_KEY] = result if isinstance(result, dict) and 'success' in result else ok(result)
        self.save()
        return self.run_notify(*args, 'hi')

    def test_missing_message_id_with_a_queued_recipient_still_succeeds(self):
        result = self.answer({'queued': ['owner@example.net']})
        self.expect(result, 0)
        self.assertEqual(result.stdout, 'sent (message_id unknown) to owner@example.net\n')
        result = self.run_json('hi')
        self.assertEqual(json.loads(result.stdout)['data'],
                         {'message_id': None, 'delivered': [], 'queued': ['owner@example.net']})

    def test_mistyped_fields_read_as_absent(self):
        result = self.answer({'message_id': 7, 'delivered': 'owner@example.net', 'queued': ['owner@example.net', 3]})
        self.expect(result, 0, 'sent (message_id unknown)')
        self.assertEqual(json.loads(self.run_json('hi').stdout)['data'],
                         {'message_id': None, 'delivered': [], 'queued': ['owner@example.net']})

    def test_no_delivered_or_queued_recipient_is_a_failure(self):
        for answer in ({}, None, [], {'message_id': 'msg-1'}, {'delivered': [None, 1], 'queued': []},
                       {'success': True}, {'success': True, 'result': 'ok'}):
            with self.subTest(answer=answer):
                result = self.answer(answer)
                self.expect(result, 1, 'Cloudflare accepted the request but reported no delivered or queued recipient')
                self.assertEqual(result.stdout, '')

    def test_suppressed_or_bounced_recipients_are_named(self):
        result = self.answer(dict(DELIVERED, delivered=[], suppressed_recipients=['owner@example.net']))
        self.expect(result, 1, 'Cloudflare suppressed owner@example.net after a bounce or complaint',
                    'hard bounces expire after 7 days')
        result = self.answer(dict(DELIVERED, delivered=[], permanent_bounces=['owner@example.net']))
        self.expect(result, 1, 'Cloudflare reported a permanent bounce for owner@example.net')


class Refusals(Notify):
    def test_configuration_problems_exit_3_before_any_request(self):
        cases = [
            ({'CF_SENDING_TOKEN': None}, [], 'CF_SENDING_TOKEN is not set — run cmail sending enable'),
            ({'CF_SENDING_TOKEN': MAIN}, [], 'CF_SENDING_TOKEN must be a separate sending-only token'),
            ({'DEST_EMAIL': None}, [], 'no recipient — pass --to EMAIL, or set DEST_EMAIL'),
            ({'DOMAIN': None}, [], 'DOMAIN is required'),
            ({'ADDRESSES': "''"}, [], 'no sender — pass --from LOCAL, or set NOTIFY_FROM or ADDRESSES'),
            ({'NOTIFY_FROM': 'a@b.com'}, [], 'NOTIFY_FROM has an invalid value'),
            ({'CF_ZONE_ID': '', 'CLOUDFLARE_API_TOKEN': None}, [],
             'set CF_ACCOUNT_ID, or CLOUDFLARE_API_TOKEN and CF_ZONE_ID (run cmail setup)'),
            ({'CLOUDFLARE_API_TOKEN': None}, [],
             'set CF_ACCOUNT_ID, or CLOUDFLARE_API_TOKEN and CF_ZONE_ID (run cmail setup)'),
        ]
        for settings, args, text in cases:
            with self.subTest(text=text):
                self.write_config(**settings)
                self.refused_before_any_request(self.run_notify(*args, 'hi'), 3, text)

    def test_usage_errors_exit_2_before_any_request(self):
        cases = [
            ([], 'notify needs MESSAGE, or --stdin'),
            (['hi', '--stdin'], 'cannot be used with'),
            (['--to', 'not-an-email', 'hi'], '--to must be an email address'),
            (['--to', 'a@b', 'hi'], '--to must be an email address'),
            (['--from', 'hello@example.com', 'hi'], '--from must be a local part'),
            (['--from', '.hello', 'hi'], '--from must be a local part'),
            (['--subject', 'two\nlines', 'hi'], '--subject must be a single line'),
            (['--subject', 'Bcc: x\r', 'hi'], '--subject must be a single line'),
            (['--subject', 'é' * 999, 'hi'], '--subject must be at most 998 characters'),
            (['--subject', 'a\u2028b', 'hi'], '--subject must be a single line'),
            (['--subject', 'a\u2029b', 'hi'], '--subject must be a single line'),
            (['--subject', 'bell\x07', 'hi'], '--subject must be printable text'),
            (['--subject', 'tab\x0bvt', 'hi'], '--subject must be printable text'),
            (['--subject', '\x1b[31mred', 'hi'], '--subject must be printable text'),
            (['--subject', 'del\x7f', 'hi'], '--subject must be printable text'),
            (['--subject', 'nel\u0085', 'hi'], '--subject must be printable text'),
            (['--subject', '   ', 'hi'], '--subject must not be blank'),
            (['--subject', '\t', 'hi'], '--subject must not be blank'),
            ([''], 'a value is required'),
            (['--subject', '', 'hi'], 'a value is required'),
            (['hi', 'extra'], 'unexpected argument'),
            (['hi', '--dry-run'], 'unexpected argument'),
        ]
        for args, text in cases:
            with self.subTest(args=args):
                self.refused_before_any_request(self.run_notify(*args), 2, text)

    def test_stdin_on_a_terminal_is_refused_before_reading(self):
        master, slave = pty.openpty()
        try:
            proc = subprocess.run([str(BIN), 'notify', '--stdin'], stdin=slave, capture_output=True, text=True,
                                  env=self.env, timeout=20)
        finally:
            os.close(slave)
            os.close(master)
        self.refused_before_any_request(self.checked(proc), 2, '--stdin needs piped input')

    def test_bad_message_bodies_exit_3_before_any_request(self):
        cases = [(b'', 'the message is empty'), (b'\n', 'the message is empty'), (b'  \n\t\n', 'the message is empty'),
                 (b'ab\x00cd', 'stdin must be UTF-8 text without NUL, at most 262144 bytes'),
                 (b'caf\xe9\n', 'stdin must be UTF-8 text without NUL'),
                 (b'a' * (256 * 1024 + 1), 'at most 262144 bytes'),
                 (b'a' * (256 * 1024) + b'\n\n', 'at most 262144 bytes'),
                 (b'a' * (256 * 1024) + b'\r\nx', 'at most 262144 bytes'),
                 (b'a' * (256 * 1024) + b'\r\n\r\n', 'at most 262144 bytes')]
        for stdin, text in cases:
            with self.subTest(stdin=stdin[:12], size=len(stdin)):
                self.refused_before_any_request(self.run_notify('--stdin', stdin=stdin), 3, text)
        self.refused_before_any_request(self.run_notify('   '), 3, 'the message is empty')


if __name__ == '__main__':
    unittest.main()
