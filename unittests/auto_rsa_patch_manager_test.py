import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import auto_rsa_patch_manager


class AutoRsaPatchManagerTest(unittest.TestCase):
    def test_resolve_auto_rsa_dir_falls_back_to_recorded_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            state_file.write_text(json.dumps({"auto_rsa_dir": "/recorded/auto-rsa"}))
            with (
                patch.object(auto_rsa_patch_manager, "AUTO_RSA_DIR", ""),
                patch.object(
                    auto_rsa_patch_manager,
                    "AUTO_RSA_PATCH_STATE_FILE",
                    state_file,
                ),
            ):
                self.assertEqual(
                    auto_rsa_patch_manager.resolve_auto_rsa_dir(),
                    "/recorded/auto-rsa",
                )

    def test_ensure_patch_runs_idempotent_patcher(self):
        result = unittest.mock.Mock(returncode=0, stdout="healthy", stderr="")
        with (
            patch.object(auto_rsa_patch_manager, "AUTO_RSA_PATCH_ENABLED", True),
            patch.object(auto_rsa_patch_manager, "AUTO_RSA_DIR", "/auto-rsa"),
            patch.object(auto_rsa_patch_manager.subprocess, "run", return_value=result) as run,
        ):
            self.assertTrue(auto_rsa_patch_manager.ensure_auto_rsa_holdings_patch())

        self.assertEqual(run.call_args.args[0][-1], "/auto-rsa")


if __name__ == "__main__":
    unittest.main()
