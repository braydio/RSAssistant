# Sent `!rsa` Order Audit Log

RSAssistant persists an audit trail whenever it sends a canonical `!rsa` order command to Discord.

## Storage

- File: `volumes/db/order_send_log.json`
- Retention: last 1000 entries (older entries are trimmed)
- Entry fields:
  - `sent_at` (UTC ISO8601)
  - `command`
  - `channel_id`
  - `ticker`
  - `action`
  - `quantity`
  - `broker`

## Query commands

- `..orders [limit|ticker] [ticker|action] [action]`
  - Examples: `..orders`, `..orders 20`, `..orders TSLA`, `..orders TSLA sell`
  - Limit defaults to 10 and is capped at 50.
- `..lastorder [ticker]`
  - Shows the latest sent order globally or for a specific ticker.

## Notes

- Only canonical order commands in the form `!rsa <buy|sell> <qty> <ticker> <broker> ...` are logged.
- Logging occurs at send time, so the timestamp reflects when RSAssistant sent the command to Discord.
