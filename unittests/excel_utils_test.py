"""Unit tests for Excel deprecation no-op behavior."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from utils import excel_utils


class ExcelUtilsDeprecationTest(TestCase):
    """Validate Excel helpers avoid filesystem writes when deprecated."""

    def test_get_excel_file_path_does_not_create_archive_when_deprecated(self):
        """Import-time path resolution should not create backup directories."""
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            archive_dir = base_dir / "archive"

            path = excel_utils.get_excel_file_path(directory=base_dir, filename="RSLog")

            self.assertEqual(path, str(base_dir / excel_utils.BASE_EXCEL_FILE))
            self.assertFalse(archive_dir.exists())

    def test_save_workbook_noops_when_excel_is_deprecated(self):
        """Workbook save should not be invoked when write paths are disabled."""
        workbook = Mock()

        with patch.object(excel_utils, "EXCEL_DEPRECATED", True):
            excel_utils.save_workbook(workbook, "dummy.xlsx")

        workbook.save.assert_not_called()
