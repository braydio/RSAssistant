Traceback (most recent call last):
  File "/home/braydenchaffee/projects/RevSplits/auto-rsa/RSAssistant/src/RSAssistant.py", line 20, in <module>
    from utils.excel_utils import (clear_account_mappings, index_account_details,
  File "/home/braydenchaffee/projects/RevSplits/auto-rsa/RSAssistant/src/utils/excel_utils.py", line 13, in <module>
    from utils.init import (config,
  File "/home/braydenchaffee/projects/RevSplits/auto-rsa/RSAssistant/src/utils/init.py", line 4, in <module>
    from utils.config_utils import (
  File "/home/braydenchaffee/projects/RevSplits/auto-rsa/RSAssistant/src/utils/config_utils.py", line 144, in <module>
    setup_logging(config)
  File "/home/braydenchaffee/projects/RevSplits/auto-rsa/RSAssistant/src/utils/logging_setup.py", line 46, in setup_logging
    handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backup_count)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/logging/handlers.py", line 155, in __init__
    BaseRotatingHandler.__init__(self, filename, mode, encoding=encoding,
  File "/usr/lib/python3.12/logging/handlers.py", line 58, in __init__
    logging.FileHandler.__init__(self, filename, mode=mode,
  File "/usr/lib/python3.12/logging/__init__.py", line 1231, in __init__
    StreamHandler.__init__(self, self._open())
                                 ^^^^^^^^^^^^
  File "/usr/lib/python3.12/logging/__init__.py", line 1263, in _open
    return open_func(self.baseFilename, self.mode,
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [Errno 13] Permission denied: '/home/braydenchaffee/projects/RevSplits/auto-rsa/RSAssistant/volumes/logs/rsassistant.log'
