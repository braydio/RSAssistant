# Packet 04: Market Scheduling Consolidation

Commit: `fix: centralize market session scheduling`

## Files

- `utils/market_calendar.py`
- `rsassistant/bot/cogs/orders.py`
- `rsassistant/bot/tasks.py`
- market/order scheduling tests

## Changes

Do not add a third-party exchange-calendar dependency in this packet.

Remove the duplicate market-hours implementation in `OrdersCog.process_order()`:

```python
now = datetime.now()
market_open = now.replace(hour=9, minute=30, ...)
market_close = now.replace(hour=16, minute=0, ...)
def next_open(...):
    ...
```

Use the existing helpers from `utils.market_calendar` and timezone-aware:

```python
now = datetime.now(MARKET_TZ)
```

Use `is_market_open_at()` and `next_market_open()` everywhere order scheduling/rescheduling needs session decisions. Do not duplicate weekday/open/close logic in cogs/tasks.

Preserve accepted input formats:
- `HH:MM`
- `mm/dd`
- `mm/dd HH:MM`

Fix the current validation message so it names those actual formats.

## Tests

- before open
- during open
- after close
- Saturday
- Sunday
- configured `MARKET_HOLIDAYS`
- returned execution times are timezone-aware America/New_York
