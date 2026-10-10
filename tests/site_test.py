#!/usr/bin/env python3
"""Offline site/document contract checks; no provider calls or third-party packages."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
IDS = ['ready', 'install', 'token', 'nameservers', 'setup', 'verify', 'test', 'send']
PAGES = ['index.html', 'setup.html', 'docs.html', 'changelog.html', 'privacy.html']


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.elements = []
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class SiteTests(unittest.TestCase):
    def test_local_links_and_assets_exist_and_anchors_resolve(self):
        for filename in PAGES:
            page = Page(ROOT / 'docs' / filename)
            for tag, attrs in page.elements:
                for attribute in ['href', 'src']:
                    if attribute not in attrs:
                        continue
                    link = urlsplit(attrs[attribute])
                    if link.scheme or link.netloc:
                        self.assertEqual(link.scheme, 'https')
                        continue
                    target = (page.path.parent / unquote(link.path)).resolve() if link.path else page.path
                    self.assertTrue(target.is_file(), f'{filename}: {attrs[attribute]}')
                    if link.fragment and target.suffix == '.html':
                        ids = {a.get('id') for _, a in Page(target).elements}
                        self.assertIn(unquote(link.fragment), ids)

    def test_native_enabled_checkboxes_and_labels(self):
        page = Page(ROOT / 'docs/setup.html')
        inputs = [a for tag, a in page.elements if tag == 'input']
        self.assertEqual([a['id'] for a in inputs], ['step-' + x for x in IDS])
        labels = {a.get('for') for tag, a in page.elements if tag == 'label'}
        for attrs in inputs:
            self.assertEqual(attrs['type'], 'checkbox')
            self.assertNotIn('disabled', attrs)
            self.assertNotIn('tabindex', attrs)
            self.assertIn(attrs['id'], labels)
        self.assertFalse(any(tag in ['form', 'textarea'] for tag, _ in page.elements))

    def test_unique_ids_landmarks_and_nojs_fallback(self):
        for name in PAGES:
            page = Page(ROOT / 'docs' / name)
            ids = [a['id'] for _, a in page.elements if 'id' in a]
            self.assertEqual(len(ids), len(set(ids)))
            for tag in ['html', 'main', 'header', 'nav', 'footer']:
                self.assertTrue(any(t == tag for t, _ in page.elements))
            html_attrs = next(a for t, a in page.elements if t == 'html')
            self.assertEqual(html_attrs['lang'], 'en')
            self.assertEqual(sum(t == 'h1' for t, _ in page.elements), 1)
        page = Page(ROOT / 'docs/setup.html')
        panel = next(a for _, a in page.elements if a.get('id') == 'progress-panel')
        self.assertIn('hidden', panel)
        self.assertTrue(any(t == 'noscript' for t, _ in page.elements))
        reset = next(a for _, a in page.elements if a.get('id') == 'reset-progress')
        self.assertEqual(reset['type'], 'button')

    def test_order_matches_markdown_and_script(self):
        html = (ROOT / 'docs/setup.html').read_text()
        positions = [html.index('class="step" id="' + x + '"') for x in IDS]
        self.assertEqual(positions, sorted(positions))
        md = (ROOT / 'docs/setup.md').read_text()
        self.assertEqual(re.findall(r'^### (\d+)\.', md, re.M), [str(x) for x in range(1, len(IDS) + 1)])
        self.assertEqual(len(re.findall(r'^- \[ \]', md, re.M)), len(IDS))
        js = (ROOT / 'docs/assets/checklist.js').read_text()
        for step in IDS:
            self.assertIn("'" + step + "'", js)
        # The overall stepper links every step, in order, and its done-state CSS covers each one.
        stepper = re.search(r'<ol class="stepper">(.*?)</ol>', html, re.S).group(1)
        self.assertEqual(re.findall(r'href="#([a-z]+)"', stepper), IDS)
        css = (ROOT / 'docs/assets/styles.css').read_text()
        for step in IDS:
            self.assertIn('#step-%s:checked) .stepper a[href="#%s"]' % (step, step), css)

    def test_issue26_cloudflare_domain_step_comes_before_setup_and_is_conditional(self):
        html = (ROOT / 'docs/setup.html').read_text()
        self.assertLess(html.index('id="nameservers"'), html.index('class="step" id="setup"'))
        step = re.search(r'<li class="step" id="nameservers">(.*?)</li>\s*<!-- 5 -->', html, re.S).group(1)
        self.assertIn('<span class="num">4</span>', step)
        text = ' '.join(unescape(re.sub(r'<[^>]+>', '', step)).split())
        for value in ['If needed: add your domain to Cloudflare',
                      'Only needed if your domain is not on Cloudflare yet.',
                      'Cloudflare dashboard → Domains → Add a domain',
                      'Follow Cloudflare’s instructions to switch nameservers at your current registrar']:
            self.assertIn(value, text)
        self.assertIn('href="https://dash.cloudflare.com/"', step)
        js = (ROOT / 'docs/assets/checklist.js').read_text()
        allowlist = re.search(r'const IDS = Object\.freeze\(\[(.*?)\]\)', js, re.S).group(1)
        self.assertEqual(re.findall(r"'([a-z]+)'", allowlist), IDS)
        setup = re.search(r'<li class="step" id="setup">(.*?)<!-- 6 -->', html, re.S).group(1)
        self.assertIn('<span class="num">5</span>', setup)
        stepper = re.search(r'<ol class="stepper">(.*?)</ol>', html, re.S).group(1)
        self.assertIn('<span class="num">4</span><span class="opt">Add domain (if needed)</span>', stepper)
        self.assertIn('<span class="num">5</span>Run setup', stepper)
        # Cross-references follow the new numbering: the nameserver step is 4, setup is 5.
        flat = unescape(re.sub(r'<[^>]+>', '', html))
        self.assertIn('copy them into Cloudflare in step 4', flat)
        self.assertIn('… see step 4 …', flat)
        self.assertNotIn('steps 5 and 6', flat)
        self.assertNotIn('see step 5', flat)
        md = (ROOT / 'docs/setup.md').read_text()
        self.assertIn('4 Add domain (if needed) → 5 Run setup', md)
        self.assertLess(md.index('### 4. If needed: add your domain to Cloudflare'),
                        md.index('### 5. Run `cmail setup`'))
        for value in ['**Only needed if your domain is not on Cloudflare yet.**',
                      '**Domains** → **Add a domain**',
                      "Follow Cloudflare's instructions to switch nameservers at your current registrar",
                      'DNS records now (step 4)']:
            self.assertIn(value, md)

    def test_issue27_completion_card_asks_for_a_github_star(self):
        page = Page(ROOT / 'docs/setup.html')
        card = next(a for _, a in page.elements if a.get('id') == 'setup-complete')
        self.assertIn('hidden', card)  # shown only by checklist.js once every step is ticked
        html = (ROOT / 'docs/setup.html').read_text()
        self.assertLess(html.index('class="step" id="send"'), html.index('id="setup-complete"'))
        section = re.search(r'<section id="setup-complete"(.*?)</section>', html, re.S).group(1)
        self.assertIn('href="https://github.com/luongnv89/cmail"', section)
        text = unescape(re.sub(r'<[^>]+>', '', section))
        self.assertIn('Congratulations', text)
        self.assertIn('Star cmail on GitHub', text)
        self.assertIn("'#setup-complete'", (ROOT / 'docs/assets/checklist.js').read_text())
        md = (ROOT / 'docs/setup.md').read_text()
        self.assertIn('[star the project on GitHub](https://github.com/luongnv89/cmail)', md)

    def test_every_page_links_every_page(self):
        for name in PAGES:
            hrefs = {a.get('href') for t, a in Page(ROOT / 'docs' / name).elements if t == 'a'}
            for target in PAGES:
                self.assertIn(target, hrefs, f'{name} -> {target}')
            current = [a['href'] for t, a in Page(ROOT / 'docs' / name).elements if 'aria-current' in a]
            self.assertEqual(current, [name])

    def test_repository_github_links_point_at_real_files(self):
        for filename in PAGES:
            for _, attrs in Page(ROOT / 'docs' / filename).elements:
                link = attrs.get('href', '')
                prefix = 'https://github.com/luongnv89/cmail/'
                if link.startswith(prefix + 'blob/main/') or link.startswith(prefix + 'tree/main/'):
                    path = urlsplit(link).path.split('/main/', 1)[1]
                    self.assertTrue((ROOT / unquote(path)).exists(), link)
        # Markdown fallback has real relative documentation paths.
        for link in re.findall(r'\]\(([^)]+)\)', (ROOT / 'docs/setup.md').read_text()):
            parsed = urlsplit(link)
            if not parsed.scheme:
                self.assertTrue((ROOT / 'docs' / parsed.path).resolve().exists(), link)

    def test_setup_documents_actual_contract_and_safety(self):
        for name in ['setup.html', 'setup.md']:
            text = unescape((ROOT / 'docs' / name).read_text())
            for value in ['bash install.sh --local', 'cmail config init', 'cmail setup',
                          'cmail setup --dry-run', 'cmail send-as', 'cmail list', 'cmail 0.2.0',
                          'Zone Settings', 'DNS', 'Email Routing Rules', 'Email Routing Addresses',
                          'zone already active on Cloudflare', 'DNSSEC', 'Receiving is set up',
                          'January 2027', 'Advanced Protection', '587', 'TLS', 'smtp.gmail.com',
                          'not proof', 'different']:
                self.assertIn(value, text, f'{name}: {value}')
            self.assertRegex(text, r'(?i)replace (?:<strong>|\*\*)?all(?:</strong>|\*\*)? nameservers')
            self.assertRegex(text, r'(?i)changes nothing')
        readme = (ROOT / 'README.md').read_text()
        for link in ['docs/index.html', 'docs/setup.html', 'docs/setup.md', 'docs/docs.html',
                     'docs/changelog.html', 'docs/privacy.html',
                     'node --test tests/checklist_test.js', 'python3 tests/site_test.py']:
            self.assertIn(link, readme)

    def test_terminal_simulations_quote_real_cli_output(self):
        # Simulated sessions must not invent output: each quoted line exists in the runtime source.
        source = '\n'.join(p.read_text() for p in [ROOT / 'cmail', *sorted((ROOT / 'lib').glob('*.sh'))])
        html = unescape(re.sub(r'<[^>]+>', '', (ROOT / 'docs/setup.html').read_text()))
        for line in ['Setting up RECEIVING: your custom addresses will forward to an inbox you already use.',
                     'Cloudflare token verified and saved to .env',
                     'email routing enabled (Cloudflare routing DNS records added and locked)',
                     'still unverified — waiting (click the email link)…',
                     'zone already active on Cloudflare', 'Receiving is set up', 'Elapsed time: ',
                     'Cloudflare assigned these nameservers to', 'Setup stopped at:',
                     'email address to receive forwarded mail (any provider)',
                     'domain you already own, at any registrar (e.g. example.com)']:
            self.assertIn(line, html)
            self.assertIn(line.rstrip(), source)
        for header in re.findall(r'── ([^─]+?) ──', html):
            fixed = re.split(r'[:(]', header)[0].strip()
            self.assertIn(fixed, source, header)
        self.assertIn('Created private configuration:', source)
        version = subprocess.run([str(ROOT / 'cmail'), '--version'], cwd=ROOT,
                                 text=True, capture_output=True, timeout=5)
        self.assertEqual(version.stdout.strip(), 'cmail ' + (ROOT / 'VERSION').read_text().strip())
        self.assertIn(version.stdout.strip(), html)

    def test_cli_docs_cover_every_command_and_setting(self):
        help_result = subprocess.run([str(ROOT / 'cmail'), 'help'], cwd=ROOT,
                                     text=True, capture_output=True, timeout=5)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        commands = re.findall(r'^  ([a-z-]+)\s', help_result.stdout.split('Start here:')[0], re.M)
        self.assertIn('list', commands)
        docs = unescape((ROOT / 'docs/docs.html').read_text())
        for command in commands:
            self.assertIn('cmail ' + command, docs)
        for key in ['DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'CLOUDFLARE_API_TOKEN', 'REGISTRAR',
                    'CF_ACCOUNT_ID', 'CF_ZONE_ID', 'GDDY_ENV', 'GDDY_PAT', 'DRY_RUN',
                    '--dry-run', '--stdin', '--registrar godaddy', '--format json', '--no-browser']:
            self.assertIn(key, docs)
        for code in ['0', '1', '2', '3', '130']:
            self.assertIn('<td>%s</td>' % code, docs)

    def test_changelog_and_privacy_stay_in_sync(self):
        changelog = (ROOT / 'docs/changelog.html').read_text()
        for version in re.findall(r'^## (v\d+\.\d+\.\d+)', (ROOT / 'CHANGELOG.md').read_text(), re.M):
            self.assertIn('id="%s"' % version.replace('.', ''), changelog)
            self.assertIn('>%s</h2>' % version, changelog)
        privacy = (ROOT / 'docs/privacy.html').read_text()
        key = re.search(r"const KEY = '([^']+)'", (ROOT / 'docs/assets/checklist.js').read_text()).group(1)
        self.assertIn(key, privacy)
        for host in ['api.cloudflare.com', 'raw.githubusercontent.com']:
            self.assertIn(host, privacy)
        # The only API host the runtime calls is the one the privacy page names.
        source = '\n'.join(p.read_text() for p in [ROOT / 'cmail', *sorted((ROOT / 'lib').glob('*.sh'))])
        self.assertEqual(set(re.findall(r'https://(api\.[a-z0-9.-]+)', source)), {'api.cloudflare.com'})

    def test_issue17_quickstarts_select_feature_runtime_not_default_installer(self):
        # Issue #17: the default installer downloads its own pinned commit (the
        # v0.2.0 release), not the checkout's revision or the feature snapshot.
        # Only the README still documents the historical snapshot; the site targets 0.2.0.
        feature_sha = 'cda65f0554a870ed8079e93741a331918118acec'
        default_sha = '21b3a082172ca4c4ef0c1a3651a9ad80504c1ed1'
        installer = (ROOT / 'install.sh').read_text()
        self.assertIn('ref="${CMAIL_REF:-' + default_sha + '}"', installer)
        self.assertNotEqual(feature_sha, default_sha)
        for name in ['README.md']:
            with self.subTest(name=name):
                text = (ROOT / name).read_text()
                blocks = re.findall(r'```bash\n(.*?)```', text, re.S)
                quickstarts = [block for block in blocks if 'git clone' in block]
                self.assertTrue(quickstarts, name)
                for block in quickstarts:
                    commands = [line.split('#', 1)[0].strip() for line in block.splitlines()]
                    commands = [line for line in commands if line]
                    expected = ['git clone https://github.com/luongnv89/cmail', 'cd cmail',
                                'git fetch origin ' + feature_sha,
                                'git checkout --detach ' + feature_sha, './cmail help']
                    self.assertEqual(commands[:5], expected)
                    self.assertTrue(all(command == './cmail setup' for command in commands[5:]))
                    self.assertNotIn('bash install.sh', block)
                    self.assertNotIn('--branch v0.1.0', block)
                flat = ' '.join(re.sub(r'<[^>]*>', '', text).replace('**', '').split())
                for required in ['development source snapshot', 'not v0.1.0',
                                 'compatible release/installer ships', 'config defaults to checkout',
                                 'pinned v0.2.0 runtime', 'send-as', './cmail setup']:
                    self.assertIn(required.lower(), flat.lower(), name)
                self.assertNotIn('pinned v0.1.0', flat.lower(), name)
                self.assertIn('Must list send-as', flat)
                self.assertRegex(flat, r'(?:stop if missing|If `?send-as`? is missing, stop)')
        # Capability check is offline: no config or provider access is needed.
        help_result = subprocess.run([str(ROOT / 'cmail'), 'help'], cwd=ROOT,
                                     text=True, capture_output=True, timeout=5)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('./cmail send-as', help_result.stdout)

    @unittest.skipUnless(shutil.which('git'), 'Git unavailable; offline SHA-fetch fixture requires Git')
    def test_issue17_explicit_fetch_makes_nondefault_pr_snapshot_available(self):
        # file:// avoids local-clone object copying; no network/provider access.
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME='Offline Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                   GIT_COMMITTER_NAME='Offline Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
                   GIT_TERMINAL_PROMPT='0')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, clone = root / 'upstream', root / 'clone'

            def git(cwd, *args, check=True):
                result = subprocess.run(['git', *args], cwd=cwd, env=env,
                                        capture_output=True, text=True, timeout=10)
                if check:
                    self.assertEqual(result.returncode, 0, result.stderr)
                return result

            git(root, 'init', str(upstream))
            git(upstream, 'checkout', '-b', 'main')
            git(upstream, 'commit', '--allow-empty', '-m', 'default snapshot')
            git(upstream, 'checkout', '-b', 'feature')
            git(upstream, 'commit', '--allow-empty', '-m', 'feature snapshot')
            pin = git(upstream, 'rev-parse', 'HEAD').stdout.strip()
            git(upstream, 'update-ref', 'refs/pull/16/head', pin)
            git(upstream, 'checkout', 'main')
            git(upstream, 'branch', '-D', 'feature')
            git(root, 'clone', '--single-branch', '--branch', 'main',
                upstream.as_uri(), str(clone))
            self.assertNotEqual(git(clone, 'cat-file', '-e', pin, check=False).returncode, 0)
            self.assertNotEqual(git(clone, 'checkout', '--detach', pin, check=False).returncode, 0)
            git(clone, 'fetch', 'origin', pin)
            git(clone, 'checkout', '--detach', pin)
            self.assertEqual(git(clone, 'rev-parse', 'HEAD').stdout.strip(), pin)
            self.assertEqual(git(clone, 'branch', '--show-current').stdout.strip(), '')

    def test_issue17_readme_uses_checkout_config_or_explicit_reuse(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('ENV_FILE="$HOME/.config/cmail/.env"', readme)
        self.assertIn('for every `./cmail` invocation', readme)

    def test_no_remote_runtime_assets_or_provider_calls(self):
        for filename in PAGES:
            for tag, attrs in Page(ROOT / 'docs' / filename).elements:
                if tag in ['script', 'img', 'iframe'] or (tag == 'link' and attrs.get('rel') == 'stylesheet'):
                    path = attrs.get('src', attrs.get('href', ''))
                    self.assertFalse(urlsplit(path).scheme, path)
        for script in ['checklist.js', 'terminal.js']:
            js = (ROOT / 'docs/assets' / script).read_text()
            for forbidden in ['fetch(', 'XMLHttpRequest', 'innerHTML', 'localStorage.clear', 'eval(']:
                self.assertNotIn(forbidden, js, script)
        self.assertIn('prefers-reduced-motion', (ROOT / 'docs/assets/terminal.js').read_text())

    def test_palette_contrast_and_focus(self):
        css = (ROOT / 'docs/assets/styles.css').read_text()
        def luminance(rgb):
            vals = [v / 255 for v in rgb]
            vals = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in vals]
            return sum(a * b for a, b in zip(vals, [.2126, .7152, .0722]))
        gray = luminance([107, 114, 128])
        self.assertGreaterEqual(1.05 / (gray + .05), 4.5)
        self.assertGreaterEqual(1.05 / .05, 4.5)  # black/white and reverse
        self.assertIn(':focus-visible', css)
        self.assertNotIn('background: var(--accent)', css)
        self.assertNotIn('color: var(--accent)', css)  # green is border-only, never low-contrast text
        self.assertIn('@media (max-width: 800px)', css)


if __name__ == '__main__':
    unittest.main(verbosity=2)
