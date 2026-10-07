#!/usr/bin/env python3
"""Offline checks; only synthetic accepted fixtures are sourced for Bash comparison."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/cmail-setup"
SCRIPT = SKILL / "scripts/check_config.py"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("check_config", SCRIPT)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
FIXTURE = "DOMAIN=example.com\nDEST_EMAIL=user@gmail.com\nADDRESSES=hello,contact\nCLOUDFLARE_API_TOKEN='synthetic fixture only'\nGDDY_ENV=prod\n"


class ConfigTests(unittest.TestCase):
    def invoke(self, text=FIXTURE, mode=0o600):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private.env"
            path.write_text(text)
            path.chmod(mode)
            return subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True, capture_output=True)

    def test_valid_private_config(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NOT checked", result.stdout)
        self.assertNotIn("synthetic fixture", result.stdout + result.stderr)

    def test_unquoted_and_escaped_literals(self):
        config.validate(config.parse(FIXTURE.replace("'synthetic fixture only'", r"synthetic\ fixture\ only")))

    def test_missing_each_required_field(self):
        for key in ("DOMAIN", "DEST_EMAIL", "ADDRESSES", "CLOUDFLARE_API_TOKEN", "GDDY_ENV"):
            with self.subTest(key=key):
                text = "\n".join(line for line in FIXTURE.splitlines() if not line.startswith(key + "="))
                result = self.invoke(text)
                self.assertEqual(result.returncode, 1)
                self.assertIn(key, result.stderr)

    def test_expansions_and_commands_never_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "must-not-exist"
            for raw in (f"$(touch {marker})", f"`touch {marker}`", "$HOME", "x; false", "x && false", "<(false)", "~/secret"):
                with self.subTest(raw=raw):
                    result = self.invoke(FIXTURE + "GDDY_PAT=" + raw + "\n")
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse(marker.exists())
                    self.assertNotIn(raw, result.stderr)

    def test_controls_cannot_hide_commands_or_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "must-not-exist"
            for separator in ("\r", "\v", "\f", "\x00", "\x1f", "\x7f", "\x85", "\u2028", "\u2029"):
                for payload in ("GDDY_PAT=x" + separator + "#;touch " + str(marker),
                                "# comment" + separator + ";touch " + str(marker)):
                    with self.subTest(separator=repr(separator), payload=payload[:12]):
                        result = self.invoke(FIXTURE + payload + "\n")
                        self.assertEqual(result.returncode, 1)
                        self.assertNotIn(str(marker), result.stdout + result.stderr)
                        self.assertFalse(marker.exists())
            self.assertEqual(self.invoke(FIXTURE.replace("\n", "\r\n")).returncode, 1)

    def test_literal_values_match_bash(self):
        import shutil
        shells = {"/bin/bash", shutil.which("bash")}
        literals = ("plain", "'literal#hash'", "literal#hash", "'literal'fragment",
                    r"literal\;fragment", r"synthetic\ fixture", '"space value"',
                    r'"keep\q"', r'"slash\\end"', r'"quote\"end"',
                    "'single'\\'quote", "'~{}*?[];|()'", "''", "'tab\tvalue'")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.env"
            for raw in literals:
                text = FIXTURE + "GDDY_PAT=" + raw + "\n"
                expected = config.parse(text)["GDDY_PAT"]
                config.validate(config.parse(text))
                self.assertEqual(self.invoke(text).returncode, 0)
                path.write_bytes(text.encode())
                for shell in shells:
                    if not shell:
                        continue
                    with self.subTest(raw=raw, shell=shell):
                        # Fixed harness, clean environment, synthetic literals only.
                        result = subprocess.run(
                            [shell, "--noprofile", "--norc", "-c", '. "$1"; printf "%s" "$GDDY_PAT"',
                             "synthetic-config", str(path)], cwd=tmp,
                            env={"PATH": "/usr/bin:/bin", "HOME": tmp},
                            text=True, capture_output=True, timeout=3)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, expected)

    def test_double_quote_backslashes_not_discarded(self):
        result = self.invoke(FIXTURE.replace("DOMAIN=example.com", r'DOMAIN="exam\ple.com"'))
        self.assertEqual(result.returncode, 1)
        self.assertIn("DOMAIN", result.stderr)

    def test_unsupported_shell_word_forms_fail_closed(self):
        for raw in ("x:~", "x~", "*", "{a,b}", "[ab]", "x\\", "x # comment", "x\\\nfalse"):
            with self.subTest(raw=raw):
                self.assertEqual(self.invoke(FIXTURE + "GDDY_PAT=" + raw + "\n").returncode, 1)

    def test_duplicates_and_unquoted_spaces(self):
        for text in (FIXTURE + "DOMAIN=other.example\n", FIXTURE.replace("hello,contact", "hello contact")):
            self.assertEqual(self.invoke(text).returncode, 1)

    def test_invalid_fields(self):
        for old, new in (("example.com", "https://example.com"), ("user@gmail.com", "user"),
                         ("hello,contact", "hello@example.com"), ("hello,contact", "hello,hello"),
                         ("hello,contact", "hello,"), ("prod", "unknown")):
            with self.subTest(new=new):
                self.assertEqual(self.invoke(FIXTURE.replace(old, new)).returncode, 1)

    def test_optional_ids_and_preview(self):
        self.assertEqual(self.invoke(FIXTURE + "CF_ACCOUNT_ID=" + "a" * 32 + "\nDRY_RUN=1\n").returncode, 0)
        for field in ("CF_ACCOUNT_ID=wrong", "CF_ZONE_ID=wrong", "DRY_RUN=2"):
            self.assertEqual(self.invoke(FIXTURE + field + "\n").returncode, 1)

    def test_unknown_runtime_control_keys(self):
        for key in ("PATH", "BASH_ENV", "ENV", "UNRELATED"):
            result = self.invoke(FIXTURE + key + "=literal\n")
            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported key", result.stderr)

    def test_literal_hash_and_quoted_fragments(self):
        for raw in ("'literal#hash'", "literal#hash", "'literal'fragment", r"literal\;fragment"):
            config.validate(config.parse(FIXTURE + "GDDY_PAT=" + raw + "\n"))
        for raw in ("x # comment", "'unterminated", "x > file", "x | false", "x\x00"):
            self.assertEqual(self.invoke(FIXTURE + "GDDY_PAT=" + raw + "\n").returncode, 1)

    def test_nonregular_and_special_mode(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            fifo = Path(tmp) / "fifo"
            os.mkfifo(fifo, 0o600)
            for path in (fifo, Path(tmp)):
                result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 1)
        self.assertEqual(self.invoke(mode=0o4600).returncode, 1)

    def test_exact_size_limit(self):
        text = FIXTURE + "#" + "a" * (65536 - len(FIXTURE.encode()) - 1)
        self.assertEqual(len(text.encode()), 65536)
        self.assertEqual(self.invoke(text).returncode, 0)
        self.assertEqual(self.invoke(text + "a").returncode, 1)

    def test_mode_is_not_changed(self):
        result = self.invoke(mode=0o644)
        self.assertEqual(result.returncode, 1)
        self.assertIn("mode 600", result.stderr)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actual"
            path.write_text(FIXTURE)
            path.chmod(0o600)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            result = subprocess.run([sys.executable, str(SCRIPT), str(link)], capture_output=True)
            self.assertEqual(result.returncode, 1)

    def test_missing_path_and_usage(self):
        for args, code in (([], 2), (["/nonexistent/cmail-config"], 1)):
            result = subprocess.run([sys.executable, str(SCRIPT)] + args, text=True, capture_output=True)
            self.assertEqual(result.returncode, code)
            self.assertIn("Error:", result.stderr)
            self.assertIn("Run" if not args else "re-run", result.stderr)

    def test_malformed_secret_diagnostics_are_value_free(self):
        secret = "SYNTHETIC-DO-NOT-ECHO"
        for text in (FIXTURE + "GDDY_PAT='" + secret, FIXTURE + "bad " + secret,
                     FIXTURE + "GDDY_PAT=x;" + secret):
            result = self.invoke(text)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(secret, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_limit_and_encoding(self):
        self.assertEqual(self.invoke(FIXTURE + "#" + "a" * 65536).returncode, 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "env"
            path.write_bytes(b"\xff")
            path.chmod(0o600)
            result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"encoding", result.stderr)


SETTER = SKILL / "scripts/set_config.py"


class HelperTests(unittest.TestCase):
    def private(self, tmp, text, name="private.env"):
        path = Path(tmp) / name
        path.write_text(text)
        path.chmod(0o600)
        return path

    def run_script(self, *args):
        return subprocess.run([sys.executable] + [str(a) for a in args], text=True, capture_output=True)

    def test_summary_shows_public_values_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.private(tmp, FIXTURE + "GDDY_PAT=\n")
            result = self.run_script(SCRIPT, "--summary", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            for line in ("DOMAIN=example.com", "DEST_EMAIL=user@gmail.com", "ADDRESSES=hello,contact",
                         "CLOUDFLARE_API_TOKEN set", "GDDY_PAT empty", "CF_ZONE_ID absent", "READY:"):
                self.assertIn(line, result.stdout)
            self.assertNotIn("synthetic fixture", result.stdout + result.stderr)
            partial = self.private(tmp, "DOMAIN=example.com\nCLOUDFLARE_API_TOKEN=\n", "partial.env")
            result = self.run_script(SCRIPT, "--summary", partial)
            self.assertEqual(result.returncode, 3)
            self.assertIn("NOT READY: DEST_EMAIL", result.stdout)
            self.assertIn("CLOUDFLARE_API_TOKEN empty", result.stdout)
            # A token pasted on a public line must never be echoed.
            misplaced = self.private(tmp, FIXTURE + "CF_ACCOUNT_ID=SYNTHETIC_tok_123\n", "misplaced.env")
            result = self.run_script(SCRIPT, "--summary", misplaced)
            self.assertEqual(result.returncode, 3)
            self.assertIn("CF_ACCOUNT_ID=<invalid>", result.stdout)
            self.assertNotIn("SYNTHETIC_tok_123", result.stdout + result.stderr)

    def test_smart_quotes_and_non_ascii_rejected(self):
        for raw in ("\u2019abc\u2019", "caf\u00e9"):
            with tempfile.TemporaryDirectory() as tmp:
                path = self.private(tmp, FIXTURE.replace("'synthetic fixture only'", raw))
                result = self.run_script(SCRIPT, path)
                self.assertEqual(result.returncode, 1)
                self.assertIn("non-ASCII", result.stderr)
                self.assertNotIn("abc", result.stderr)

    def test_summary_keeps_file_safety_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.private(tmp, FIXTURE)
            path.chmod(0o644)
            self.assertEqual(self.run_script(SCRIPT, "--summary", path).returncode, 1)
            path.chmod(0o600)
            path.write_text(FIXTURE + "GDDY_PAT=$(id)\n")
            result = self.run_script(SCRIPT, "--summary", path)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("synthetic fixture", result.stdout + result.stderr)

    def test_setter_updates_public_keys_and_preserves_secrets(self):
        template = (ROOT / ".env.example").read_text().replace("CLOUDFLARE_API_TOKEN=", "CLOUDFLARE_API_TOKEN='synthetic fixture only'")
        with tempfile.TemporaryDirectory() as tmp:
            path = self.private(tmp, template)
            # The template's ADDRESSES=hello default needs --replace to change.
            refused = self.run_script(SETTER, path, "ADDRESSES=hello,contact")
            self.assertEqual(refused.returncode, 1)
            self.assertIn("--replace", refused.stderr)
            self.assertEqual(self.run_script(SETTER, path, "ADDRESSES=hello", "GDDY_ENV=prod").returncode, 0)
            result = self.run_script(SETTER, "--replace", path, "DOMAIN=example.com", "DEST_EMAIL=user@gmail.com",
                                     "ADDRESSES=hello,contact", "DRY_RUN=0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("example.com", result.stdout)
            text = path.read_text()
            self.assertIn("CLOUDFLARE_API_TOKEN='synthetic fixture only'", text)
            self.assertEqual(text.count("DOMAIN="), 1)
            self.assertEqual(oct(path.stat().st_mode & 0o777), oct(0o600))
            self.assertEqual(self.run_script(SCRIPT, path).returncode, 0)
            values = config.parse(text)
            self.assertEqual((values["DOMAIN"], values["ADDRESSES"], values["DRY_RUN"]), ("example.com", "hello,contact", "0"))
            sourced = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c",
                                      '. "$1"; printf "%s|%s" "$DOMAIN" "$ADDRESSES"', "synthetic", str(path)],
                                     env={"PATH": "/usr/bin:/bin", "HOME": tmp}, text=True, capture_output=True, timeout=3)
            self.assertEqual(sourced.stdout, "example.com|hello,contact")

    def test_setter_refuses_secrets_invalid_values_and_unsafe_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.private(tmp, FIXTURE)
            before = path.read_bytes()
            for arg in ("CLOUDFLARE_API_TOKEN=x", "GDDY_PAT=x", "DOMAIN=https://x", "PATH=/tmp",
                        "ADDRESSES=a,a", "DOMAIN", "DOMAIN=example.org DOMAIN=example.net"):
                with self.subTest(arg=arg):
                    result = self.run_script(SETTER, path, *arg.split(" "))
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("Nothing was written", result.stderr)
                    self.assertEqual(path.read_bytes(), before)
            self.assertEqual(self.run_script(SETTER, path).returncode, 2)
            self.assertEqual(self.run_script(SETTER, "--replace", path).returncode, 2)
            self.assertEqual(self.run_script(SETTER, path, "DOMAIN=example.org").returncode, 1)
            self.assertEqual(path.read_bytes(), before)
            unsafe = self.private(tmp, FIXTURE + "GDDY_PAT=$(id)\n", "unsafe.env")
            self.assertEqual(self.run_script(SETTER, unsafe, "DOMAIN=example.org").returncode, 1)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            self.assertEqual(self.run_script(SETTER, link, "DOMAIN=example.org").returncode, 1)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(tmp).glob(".cmail-config.*")), [])


class SkillContractTests(unittest.TestCase):
    def test_references_resolve(self):
        body = (SKILL / "SKILL.md").read_text()
        paths = set(re.findall(r"(?:references|scripts|evals)/[\w./-]+", body))
        self.assertGreaterEqual(len(paths), 5)
        for path in paths:
            self.assertTrue((SKILL / path).is_file(), path)

    def test_nine_gates_have_check_failure_recheck(self):
        matrix = (SKILL / "references/verification.md").read_text()
        sections = re.split(r"(?m)^## Gate ", matrix)[1:]
        self.assertEqual(len(sections), 9)
        for number, section in enumerate(sections, 1):
            self.assertTrue(section.startswith(str(number) + " "))
            for field in ("Prerequisite:", "Action:", "Verify:", "Failure:", "Repair/recheck:"):
                self.assertIn(field, section)

    def test_installer_and_config_contract(self):
        body = (SKILL / "SKILL.md").read_text()
        for text in ("bash install.sh", "v0.1.0 lacks", "ENV_FILE", "CMAIL_CONFIG_DIR", "~/.config/cmail/.env",
                     "cmail --version", "Run `cmail setup` as the primary path", "references/autonomous-run.md"):
            self.assertIn(text, body.replace("**", ""))
        self.assertNotIn("gate orchestrator", body)
        self.assertTrue((ROOT / "install.sh").is_file())
        self.assertIn('CMAIL_CONFIG_DIR', (ROOT / "install.sh").read_text())

    def test_dependency_and_secret_guidance(self):
        body = (SKILL / "SKILL.md").read_text()
        for command in ("curl --version", "jq --version", "gddy --version", "command -v bash"):
            self.assertIn(command, body)
        instructions = (SKILL / "references/configuration.md").read_text()
        for key in ("DOMAIN", "DEST_EMAIL", "ADDRESSES", "GDDY_ENV", "CLOUDFLARE_API_TOKEN", "GDDY_PAT"):
            self.assertIn(key, instructions)
        self.assertIn("unrecorded local editor", instructions)
        self.assertIn("not `.env`", instructions)

    def test_fail_closed_and_recheck_contract(self):
        body = (SKILL / "SKILL.md").read_text()
        self.assertIn("Only VERIFIED unlocks", body)
        self.assertIn("same verification check", body)
        self.assertIn("three unsuccessful repairs", body)
        self.assertIn("repeat the original check", (SKILL / "docs/README.md").read_text())

    def test_launcher_trust_precedes_help(self):
        body = (SKILL / "SKILL.md").read_text()
        trust = body.index("Before executing help")
        run = body.index("Only then use the quoted trusted absolute path")
        self.assertLess(trust, run)
        for text in ("type -t cmail", "reject aliases/functions", "provenance cannot be established",
                     "marker or familiar", "BLOCKED"):
            self.assertIn(text, body)

    def test_token_resource_proof_is_not_dashboard_login(self):
        matrix = (SKILL / "references/verification.md").read_text()
        gate = matrix.split("## Gate 4", 1)[1].split("## Gate 5", 1)[0]
        for text in ("actual configured token", "/zones/<zone-id>",
                     "/accounts/<owning-account-id>/email/routing/addresses",
                     "API success", "Dashboard login/visibility", "BLOCKED", "Read access does not prove write"):
            self.assertIn(text, gate)

    def test_context_discovery_replaces_opening_questions(self):
        body = (SKILL / "SKILL.md").read_text()
        discovery = body.index("## Discover context first")
        self.assertLess(discovery, body.index("## Select the mode"))
        self.assertLess(discovery, body.index("## Gate 1"))
        section = body[discovery:body.index("## Safety and gate contract")].replace("**", "")
        for rule in ("references/discovery.md", "never executes a found `cmail`",
                     "never reads or sources `.env`", "`unknown`", "browser access",
                     "do not ask for it", "current gate", "earliest unverified gate"):
            self.assertIn(rule, section.replace("\n", " "))
        probes = (SKILL / "references/discovery.md").read_text()
        for text in ("uname -s", "git rev-parse --show-toplevel", "command -v cmail",
                     "type -t cmail", "~/.config/cmail/.env", "command -v bash curl jq gddy",
                     "Browser access: unknown", "contents not read", "Forbidden during discovery",
                     "whence -w cmail", "Target machine", 'ls -l "$ENV_FILE"', "none in cwd",
                     "earliest unverified gate",
                     "for v in ENV_FILE CMAIL_BIN_DIR CMAIL_DATA_DIR CMAIL_CONFIG_DIR; do",
                     'printf \'%s=%s\\n\' "$v" "$(printenv "$v")"',
                     "unknown (launcher-baked path; resolved after Gate 1 provenance)",
                     "grep '^default_config='"):
            self.assertIn(text, probes)
        flat = " ".join(probes.split())
        # Target-machine rule: probes describe the agent shell; a mismatch stays unknown.
        self.assertIn("Probe results describe the agent's shell", flat)
        self.assertIn("A probe on a non-target shell does not answer", flat)
        self.assertIn("empty value means unset in the agent shell", flat)
        self.assertIn("confirm it at Gate 2 before selecting that config", flat)
        self.assertNotIn("printenv ENV_FILE CMAIL_BIN_DIR", probes)
        configuration = " ".join((SKILL / "references/configuration.md").read_text().split())
        self.assertIn("trusted launcher's `default_config=` line", configuration)
        self.assertIn("which file their invocation actually uses", configuration)
        self.assertIn("whence -w cmail", body)
        self.assertIn("whence -w cmail", (SKILL / "references/verification.md").read_text())
        self.assertIn("target machine", section.replace("\n", " "))
        # Environment dumps could expose provider secrets during discovery.
        forbidden = flat.split("Forbidden during discovery", 1)[1].split("## ", 1)[0]
        for dump in ("`env`", "`set`", "`printenv`", "`export -p`"):
            self.assertIn(dump, forbidden)
        texts = [body] + [p.read_text() for p in sorted((SKILL / "references").glob("*.md"))]
        old_questions = re.compile(r"ask\s+os\b|terminal\s+availability|installed\s+or\s+a\s+source"
                                   r"\s+checkout|ask\s+which\s+gate\s+failed|to\s+start,\s+please\s+tell\s+me",
                                   re.IGNORECASE)
        more_questions = [re.compile(p, re.IGNORECASE) for p in (
            r"ask\s+(whether|if)\s+.*(new setup|troubleshoot)",
            r"which\s+(os|operating system)",
            r"(do you have|is there)\s+(terminal|browser)")]
        for text in texts:
            self.assertIsNone(old_questions.search(text))
            for pattern in more_questions:
                self.assertIsNone(pattern.search(text), pattern.pattern)
        recovery = (SKILL / "references/troubleshooting.md").read_text()
        self.assertIn("do not open by asking which step failed", recovery)
        link = ROOT / ".claude/skills/cmail-setup"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (ROOT / ".agents/skills/cmail-setup").resolve())

    def test_agent_discovery_copy_matches_source(self):
        mirror = ROOT / ".agents/skills/cmail-setup"
        source_files = sorted(p.relative_to(SKILL) for p in SKILL.rglob("*")
                              if p.is_file() and "__pycache__" not in p.parts)
        mirror_files = sorted(p.relative_to(mirror) for p in mirror.rglob("*")
                              if p.is_file() and "__pycache__" not in p.parts)
        self.assertEqual(source_files, mirror_files)
        for rel in source_files:
            self.assertEqual((SKILL / rel).read_bytes(), (mirror / rel).read_bytes(), str(rel))

    def test_autonomy_contract_and_run_protocol(self):
        body = (SKILL / "SKILL.md").read_text().replace("**", "")
        auto, stop = body.index("Auto — run without asking"), body.index("Stop — ask once")
        self.assertLess(auto, stop)
        self.assertLess(stop, body.index("## Gate 1"))
        for text in ("nameserver replacement", "domain purchase", "sudo", "Missing:", "Super important:",
                     "Wrong:", "three unsuccessful repairs", "check_config.py --summary", "set_config.py"):
            self.assertIn(text, body)
        run = " ".join((SKILL / "references/autonomous-run.md").read_text().split())
        for text in ('ENV_FILE="$cfg" "$launcher" setup </dev/null', "printf 'y\\n\\n' |",
                     "aborted before nameserver change", "Setup stopped at:", "paused without input",
                     "Never pipe `yes`", "Stop before pass 1", "route*.mx.cloudflare.net", "in the background",
                     "Run every pass in the background", "DRY_RUN must be absent or `0`", "DRY_RUN=0 ENV_FILE",
                     "first match wins", "needs attention", "treat the same records as approved",
                     "creating zone … in account <id>"):
            self.assertIn(text, run)
        # Pass 1 (stdin closed) must be specified before any piped approval input.
        self.assertLess(run.index("</dev/null"), run.index("printf 'y"))
        recovery = (SKILL / "references/troubleshooting.md").read_text()
        for step in ("`Dependencies`", "`Configuration`", "`GoDaddy authentication`", "`Choose domain`",
                     "`Cloudflare API token`", "`Cloudflare zone:`", "`GoDaddy: point`",
                     "`Waiting for zone activation`", "`Enable Cloudflare Email Routing`",
                     "`Destination address:`", "`Forwarding addresses`", "`Send FROM`"):
            self.assertIn(step, recovery)
        steps = (ROOT / "lib/ui.sh").read_text()
        for step in ("Dependencies", "Configuration", "'GoDaddy authentication'", "'Choose domain'",
                     "'Cloudflare API token'", "'Cloudflare zone:'", "'GoDaddy: point'",
                     "'Waiting for zone activation'", "'Enable Cloudflare Email Routing'",
                     "'Destination address:'", "'Forwarding addresses'", "'Send FROM'"):
            self.assertIn(step, steps)
        for text in ("aborted before nameserver change", "paused without input"):
            self.assertIn(text, (ROOT / "lib/godaddy.sh").read_text() + (ROOT / "lib/gmail.sh").read_text())

    def test_setup_prompts_fail_closed_on_stdin(self):
        # Pass 1 relies on closed stdin declining prompts; pass 2 on "y" then Enter.
        script = '. "$1/lib/ui.sh"; if confirm "apply nameserver change"; then echo YES; else echo NO; fi; pause && echo PAUSED || echo NOPAUSE'
        def run(stdin):
            return subprocess.run(["bash", "-c", script, "probe", str(ROOT)], input=stdin, text=True,
                                  capture_output=True, timeout=5).stdout
        self.assertIn("NO", run(""))
        self.assertIn("NOPAUSE", run(""))
        self.assertIn("YES", run("y\n\n"))
        self.assertIn("PAUSED", run("y\n\n"))
        self.assertIn("NO", run("\n"))

    def test_eval_floor_and_process_assertions(self):
        suite = json.loads((SKILL / "evals/evals.json").read_text())
        self.assertEqual(suite["skill_name"], "cmail-setup")
        cases = suite["evals"]
        self.assertEqual(len({item["id"] for item in cases}), len(cases))
        self.assertGreaterEqual(sum(c["kind"] == "happy-path" for c in cases), 3)
        self.assertTrue(any(c["kind"] == "edge" for c in cases))
        self.assertTrue(any(c["kind"] == "negative-trigger" for c in cases))
        for case in cases:
            self.assertTrue(case["prompt"])
            self.assertTrue(case["expected_output"])
            self.assertTrue(case["expectations"])
            if case["kind"] == "happy-path":
                self.assertTrue(any("gate" in e.lower() for e in case["expectations"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
