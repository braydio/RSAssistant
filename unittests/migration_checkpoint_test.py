"""Tests for offline, non-mutating migration checkpoints."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migration_checkpoint.py"
spec = importlib.util.spec_from_file_location("migration_checkpoint", SCRIPT)
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


class MigrationCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root / "production.db"
        self.conn = sqlite3.connect(self.source)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA user_version=10")
        self.conn.execute("CREATE TABLE Accounts (id integer PRIMARY KEY, name text)")
        self.conn.execute("INSERT INTO Accounts(name) VALUES ('synthetic')")
        self.conn.commit()
        self.addCleanup(self.conn.close)

    def test_inspect_is_read_only(self):
        with checkpoint.source_connection(self.source) as conn:
            self.assertEqual(checkpoint.inventory(conn)["row_counts"]["Accounts"], 1)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO Accounts(name) VALUES ('unexpected')")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM Accounts").fetchone()[0], 1)

    def test_backup_wal_consistent_and_verifiable(self):
        output = checkpoint.backup(self.source, self.root / "private", self.root)
        snapshot = Path(output["backup"])
        self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(snapshot.parent.stat().st_mode), 0o700)
        self.assertEqual(checkpoint.verify(snapshot)["inventory"]["row_counts"]["Accounts"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM Accounts").fetchone()[0], 1)
        self.conn.execute("INSERT INTO Accounts(name) VALUES ('later')")
        self.conn.commit()
        self.assertEqual(checkpoint.verify(snapshot)["inventory"]["row_counts"]["Accounts"], 1)

    def test_tamper_detected(self):
        output = checkpoint.backup(self.source, self.root / "private", self.root)
        backup = Path(output["backup"])
        with backup.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaisesRegex(ValueError, "checksum"):
            checkpoint.verify(backup)

    def test_missing_source_does_not_create_database(self):
        missing = self.root / "missing.db"
        with self.assertRaises(ValueError):
            checkpoint.source_connection(missing)
        self.assertFalse(missing.exists())

    def test_rejects_symlink_and_source_directory(self):
        alias = self.root / "alias.db"
        alias.symlink_to(self.source)
        with self.assertRaises(ValueError):
            checkpoint.source_connection(alias)
        with self.assertRaises(ValueError):
            checkpoint.backup(self.source, self.root, self.root)

    def test_rejects_public_backup_directory(self):
        directory = self.root / "public"
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            checkpoint.backup(self.source, directory, self.root)


if __name__ == "__main__":
    unittest.main()
