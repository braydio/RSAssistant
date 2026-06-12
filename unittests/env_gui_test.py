import unittest
from http import HTTPStatus
from unittest.mock import Mock, patch

from scripts import env_gui


class SubmitCodexChangeRequestTest(unittest.TestCase):
    def test_rejects_empty_change_details(self) -> None:
        result = env_gui.submit_codex_change_request("feature", "")

        self.assertEqual(result["status"], HTTPStatus.BAD_REQUEST)
        self.assertIn("required", result["message"])

    def test_rejects_oversized_change_details(self) -> None:
        oversized = "x" * (env_gui.CODEX_PROMPT_LIMIT + 1)

        result = env_gui.submit_codex_change_request("feature", oversized)

        self.assertEqual(result["status"], HTTPStatus.BAD_REQUEST)
        self.assertIn(str(env_gui.CODEX_PROMPT_LIMIT), result["message"])

    @patch("scripts.env_gui.subprocess.run")
    def test_returns_success_on_zero_exit(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(returncode=0, stderr="")

        result = env_gui.submit_codex_change_request("bugfix", "Fix the crash")

        self.assertEqual(result["status"], HTTPStatus.OK)
        self.assertIn("successfully", result["message"])
        run_mock.assert_called_once()

    @patch("scripts.env_gui.subprocess.run")
    def test_returns_error_on_non_zero_exit(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(returncode=1, stderr="failed")

        result = env_gui.submit_codex_change_request("docs", "Update docs")

        self.assertEqual(result["status"], HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("failed", result["message"])


if __name__ == "__main__":
    unittest.main()
