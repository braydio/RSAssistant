import logging
import time
import unittest

from utils.logging_setup import TimeLengthListDuplicateFilter, setup_logging


def _record(msg, level=logging.INFO, **extra):
    record = logging.LogRecord("t", level, __file__, 1, msg, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class DuplicateFilterTest(unittest.TestCase):
    def test_entries_bounded_under_unique_message_stress(self):
        flt = TimeLengthListDuplicateFilter(interval=3600, max_entries=64)
        for i in range(5000):
            self.assertTrue(flt.filter(_record(f"unique {i}")))
        self.assertLessEqual(len(flt.logged_messages), 64)

    def test_duplicate_suppressed_then_expires(self):
        flt = TimeLengthListDuplicateFilter(interval=0.05)
        self.assertTrue(flt.filter(_record("dup")))
        self.assertFalse(flt.filter(_record("dup")))
        time.sleep(0.07)
        self.assertTrue(flt.filter(_record("dup")))

    def test_warnings_and_never_dedupe_survive_untruncated(self):
        flt = TimeLengthListDuplicateFilter()
        long_msg = "x" * 500
        for _ in range(3):
            warning = _record(long_msg, logging.WARNING)
            self.assertTrue(flt.filter(warning))
            self.assertEqual(warning.getMessage(), long_msg)
            self.assertTrue(flt.filter(_record("audit", never_dedupe=True)))


class SetupLoggingTest(unittest.TestCase):
    def tearDown(self):
        for h in logging.getLogger().handlers[:]:
            logging.getLogger().removeHandler(h)
            h.close()

    def test_idempotent_and_levelname_not_mutated(self):
        import tempfile, os

        with tempfile.TemporaryDirectory() as d:
            cfg = {"logging": {"level": "INFO", "file": os.path.join(d, "a.log")}}
            setup_logging(cfg)
            setup_logging(cfg)
            self.assertEqual(len(logging.getLogger().handlers), 2)
            logging.warning("hello-warning")
            for h in logging.getLogger().handlers:
                h.flush()
            with open(cfg["logging"]["file"]) as f:
                text = f.read()
            self.assertIn("WARNING - ", text)
            self.assertNotIn("\x1b[", text)


if __name__ == "__main__":
    unittest.main()
