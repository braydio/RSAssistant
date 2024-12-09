
# Project Improvement and Implementation Notes

## Working

### 1. Notify on Unmapped Accounts
At the end of the `!rsa holdings` command (from the other bot), notify if any accounts:
   - Are included in the account mappings but **not listed** in the summary returned by the other bot.
   - This notification should appear as a Discord message appended after the usual end message:
     ```
     Total Value of All Accounts: $4457.14
     All commands complete in all brokers
     ```

### 2. Detailed Unmapped Account Notifications
Enhance existing unmapped account notifications to include detailed information:
   - **Details to include**: Broker name, broker number, account number.
   - This notification should also be sent as a Discord message.

### 3. Improve `top holdings` Command
Refactor the `top holdings` command for the Discord bot to ensure that the embed message:
   - Has a cleaner and more user-friendly layout.
   - Provides clear sections for different account types or categories.

### 4. Fix `shutdown` Command
Investigate and fix the issue with the `shutdown` command not working properly.

---

## General Enhancements
1. **Refactor for Consistency and Readability**:
   - Ensure consistent naming conventions across all modules (e.g., snake_case for function names).
   - Add docstrings where missing to clarify the purpose of each function.

2. **Configuration Management**:
   - Transition from a JSON/TXT-based config management to a standardized `.yaml` or `.env` setup, leveraging the existing `load_config` function for all modules.

3. **Logging Improvements**:
   - Introduce contextual logging to highlight critical actions in each module.
   - Add more granular logging levels (DEBUG, INFO, WARNING, ERROR) for better debugging capabilities.

---

## Functional Improvements
1. **Excel Utilities (`excel_utils.py`)**:
   - Add error handling for `openpyxl` operations to gracefully manage corrupt/missing Excel files.
   - Optimize `map_accounts_in_excel_log` to handle larger data sets more efficiently.

2. **Watchlist Features (`watch_utils.py`)**:
   - Enhance `update_watchlist_with_stock` to validate ticker formats and provide user feedback for invalid entries.
   - Allow batch addition of tickers and split dates using a CSV or JSON upload.

3. **Order Parsing and Normalization (`parsing_utils.py`)**:
   - Expand regex patterns in `order_patterns` for broader broker support.
   - Optimize the `normalize_order_data` function for better exception handling when dealing with malformed data.

---

## Database and Persistence
1. **Database Optimization (`sql_utils.py`)**:
   - Ensure proper indexing on critical columns in the database for faster queries (e.g., `AccountMappings.account_number` and `Orders.date`).
   - Add a function to perform routine database maintenance, such as vacuuming and backing up.

2. **Historical Data Tracking**:
   - Implement archiving for older database records (e.g., orders older than one year) into separate tables or files.

---

## New Features and Integrations
1. **Discord Bot Commands (`RSAssistant.py`)**:
   - Add a `..help` command to dynamically display available commands based on the loaded modules.
   - Implement a more robust task scheduling mechanism for reminders, including user-customizable schedules.

2. **Data Visualization**:
   - Create visual reports (charts/graphs) for account holdings or order history using `matplotlib` or `plotly`.

3. **Backup and Recovery**:
   - Extend the backup mechanism in `excel_utils.py` to support automatic versioning of all key files.

---

## Performance and Testing
1. **Async Improvements**:
   - Review and optimize `async` functions for performance, especially those involving file I/O or API calls.

2. **Unit Testing**:
   - Introduce a `tests/` directory and set up `pytest` for unit and integration testing of key functions.

3. **Load Testing**:
   - Simulate high-load scenarios for modules interacting with databases or files to identify bottlenecks.

---

## Miscellaneous
1. **Error Notifications**:
   - Send Discord alerts for critical errors or when backups fail.

2. **Documentation**:
   - Work on your documentation you pleb
