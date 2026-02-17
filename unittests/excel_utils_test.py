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

    def test_add_stock_to_excel_log_writes_reverse_split_history(self):
        """Legacy add_stock helper should now route writes to SQL helper."""

        class DummyCtx:
            def __init__(self):
                self.sent = []

            async def send(self, message):
                self.sent.append(message)

        ctx = DummyCtx()

        with patch.object(
            excel_utils, "insert_reverse_split_log_entry", return_value=True
        ) as mock_insert:
            import asyncio

            asyncio.run(excel_utils.add_stock_to_excel_log(ctx, "TST", "01/02", "1-5"))

        mock_insert.assert_called_once()
        self.assertIn("Recorded reverse split history for TST", ctx.sent[0])

    def test_update_excel_log_writes_account_entries(self):
        """Legacy update helper should append SQL account entries."""
        order_data = {
            "Broker Name": "BrokerA",
            "Broker Number": "1",
            "Account Number": "1001",
            "Order Type": "buy",
            "Stock": "TST",
            "Price": "2.50",
        }

        with patch.object(
            excel_utils, "get_or_create_account_id", return_value=77
        ) as mock_get_id:
            with patch.object(
                excel_utils, "insert_reverse_split_account_entry", return_value=True
            ) as mock_insert:
                excel_utils.update_excel_log(order_data)

        mock_get_id.assert_called_once_with("BrokerA", "1", "1001")
        mock_insert.assert_called_once()
