# Packet 01: Order Integrity

Commit: `fix: preserve failed orders and use unique order ids`

## Files

- `utils/order_exec.py`
- `rsassistant/bot/cogs/orders.py`
- `unittests/order_send_commands_test.py`
- `unittests/order_queue_tasks_test.py`
- `unittests/ord_command_test.py` as needed

## Changes

### Failed send must retain order

In `send_sell_command()`, replace swallowed failures:

```python
except Exception as e:
    logger.error(f"Error sending sell command: {e}")
```

with propagation:

```python
except Exception:
    logger.exception("Error sending RSA command")
    raise
```

If no target channel is available, raise `RuntimeError` instead of returning normally.

`schedule_and_execute()` must call `remove_order(order_id)` only after a successful send. A failed send must also leave any sell-list entry intact.

### Unique IDs

Replace ticker/minute/action IDs such as:

```python
f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_{action.lower()}"
```

with `uuid4().hex`. Generate once when creating a new order and reuse that ID through queue persistence/resume/removal. Never regenerate an ID while restoring a persisted order.

## Tests

- successful send sends once and removes queued order
- Discord `.send()` raises -> queued order remains, no sent-order audit entry, sell-list remains
- no target channel -> same retention
- two identical same-minute orders receive distinct IDs and remain independently addressable
