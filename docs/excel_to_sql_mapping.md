# Excel to SQL Mapping Reference

## Status Note
Excel is deprecated and non-authoritative after migration. The SQL database and
JSON logs are the sources of truth, and Excel should be treated as a historical
artifact only.

## Excel Sheet Layouts (Deprecated)

### Account Details
Column headers and meaning:

| Column | Header (inferred) | Meaning | SQL Mapping |
| --- | --- | --- | --- |
| A | Broker Name | Broker name string used in account mapping. | `Accounts.broker` |
| B | Group Number | Broker group number used in account mapping. | `Accounts.broker_number` |
| C | Account Number | Account number (zero-padded to 4 digits in code). | `Accounts.account_number` |
| D | Account Nickname | Human-readable nickname for the account. | `Accounts.account_nickname` |

### Reverse Split Log
Row indices (from `utils/excel_utils.py`):

- `stock_row = 1`
- `date_row = 1`
- `ratio_row = 2`
- `order_row = 3`
- `account_start_row = 4`
- `account_start_column = 1`

Column layout for per-account values:

- Columns are grouped in repeating blocks of three:
  - **Cost column**: ticker symbol appears on `stock_row`; account prices for buy/cost entries.
  - **Proceeds column**: split date appears on `date_row`; split ratio appears on `ratio_row`; order header uses "Proceeds" on `order_row`; account prices for sell/proceeds entries.
  - **Spacer column**: formatting-only spacer copied from the prior block.
- The first two columns are treated as headers/labels in helpers (tickers start at
  column 3 when adding new tickers).
- Account rows begin at `account_start_row`, with column A containing the
  account label (broker + nickname).

## Excel Concepts → SQL Mapping

| Excel Concept | SQL Table / Column | Stored or Derived | Notes |
| --- | --- | --- | --- |
| Account Details (Broker Name) | `Accounts.broker` | Stored | Canonical broker name. |
| Account Details (Group Number) | `Accounts.broker_number` | Stored | Group number in Excel corresponds to broker number. |
| Account Details (Account Number) | `Accounts.account_number` | Stored | Stored as text to preserve zero padding. |
| Account Details (Account Nickname) | `Accounts.account_nickname` | Stored | Defaulted in code when missing. |
| Account identifier | `Accounts.account_id` | Derived | Auto-increment primary key. |
| Reverse split ticker | `reverse_split_log.ticker` (proposed) | Stored | From `stock_row` cost column. |
| Reverse split date | `reverse_split_log.split_date` (proposed) | Stored | From `date_row` in proceeds column. |
| Reverse split ratio | `reverse_split_log.split_ratio` (proposed) | Stored | From `ratio_row` in proceeds column. |
| Order cost/proceeds price | `reverse_split_account_entries.price` (proposed) | Stored | Value for the account row in cost/proceeds column. |
| Order type (cost/proceeds) | `reverse_split_account_entries.order_type` (proposed) | Derived | Derived from which column (cost vs. proceeds) contains the value. |
| Account label | `reverse_split_account_entries.account_id` (proposed) | Derived | Resolve from `Accounts` via broker + account number or nickname. |
| Order timestamp | `reverse_split_account_entries.timestamp` (proposed) | Stored | When the entry was captured/imported. |

Existing SQL tables for related data:

- `Accounts`: canonical account registry.
- `OrderHistory`: structured order events (action, quantity, price, timestamp).
- `HoldingsLive` / `HistoricalHoldings`: holdings snapshots.
- `account_mappings`: broker/account nickname mappings (replaces legacy JSON).
- `watchlist` / `sell_list`: reverse split watch and sell queues (replaces legacy JSON).

## Proposed SQL Tables for Excel-Only Concepts

### reverse_split_log
Tracks per-ticker reverse split metadata that used to live in the Excel sheet.

| Column | Type | Notes |
| --- | --- | --- |
| reverse_split_id | INTEGER PRIMARY KEY | Surrogate key. |
| ticker | TEXT NOT NULL | Stock symbol. |
| split_ratio | TEXT NOT NULL | Original split ratio string (e.g., "1-20"). |
| split_date | TEXT NOT NULL | Split effective date. |
| ingestion_timestamp | TEXT NOT NULL | When the entry was captured/imported. |
| source | TEXT NOT NULL | "excel_migration", "manual", etc. |

### reverse_split_account_entries
Tracks per-account cost/proceeds entries that were stored in the Excel grid.

| Column | Type | Notes |
| --- | --- | --- |
| entry_id | INTEGER PRIMARY KEY | Surrogate key. |
| account_id | INTEGER NOT NULL | FK to `Accounts.account_id`. |
| ticker | TEXT NOT NULL | Stock symbol. |
| order_type | TEXT NOT NULL | "cost" or "proceeds" derived from column position. |
| price | REAL NOT NULL | Value logged in the sheet cell. |
| timestamp | TEXT NOT NULL | When the entry was captured/imported. |
| source | TEXT NOT NULL | "excel_migration", "manual", etc. |

## Migration Guidance
- After migration, Excel should not be updated by the system. Any new entries
  should be written to the SQL tables above, and Excel should be considered
  read-only for audit or historical reference.
