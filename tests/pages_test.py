#!/usr/bin/env python3
"""Check the exact Pages artifact offline; never publish or call providers."""
import functools
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FILES = {'index.html', 'setup.html', 'setup.md', 'distribution.md',
         'assets/styles.css', 'assets/checklist.js'}


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.paths = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src') and value:
                link = urlsplit(value)
                if not link.scheme and not link.netloc and link.path:
                    self.paths.append(link.path)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class PagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in FILES:
            target = self.root / 'docs' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'docs' / name, target)

    def stage(self):
        return subprocess.run(['bash', str(ROOT / 'scripts/build-pages.sh')],
                              cwd=self.root, capture_output=True, text=True)

    def test_exact_allowlist_preserves_files_and_excludes_private_or_future_inputs(self):
        for name in ['.env', 'private.md', 'assets/secret.txt']:
            (self.root / 'docs' / name).write_text('must not be published')
        (self.root / '.env').write_text('must not be published')
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = self.root / '_site'
        actual = {p.relative_to(artifact).as_posix() for p in artifact.rglob('*') if p.is_file()}
        self.assertEqual(actual, FILES)
        for name in FILES:
            self.assertEqual((artifact / name).read_bytes(), (ROOT / 'docs' / name).read_bytes())

    def test_missing_input_fails_before_creating_artifact(self):
        (self.root / 'docs/setup.html').unlink()
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertFalse((self.root / '_site').exists())

    def test_symlinked_input_is_refused(self):
        target = self.root / 'docs/setup.md'
        target.unlink()
        target.symlink_to(ROOT / 'docs/setup.md')
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertFalse((self.root / '_site').exists())

    def test_existing_artifact_is_not_modified(self):
        (self.root / '_site').mkdir()
        sentinel = self.root / '_site/sentinel'
        sentinel.write_text('preserve')
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertEqual(sentinel.read_text(), 'preserve')
        self.assertEqual(list((self.root / '_site').iterdir()), [sentinel])

    def test_project_subpath_serves_all_page_links_and_assets(self):
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / '_site').rename(self.root / 'cmail')
        handler = functools.partial(QuietHandler, directory=str(self.root))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}/cmail/'
            for name in ['index.html', 'setup.html']:
                url = urljoin(base, name)
                with urlopen(url) as response:
                    text = response.read().decode()
                    self.assertEqual(response.status, 200)
                for path in Links(text).paths:
                    target = urljoin(url, path)
                    self.assertTrue(urlsplit(target).path.startswith('/cmail/'), target)
                    with urlopen(target) as response:
                        self.assertEqual(response.status, 200)
            for name in ['setup.md', 'distribution.md']:
                text = (self.root / 'cmail' / name).read_text()
                for path in re.findall(r'\]\(([^)]+)\)', text):
                    parsed = urlsplit(path)
                    if not parsed.scheme and not parsed.netloc:
                        target = urljoin(urljoin(base, name), unquote(parsed.path))
                        self.assertTrue(urlsplit(target).path.startswith('/cmail/'), target)
                        with urlopen(target) as response:
                            self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_workflow_scopes_publication_and_pins_actions(self):
        text = (ROOT / '.github/workflows/pages.yml').read_text()
        self.assertIn('pull_request:', text)
        self.assertIn('workflow_dispatch:', text)
        self.assertIn("if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'", text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('path: _site', text)
        self.assertIn('run: bash scripts/build-pages.sh', text)
        self.assertIn('pages: write', text)
        self.assertIn('id-token: write', text)
        self.assertIn('name: github-pages', text)
        self.assertIn('cancel-in-progress: false', text)
        self.assertEqual(len(re.findall(r'uses: actions/[\w-]+@[a-f0-9]{40}\b', text)), 4)
        for name in ['scripts/build-pages.sh', 'tests/pages_test.py', '.github/workflows/pages.yml']:
            self.assertEqual(text.count("- '" + name + "'"), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
