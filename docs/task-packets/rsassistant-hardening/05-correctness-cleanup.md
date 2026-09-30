# Packet 05: Deterministic Correctness Cleanup

Commit: `fix: harden split lifecycle and optional plotting`

## Files

- `utils/split_watch_utils.py`
- `rsassistant/bot/cogs/split_monitor.py`
- `rsassistant/bot/history_query.py`
- `rsassistant/bot/cogs/holdings.py`
- related tests

## Split lifecycle

Current behavior conflicts:
- `update_split_status()` moves passed-date `buying -> selling`
- `cleanup_expired_tickers()` deletes records merely because the split date passed

Change `splitstatus` and `splitlist` to advance status rather than delete active selling records. Retire `cleanup_expired_tickers()` or redefine it so it cannot delete an incomplete selling record.

Completion/removal remains based on `cleanup_completed_tickers()`: selling status, at least one bought account, and bought accounts equal sold accounts.

## Matplotlib

Remove module-level:

```python
import matplotlib.pyplot as plt
```

from `history_query.py`. Import it only in the plotting path:

```python
try:
    import matplotlib.pyplot as plt
except ImportError:
    await ctx.send("Holdings history plotting is unavailable on this installation.")
    return
```

Do not add matplotlib as a mandatory dependency. `HoldingsCog` must load without it.

## Tests

- passed split remains tracked in selling phase
- completed split is removable
- incomplete selling split is not removed
- holdings cog imports without matplotlib
- only history plotting degrades when matplotlib is absent
