
# RSAssistant Bot Command Reference

## General Query Command
**Command:** `..query table_name [key=value...] [limit=n]`
- **Description:** Queries a database table and retrieves rows based on optional filters and limits.
- **Examples:**
  - Query all rows in the `Orders` table:
    ```
    ..query Orders
    ```
  - Query the `Orders` table with filters:
    ```
    ..query Orders account_id=1 ticker=AAPL
    ```
  - Query the `Orders` table with a limit:
    ```
    ..query Orders limit=5
    ```
  - Combine filters and a limit:
    ```
    ..query Orders account_id=1 limit=10
    ```

## Custom Query Command (Future Expansion)
- Placeholder for additional custom commands you might add.

---

### Notes
- **Filters:** Specify filters as `key=value`. Multiple filters can be chained with spaces.
- **Limit:** Use `limit=n` to restrict the number of rows returned.
- **Error Handling:** The bot will report errors if the table name is invalid, filters are incorrect, or if there’s a database issue.

---

Feel free to expand this document as new features are added!
