# Excel to SQL Mapping Reference

## Status Note
Excel is deprecated and non-authoritative after migration. The SQL database and
JSON/structured logs are the sources of truth, and Excel should be treated as a
historical artifact only.

## Excel Sheet Enumeration from `utils/excel_utils.py`

`utils/excel_utils.py` references the following worksheet names:

1. `Account Details`
2. `Reverse Split Log`

No other sheet name is explicitly used for business logic in this module.

## Excel Sheet Layouts (Deprecated)

### `Account Details`

The `index_account_details` workflow reads rows starting at row `2` and consumes
columns `A:D`.

| Column | Header (inferred) | Meaning in Excel | SQL Mapping |
| --- | --- | --- | --- |
| A | Broker Name | Broker identifier namespace for an account. | `Accounts.broker`, `account_mappings.broker` |
| B | Group Number | Broker grouping / broker number partition. | `Accounts.broker_number`, `account_mappings.group_number` |
| C | Account Number | Raw account number, normalized to 4-char zero-padded text before write. | `Accounts.account_number`, `account_mappings.account_number` |
| D | Account Nickname | Human-readable account label; generated when missing. | `Accounts.account_nickname`, `account_mappings.account_nickname` |

Stored vs. derived notes:

- `account_number` is **stored** in SQL as text after normalization.
- default nickname generation (`"Account N"`) is **derived** at ingest time,
  then the resulting value is **stored**.

### `Reverse Split Log`

Row indices/constants defined in `utils/excel_utils.py`:

- `stock_row = 1`
- `date_row = 1`
- `ratio_row = 2`
- `order_row = 3`
- `account_start_row = 4`
- `account_start_column = 1`

Column layout used for per-account values:

- Repeating 3-column block per ticker event:
  1. **Cost column** (`N`):
     - `row 1` (`stock_row`) stores ticker symbol.
     - `row 2` (`ratio_row`) stores label text `"Split Ratio:"`.
     - `row 3` (`order_row`) stores `"Cost"`.
     - `rows >= 4` store account-level price values for cost-side entries.
  2. **Proceeds column** (`N+1`):
     - `row 1` (`date_row`) stores split date.
     - `row 2` (`ratio_row`) stores split ratio value.
     - `row 3` (`order_row`) stores `"Proceeds"`.
     - `rows >= 4` store account-level price values for proceeds-side entries.
  3. **Spacer column** (`N+2`): formatting spacer, no business value.
- Account labels are in column `A`, starting at `account_start_row`.
- Lookup helpers scan ticker columns in steps of 2 (`cost`, then `proceeds`),
  effectively treating spacer columns as non-data.

## Excel Concept → SQL Table/Column Mapping

| Excel Concept | SQL Table.Column | Existing or New | Stored or Derived | Notes |
| --- | --- | --- | --- | --- |
| Broker Name (`Account Details!A`) | `Accounts.broker` | Existing | Stored | Canonical broker string. |
| Broker Name (`Account Details!A`) | `account_mappings.broker` | Existing | Stored | Compatibility mapping table. |
| Group Number (`Account Details!B`) | `Accounts.broker_number` | Existing | Stored | Numeric/text broker grouping. |
| Group Number (`Account Details!B`) | `account_mappings.group_number` | Existing | Stored | String representation in mapping rows. |
| Account Number (`Account Details!C`) | `Accounts.account_number` | Existing | Stored | Persisted as zero-padded text. |
| Account Number (`Account Details!C`) | `account_mappings.account_number` | Existing | Stored | Same normalized value. |
| Account Nickname (`Account Details!D`) | `Accounts.account_nickname` | Existing | Stored | Final resolved nickname. |
| Account Nickname (`Account Details!D`) | `account_mappings.account_nickname` | Existing | Stored | Mirrors mapping lookup surface. |
| Default nickname generation | n/a (logic in `generate_account_nickname`) | Existing logic | Derived then Stored | `"Account N"` calculated from existing nicknames. |
| Account row label (`Reverse Split Log!A{row}`) | `Accounts.account_id` | Existing | Derived | Resolve account via broker + nickname/number. |
| Ticker (`stock_row` in cost col) | `reverse_split_log.ticker` | New (proposed) | Stored | One ticker per reverse split log record. |
| Split date (`date_row` in proceeds col) | `reverse_split_log.split_date` | New (proposed) | Stored | Source date string/date from Excel. |
| Split ratio (`ratio_row` in proceeds col) | `reverse_split_log.split_ratio` | New (proposed) | Stored | Keep source representation (e.g., `1-20`). |
| Cost/Proceeds header (`order_row`) | `reverse_split_account_entries.order_type` | New (proposed) | Derived | Derived from whether value came from cost or proceeds column. |
| Account price cell (`rows >= 4`) | `reverse_split_account_entries.price` | New (proposed) | Stored | Numeric price payload. |
| Cell capture moment | `reverse_split_account_entries.timestamp` | New (proposed) | Stored | Capture/ingestion timestamp. |
| Import metadata | `reverse_split_log.ingestion_timestamp`, `reverse_split_log.source`, `reverse_split_account_entries.source` | New (proposed) | Stored | Audit lineage for migration and post-migration writes. |

## Proposed SQL Tables for Excel-Only Concepts

### `reverse_split_log`

Tracks per-ticker reverse split metadata that previously lived in header rows of
`Reverse Split Log`.

| Column | Type | Notes |
| --- | --- | --- |
| reverse_split_id | INTEGER PRIMARY KEY | Surrogate key. |
| ticker | TEXT NOT NULL | Stock symbol. |
| split_ratio | TEXT NOT NULL | Original split ratio string (e.g., `1-20`). |
| split_date | TEXT NOT NULL | Split effective date from source. |
| ingestion_timestamp | TEXT NOT NULL | When ingested/migrated. |
| source | TEXT NOT NULL | e.g., `excel_migration`, `manual`, `feed_parser`. |

### `reverse_split_account_entries`

Tracks per-account cost/proceeds values from `Reverse Split Log` account rows.

| Column | Type | Notes |
| --- | --- | --- |
| entry_id | INTEGER PRIMARY KEY | Surrogate key. |
| reverse_split_id | INTEGER NOT NULL | FK to `reverse_split_log.reverse_split_id`. |
| account_id | INTEGER NOT NULL | FK to `Accounts.account_id`. |
| ticker | TEXT NOT NULL | Redundant convenience column for read performance (optional if joining via `reverse_split_id`). |
| order_type | TEXT NOT NULL CHECK(order_type IN ('cost','proceeds')) | Derived from column family. |
| price | REAL NOT NULL | Account-specific cost/proceeds value. |
| timestamp | TEXT NOT NULL | Capture/ingestion time. |
| source | TEXT NOT NULL | e.g., `excel_migration`, `manual`. |

## Migration Guidance

- After migration, Excel should not be updated by the system.
- New reverse split metadata and account entries should be written to SQL,
  optionally mirrored to JSON/CSV logs for reporting compatibility.
- Excel is explicitly non-authoritative after migration; it is retained only for
  historical audit and reconciliation.
