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
                     "cmail --version", "Do not run it as a gate orchestrator"):
            # The monolithic-setup restriction is Markdown emphasized.
            self.assertIn(text, body.replace("**", ""))
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
                     "whence -w cmail", "Target machine", "printenv ENV_FILE CMAIL_BIN_DIR",
                     'ls -l "$ENV_FILE"', "none in cwd", "earliest unverified gate"):
            self.assertIn(text, probes)
        flat = " ".join(probes.split())
        # Target-machine rule: probes describe the agent shell; a mismatch stays unknown.
        self.assertIn("Probe results describe the agent's shell", flat)
        self.assertIn("A probe on a non-target shell does not answer", flat)
        self.assertIn("target machine", section.replace("\n", " "))
        # Environment dumps could expose provider secrets during discovery.
        forbidden = flat.split("Forbidden during discovery", 1)[1].split("## ", 1)[0]
        for dump in ("`env`", "`set`", "`printenv`", "`export -p`"):
            self.assertIn(dump, forbidden)
        texts = [body] + [p.read_text() for p in sorted((SKILL / "references").glob("*.md"))]
        old_questions = re.compile(r"ask\s+os\b|terminal\s+availability|installed\s+or\s+a\s+source"
                                   r"\s+checkout|ask\s+which\s+gate\s+failed|to\s+start,\s+please\s+tell\s+me",
                                   re.IGNORECASE)
        for text in texts:
            self.assertIsNone(old_questions.search(text))
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
