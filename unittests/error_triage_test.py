"""Pure-helper tests for the read-only Codex error watcher."""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from rsassistant.services import error_triage as et


class ValidateInvocationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        self.codex = self.cwd / "codex"
        self.codex.write_text("#!/bin/sh\n")
        self.codex.chmod(self.codex.stat().st_mode | stat.S_IXUSR)

    def test_valid_command_has_exactly_one_readonly_never_pair(self):
        argv = et.validate_codex_invocation(f"{self.codex} exec --skip-git-repo-check -m gpt-5", self.cwd)
        self.assertEqual(argv[0], str(self.codex))
        self.assertEqual(argv.count("--sandbox"), 1)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[argv.index("--ask-for-approval") + 1], "never")

    def test_rejects_unsafe_commands(self):
        bad = [
            "python -c 'print(1)'",
            f"sh -c '{self.codex} exec'",
            f"{self.codex} exec --yolo",
            f"{self.codex} exec --full-auto",
            f"{self.codex} exec --sandbox workspace-write",
            f"{self.codex} exec --cd /",
            f"{self.codex} exec --output-schema /etc/passwd",
            f"{self.codex} exec --json",
            f"{self.codex} exec --model $(id)",
            f"{self.codex} exec -m",
            f"{self.cwd}/notcodex exec",
            "./codex exec",
            "codex",
            "",
            "codex 'unterminated",
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                et.validate_codex_invocation(raw, self.cwd)

    def test_missing_cwd_rejected(self):
        with self.assertRaises(ValueError):
            et.validate_codex_invocation(f"{self.codex} exec", self.cwd / "nope")

    def test_preflight_names_only(self):
        ok = dict(primary_channel=5, sender_ids={1}, auto_rsa_dir=str(self.cwd),
                  codex_command=f"{self.codex} exec")
        self.assertEqual(et.watcher_preflight(**ok), [])
        self.assertEqual(et.watcher_preflight(**{**ok, "primary_channel": 0}), ["DISCORD_PRIMARY_CHANNEL"])
        self.assertEqual(et.watcher_preflight(**{**ok, "sender_ids": set()}), ["AUTO_RSA_ERROR_WATCHER_SENDER_IDS"])
        self.assertEqual(et.watcher_preflight(**{**ok, "auto_rsa_dir": ""}), ["AUTO_RSA_DIR", ])
        self.assertEqual(et.watcher_preflight(**{**ok, "auto_rsa_dir": "/nonexistent-dir"}), ["AUTO_RSA_DIR"])


class SanitizeTest(unittest.TestCase):
    def test_redaction_of_synthetic_secrets(self):
        raw = (
            "Authorization: Bearer abcdefghijklmnop1234 key=sk-live1234567890abcdef "
            "user@example.com acct 123456789 /home/alice/app @everyone <@12345678901> "
            "token=" + "A" * 40
        )
        out = et.redact(raw)
        for leak in ("abcdefghijklmnop1234", "sk-live", "user@example.com", "123456789",
                     "/home/alice", "@everyone", "<@12345678901>", "A" * 40):
            self.assertNotIn(leak, out)

    def test_summary_never_echoes_raw_output(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cwd = Path(self.tmp.name)
        (cwd / "mod.py").write_text("x = 1\n")
        stdout = "Found: PermissionError in mod.py:12 token=SECRETVALUE1234567890 @everyone"
        summary = et.summarize_triage_result(
            exit_code=0, stdout=stdout, stderr="ghp_ABCDEFGHIJKLMNOP123456",
            runtime_context={"cwd": cwd, "max_chars": 500},
        )
        self.assertIn("permission", summary)
        self.assertIn("mod.py:12", summary)
        for leak in ("SECRETVALUE", "ghp_", "@everyone", "Found:"):
            self.assertNotIn(leak, summary)
        self.assertLessEqual(len(summary), 500)

    def test_unverified_path_and_unknown_category_withheld(self):
        summary = et.summarize_triage_result(
            exit_code=3, stdout="see /etc/shadow.py:1 weird", stderr="",
            runtime_context={"cwd": Path(tempfile.gettempdir())},
        )
        self.assertIn(et.WITHHELD, summary)
        self.assertNotIn("shadow", summary)
        self.assertIn("exit 3", summary)


class BoundedSeenTest(unittest.TestCase):
    def test_cap_and_ttl(self):
        now = [0.0]
        seen = et.BoundedSeen(clock=lambda: now[0])
        for i in range(5000):
            seen.add(i)
        self.assertLessEqual(len(seen), 1024)
        self.assertTrue(seen.seen(4999))
        self.assertFalse(seen.seen(0))
        now[0] += et.SEEN_TTL_SECONDS + 1
        self.assertFalse(seen.seen(4999))
        self.assertEqual(len(seen), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
