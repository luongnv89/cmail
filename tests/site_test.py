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
BIN = Path(os.environ.get('CMAIL_BIN', ROOT / 'target' / 'debug' / 'cmail'))


def runtime_source():
    return '\n'.join(p.read_text() for p in sorted((ROOT / 'src').rglob('*.rs')))
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

    def test_issue25_one_line_curl_install_is_the_main_method(self):
        one_liner = 'curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash'
        texts = {name: unescape((ROOT / name).read_text())
                 for name in ['README.md', 'docs/setup.html', 'docs/setup.md', 'docs/docs.html']}
        for name, text in texts.items():
            with self.subTest(name=name):
                self.assertIn(one_liner, text)
                # The clone-and-install route stays documented, after the one-liner.
                self.assertIn('bash install.sh --local', text)
                self.assertLess(text.index(one_liner), text.index('bash install.sh --local'))
        self.assertNotIn('No remote bootstrap', texts['README.md'])
        for name in ['docs/setup.html', 'docs/setup.md']:
            text = texts[name]
            step = text[text.index('nstall cmail'):text.index('Create a Cloudflare API token')]
            self.assertIn(one_liner, step)
            self.assertIn('export PATH="$HOME/.local/bin:$PATH"', step)
            self.assertLess(step.index(one_liner), step.index('git clone'))
        self.assertIn('Run one <code>curl</code> command', (ROOT / 'docs/index.html').read_text())
        # A piped script has no file path, so only --local may resolve one.
        installer = (ROOT / 'install.sh').read_text()
        self.assertNotIn('"${BASH_SOURCE[0]}"', installer)
        self.assertIn('${BASH_SOURCE[0]:-}', installer)

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
                          'cmail setup --dry-run', 'cmail send-as', 'cmail list', 'cmail 0.4.0',
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
        source = runtime_source()
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
        version = subprocess.run([str(BIN), '--version'], cwd=ROOT,
                                 text=True, capture_output=True, timeout=5)
        self.assertEqual(version.stdout.strip(), 'cmail ' + (ROOT / 'VERSION').read_text().strip())
        self.assertIn(version.stdout.strip(), html)

    def test_cli_docs_cover_every_command_and_setting(self):
        help_result = subprocess.run([str(BIN), 'help'], cwd=ROOT,
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
        source = runtime_source()
        self.assertEqual(set(re.findall(r'https://(api\.[a-z0-9.-]+)', source)), {'api.cloudflare.com'})

    def test_readme_install_story_uses_the_installed_command(self):
        # Installed `cmail` is the only documented invocation; a reviewed checkout
        # installs itself with --local instead of running ./cmail in place.
        readme = (ROOT / 'README.md').read_text()
        blocks = re.findall(r'```bash\n(.*?)```', readme, re.S)
        clones = [block for block in blocks if 'git clone' in block]
        self.assertEqual(len(clones), 1)
        commands = [line.split('#', 1)[0].strip() for line in clones[0].splitlines()]
        self.assertEqual([c for c in commands if c][:3],
                         ['git clone https://github.com/luongnv89/cmail', 'cd cmail', 'bash install.sh --local'])
        self.assertIn('brew install luongnv89/tap/cmail', readme)
        self.assertNotIn('./cmail', readme)
        self.assertIn('Sending is optional', readme)
        help_result = subprocess.run([str(BIN), 'help'], cwd=ROOT, text=True, capture_output=True, timeout=5)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('send-as', help_result.stdout)
        self.assertNotIn('./cmail', help_result.stdout)

    def test_readme_documents_config_location_and_migration(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('`~/.config/cmail/.env`', readme)
        self.assertIn('--config ./.env', readme)
        self.assertIn('cmail config path', readme)

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
