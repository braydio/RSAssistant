"""Regression checks for removing Excel from the runtime bootstrap."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class ExcelRetirementTest(unittest.TestCase):
    def test_entrypoint_initializes_without_excel_volume(self):
        repo_root = Path(__file__).resolve().parents[1]
        temporary_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        volumes_dir = temporary_dir / "volumes"
        bin_dir = temporary_dir / "bin"
        bin_dir.mkdir()
        python_stub = bin_dir / "python"
        python_stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        python_stub.chmod(0o755)
        env = os.environ.copy()
        env["VOLUMES_DIR"] = str(volumes_dir)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
        env.pop("EXCEL_LOGGING_ENABLED", None)
        env.pop("EXCEL_FILE_MAIN", None)

        result = subprocess.run(
            ["sh", "entrypoint.sh"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((volumes_dir / "logs").is_dir())
        self.assertTrue((volumes_dir / "db").is_dir())
        self.assertTrue((volumes_dir / "cache").is_dir())
        self.assertFalse((volumes_dir / "excel").exists())


if __name__ == "__main__":
    unittest.main()
