#!/usr/bin/env python3
"""Offline site/document contract checks; no provider calls or third-party packages."""
import re
import unittest
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
IDS = ['readiness', 'install', 'dependencies', 'registrar', 'zone', 'token',
       'config', 'access', 'delegation', 'routing', 'destination', 'rules', 'gmail', 'delivery']


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
        for filename in ['index.html', 'setup.html']:
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
        for name in ['index.html', 'setup.html']:
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
        self.assertEqual(re.findall(r'^### (\d+)\.', md, re.M), [str(x) for x in range(1, 15)])
        self.assertEqual(len(re.findall(r'^- \[ \]', md, re.M)), 14)
        js = (ROOT / 'docs/assets/checklist.js').read_text()
        for step in IDS:
            self.assertIn("'" + step + "'", js)

    def test_repository_github_links_point_at_real_files(self):
        for filename in ['index.html', 'setup.html']:
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
            text = (ROOT / 'docs' / name).read_text()
            for value in ['CLOUDFLARE_API_TOKEN', 'GDDY_PAT', 'GDDY_ENV', 'CF_ACCOUNT_ID',
                          'CF_ZONE_ID', 'DOMAIN', 'DEST_EMAIL', 'ADDRESSES', 'DRY_RUN',
                          'Zone Settings', 'Email Routing Rules', 'Email Routing Addresses',
                          'January 2027', 'Advanced Protection', '587', 'TLS', 'smtp.gmail.com',
                          'check_config.py', 'x-request-id', 'api.ote-godaddy.com']:
                self.assertIn(value, text, f'{name}: {value}')
            self.assertRegex(text, r'previews only.*nameserver')
            self.assertIn('not proof', text)
            self.assertIn('pinned', text)
        readme = (ROOT / 'README.md').read_text()
        for link in ['docs/index.html', 'docs/setup.html', 'docs/setup.md', 'node --test tests/checklist_test.js', 'python3 tests/site_test.py']:
            self.assertIn(link, readme)

    def test_issue17_quickstarts_select_feature_runtime_not_default_installer(self):
        # Issue #17: installing from a newer checkout still downloads v0.1.0.
        feature_sha = 'cda65f0554a870ed8079e93741a331918118acec'
        legacy_sha = 'eb45f9558ecc5874e6a21d6f1b93fe1379f46841'
        installer = (ROOT / 'install.sh').read_text()
        self.assertIn('ref="${CMAIL_REF:-' + legacy_sha + '}"', installer)
        self.assertNotEqual(feature_sha, legacy_sha)
        for name in ['README.md', 'docs/index.html', 'docs/setup.html', 'docs/setup.md']:
            with self.subTest(name=name):
                text = unescape((ROOT / name).read_text())
                blocks = (re.findall(r'<pre><code>(.*?)</code></pre>', text, re.S)
                          if name.endswith('.html') else re.findall(r'```bash\n(.*?)```', text, re.S))
                quickstarts = [block for block in blocks if 'git clone' in block]
                self.assertTrue(quickstarts, name)
                for block in quickstarts:
                    commands = [line.split('#', 1)[0].strip() for line in block.splitlines()]
                    commands = [line for line in commands if line]
                    expected = ['git clone https://github.com/luongnv89/cmail', 'cd cmail',
                                'git checkout --detach ' + feature_sha, './cmail help']
                    self.assertEqual(commands[:4], expected)
                    self.assertTrue(all(command == './cmail setup' for command in commands[4:]))
                    self.assertNotIn('bash install.sh', block)
                    self.assertNotIn('--branch v0.1.0', block)
                flat = ' '.join(re.sub(r'<[^>]*>', '', text).replace('**', '').split())
                for required in ['development source snapshot', 'not v0.1.0',
                                 'compatible release/installer ships', 'config defaults to checkout',
                                 'Gmail guide', 'send-as', 'legacy', './cmail setup']:
                    self.assertIn(required.lower(), flat.lower(), name)
                if name == 'README.md':
                    self.assertIn('Must list send-as', flat)
                else:
                    self.assertRegex(flat, r'(?:must (?:load offline and )?list|lists).*send-as')
                self.assertRegex(flat, r'(?:stop if missing|If `?send-as`? is missing, stop)')
        # Capability check is offline: no config or provider access is needed.
        import subprocess
        help_result = subprocess.run([str(ROOT / 'cmail'), 'help'], cwd=ROOT,
                                     text=True, capture_output=True, timeout=5)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('./cmail send-as', help_result.stdout)

    def test_issue17_guides_use_checkout_config_or_explicit_reuse(self):
        for name in ['docs/setup.md', 'docs/setup.html']:
            text = unescape((ROOT / name).read_text())
            for command in ['cp -n .env.example .env', 'chmod 600 .env',
                            'python3 skills/cmail-setup/scripts/check_config.py .env',
                            'bash -n .env', 'ENV_FILE="$HOME/.config/cmail/.env"',
                            './cmail send-as', './cmail setup']:
                self.assertIn(command, text, name)
            self.assertIn('same path for both checks', text)
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('ENV_FILE="$HOME/.config/cmail/.env"', readme)
        self.assertIn('for every `./cmail` invocation', readme)

    def test_no_remote_runtime_assets_or_provider_calls(self):
        for filename in ['index.html', 'setup.html']:
            for tag, attrs in Page(ROOT / 'docs' / filename).elements:
                if tag in ['script', 'img', 'iframe'] or (tag == 'link' and attrs.get('rel') == 'stylesheet'):
                    path = attrs.get('src', attrs.get('href', ''))
                    self.assertFalse(urlsplit(path).scheme, path)
        js = (ROOT / 'docs/assets/checklist.js').read_text()
        for forbidden in ['fetch(', 'XMLHttpRequest', 'innerHTML', 'localStorage.clear', 'eval(']:
            self.assertNotIn(forbidden, js)

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
