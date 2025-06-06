# 📈 Development Plan: Auto Orders Based on Watchlist + Holdings

This feature will trigger automatic orders based on whether a ticker is:

- Present in the **watchlist** (`watch_list_manager.py` or `watch_utils.py`)
- Present in or recently exited from **holdings** (`history_query.py`, `csv_utils.py`)

---

## 🔧 Target Files for Integration

- `utils/watch_list_manager.py` — Add ticker check and insert logic
- `utils/history_query.py` — For verifying recent holding status
- `utils/on_message_utils.py` — Main alert processing and decision logic
- `utils/order_exec.py` — For submitting the auto orders
- `utils/autobuy_utils.py` — If using existing auto-execution patterns

---

## ✅ Development Checklist

### Step 1: Ticker Status Detection Logic

- [ ] Add utility function to detect if ticker is in active holdings (from `history_query.py`)
- [ ] Add function to check if ticker was held within X days
- [ ] Extend `watch_list_manager.py` or `watch_utils.py` to check if already watched

### Step 2: Decision Logic in `on_message_utils.py`

- [ ] Hook into alert parsing pipeline after reverse split detection / signal trigger
- [ ] Add decision branch: If not watched but in holdings/recently held, continue
- [ ] Call `watch_list_manager.add_watch(ticker)` if not present

### Step 3: Auto Order Trigger (Optional Mode)

- [ ] Add flag to trigger order once ticker is added from holdings logic
- [ ] Use `order_exec.py.place_order()` or `autobuy_utils.schedule_autobuy()`
- [ ] Respect rate limits and trading schedule (during market hours)

### Step 4: Logging + Visibility

- [ ] Add logging in `logging_setup.py` for traceability
- [ ] Confirm Discord notification includes "auto order from holdings"

### Step 5: Testing + Rollout

- [ ] Create unit tests for watchlist + holdings checks
- [ ] Test tickers: one in watchlist, one recently sold, one never held
- [ ] Roll out with dry-run first before enabling live orders

---

## ⚠️ Potential Issues

- Holdings data might be stale or incomplete if CSV parsing fails
- Tickers might reappear in alerts that were sold off for good reason
- Re-adding to watchlist may interfere with manual strategies
- Race conditions if multiple auto-order triggers fire simultaneously
- Required rate-limiting or cooldown to avoid overtrading

---
