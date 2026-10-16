# Migration audit addendum — 2026-10-16

Follow-up to `docs/migration-audit-2026-10-15.md`. Read-only investigation plus the
two live changes listed in section 6. No orders were placed. No `.env` contents,
credentials, or full account numbers are recorded here.

## 1. Who recreated the containers at 23:43 ET on 2026-10-15

Most likely **the user, via the `redocker` shell alias**, not an automated mechanism.

- `~/.bash_aliases`: `alias redocker='docker compose down && docker compose up --build -d'`
  (also present twice in `~/.bash_history`; history has no timestamps).
- `auto-rsa/.env` was modified at 23:37:35. `dockerd` began stopping containers at
  23:37:39 (several unrelated compose projects were also stopped/started).
- Images were then built: `auto-rsa-holdings:local` 23:39:47, `rsassistant-rsassistant` 23:43:04.
  Both containers carry compose label `config_files=.../RSAssistant/docker-compose.yml`.
- No systemd timers, cron entries, git hooks, or file watchers touch this stack. No Claude
  session was active in that window.
- Consequence: **`--build` always builds from whatever is in the working tree.** There is no
  review gate between an uncommitted edit and production. Also seen: another restart at
  13:57 on 10-15 (Docker log), and `docker-compose.yml`/`Dockerfile` edited 06:04 that day.

## 2. Exact cause of the Fidelity / Chase browser-launch failure

Two different things, one of which was my own test artifact.

1. **Artifact of running the CLI instead of the bot.** `auto_rsa_bot holdings all` (CLI form)
   leaves `docker_mode=False`; Fidelity then starts Chromium with its sandbox on, which fails
   as non-root (`No usable sandbox`) and surfaces as zendriver's "Failed to connect to browser".
   Run with `docker_mode=True` (what the live bot does) Fidelity logs in, verifies its session,
   and returns 25 accounts, 0 errors. **The live Fidelity browser launch is not broken.**
2. **Chase is genuinely broken in the container**, for two stacked reasons:
   - `auto-rsa/creds/chase_1` held Chromium `Singleton*` lock symlinks created on host
     `archdesk` on 2026-08-14 ("profile in use by another computer"). Removed (locks only).
   - `HEADLESS=false` in the container makes the `chase` library take its headed branch, which
     passes no `--no-sandbox`. With `HEADLESS=true` the browser launches.
   - After both fixes Chase still reports `Timed out waiting for network response` and finds
     **zero accounts**. Not yet explained (possible Chase-side change or session not actually
     authenticated).
3. **Wells Fargo**: its earlier "Driver not found" was the same CLI artifact. In docker mode it
   reaches device approval and waits 3 minutes for a phone approval. Needs a human.

Leftover hygiene: defunct `chrome_crashpad` zombies accumulate (no init process in the
container); `/dev/shm` is 64 MB.

Original failing trace preserved at
`/tmp/claude-1000/-home-braydenchaffee-Production-RSAssistant/423e0357-6d50-4edd-a010-80a06400e556/scratchpad/holdings_run.ORIGINAL.log`
(plus `chase_docker_mode.BEFORE.log` and `chase_docker_mode.AFTERLOCK.log`).

## 3. Trace of a historical order (FRGT autobuy, 2026-10-15 13:23 ET)

| Step | Evidence | Result |
|---|---|---|
| Alert received (MonitoRSS, nasdaqtrader ECA2026-735) | `on_message` 13:23:10 | ok |
| Policy analysis (LLM) | `policy_resolver`/`openai_utils`, HTTP 200 | ok |
| Split watch recorded | `Added split watch: FRGT @ 2026-10-19` 13:23:17.9 | ok |
| Command sent | `order_exec`: `!rsa buy 1 FRGT all false` 13:23:18.15; send-log row 208 | ok |
| Autobuy "scheduled" | `Scheduled autobuy ... (uuid)` 13:23:18.29 | ok (nothing downstream confirms it) |
| auto-rsa replies | 13:23:30–31: two bot messages | **dropped: `Ignoring message from untrusted bot ID`** |
| Parse -> price -> `OrderHistory` | no "Matched order", "Processing complete order", or "Order data saved" lines | **never reached** |
| Broker acknowledgement | not visible anywhere in RSAssistant | **not recorded** |

Two independent defects stop confirmations from ever reaching `OrderHistory`:

- **A. Trusted-bot gate (new, since ~2026-10-14).** `on_message.py` (added in `bfe2d23`,
  2026-10-03) ignores every non-embed bot message unless the sender id equals
  `TRUSTED_AUTORSA_BOT_ID`. That variable is **unset** in the live container, so the gate
  rejects all auto-rsa order replies (127 occurrences, one sender id, 10-14 to 10-16). Fails
  closed, silently, at WARNING.
- **B. Price lookup drops orders (since at least Aug; explains the July-30 gap).**
  `handle_complete_order` returns without persisting when `get_last_stock_price` is `None`.
  The container pins `yfinance==0.2.40`, which now returns `JSONDecodeError` for **every**
  ticker (verified live, including AAPL). 237 "Price fetch failed" events since 08-16 and zero
  successful saves. `yfinance 1.7.0` in an isolated venv returns prices for AAPL/CURX/VMAR.
  Design smell: a confirmed fill is discarded because an unrelated price quote failed.

Not fixed: neither is changed in code or config. Autobuy also marks itself "scheduled" with no
feedback loop, which is the requested/submitted/accepted/filled/reconciled gap the unified
design should close.

## 4. Legacy vs canonical holdings sources

| Source | State |
|---|---|
| `volumes/db/auto_rsa_holdings.json` (auto-rsa export, "legacy" JSON) | Fresh (02:08 today), 545 entries; Fennel 6, Public 2, Robinhood 3, Fidelity 21, WF 5, Vanguard 1 accounts. Every snapshot account exists in `Accounts` (Fidelity 19/21 by exact number, 20/21 by last-4). |
| `HoldingsLive` (append-only history) | Fennel/Public/Robinhood updated to 03:10Z; Fidelity last 2026-08-28; Wells Fargo/Vanguard 2026-08-20. |
| `holdings_current` ("canonical" replace table) | **One row, and it is test pollution**: `source=/tmp/pytest-of-braydenchaffee/pytest-2/test_save_holdings_to_csv_disa0/holdings.csv`, observed 2026-10-12 17:44. Accounts `B` and `BrokerA` are fixtures too. A pytest run wrote into the production DB on 10-12. |
| `volumes/logs/holdings_log.csv` | Stale compatibility CSV (snapshot rows dated 2026-08-20). |

Why the fresh Fidelity snapshot never lands: `save_holdings_to_csv` (`utils/csv_utils.py`)
catches every exception and only logs it, and `holdings_importer` still logs
"Imported N holdings entries". `app.log` shows the swallowed errors:
`Invalid holdings observed_at in row 1: ''` (10-14, 10-15 x5, 10-16 x2),
`Row 2: invalid Timestamp value ''` (10-10, 10-13) and `database is locked` (10-15). The
polluted `holdings_current` row is read back as an "existing" row and fails validation, so the
snapshot import is rejected. Only live-bot refresh paths (`!rsa holdings`, 10-15) wrote
successfully. Net: **two writers, no single source of truth, and failures reported as success.**

## 5. Recommended order of work (diagnosis only; no changes made for these)

1. Set `TRUSTED_AUTORSA_BOT_ID` (the ignored sender id is in the logs) — security-gate
   decision for the user.
2. Upgrade `yfinance` (pin `1.7.0`) and make fill persistence independent of price lookup.
3. Delete the pytest-polluted rows (`holdings_current`, accounts `B`/`BrokerA`) after a DB
   backup, then add a test guard so tests cannot open the production database.
4. Make the importer report failure when `save_holdings_to_csv` fails.
5. Reconcile Fidelity "order button clicked but confirmation not detected" orders against the
   actual Fidelity order history **before** any retry.
6. Chase empty-account response; Wells Fargo needs a human device approval.
7. Take a DB + `creds/` backup and add scheduled backups before schema work.

## 6. Live changes made during this investigation

- Removed three stale `Singleton*` lock symlinks from `auto-rsa/creds/chase_1`.
- Set `HEADLESS=true` in `auto-rsa/.env` (was `false`); backup of the prior file at
  `~/.rsa-backups/auto-rsa.env.pre-headless-20261016` (mode 600, outside the repo).
  Recreated only the `auto-rsa` container (`docker compose up -d auto-rsa`, no rebuild).
- Ran read-only holdings pulls (Fidelity, Chase, Wells Fargo, and one `holdings all`) which
  refreshed `auto_rsa_holdings.json`. No orders placed.
