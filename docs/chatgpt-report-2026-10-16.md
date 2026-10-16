# RSAssistant + auto-rsa: local investigation report (2026-10-16)

Self-contained report for design work. Answers the four open questions. Everything
below was observed on the local machine (`archdesk`) by reading code, logs, the
production SQLite database, and the running containers. **No live order was placed
at any point.** Secrets, `.env` values, and full account numbers are deliberately
omitted. Times are America/New_York unless marked Z (UTC).

## 0. Context in one paragraph

Two apps cooperate over Discord and a shared volume. **RSAssistant** (Python 3.12,
discord.py, APScheduler, SQLite schema v10) watches split alerts, queues autobuys and
sends `!rsa buy|sell|holdings ...` text commands. **auto-rsa** (a nested, gitignored
fork repo at `RSAssistant/auto-rsa`, Python 3.14 image) is a second Discord bot that
receives those commands, logs into brokers, places orders, replies in the channel, and
writes a holdings snapshot `volumes/db/auto_rsa_holdings.json` that RSAssistant imports
every 5 minutes. Coupling is therefore (a) free-text Discord commands and replies parsed
by regex, and (b) a JSON file on a shared volume.

## 1. Why the containers were recreated at 23:43 on 2026-10-15

**Most likely the user running their `redocker` shell alias; not an automated mechanism.**

- `~/.bash_aliases`: `alias redocker='docker compose down && docker compose up --build -d'`
  (also in shell history twice; history has no timestamps).
- `auto-rsa/.env` was modified at 23:37:35. `dockerd` started stopping containers at
  23:37:39 (several unrelated compose projects were stopped/started too). Images were
  built at 23:39:47 (`auto-rsa-holdings:local`) and 23:43:04 (`rsassistant-rsassistant`).
  Both containers carry compose label `config_files=.../RSAssistant/docker-compose.yml`.
- Ruled out: systemd timers (only man-db, tmpfiles, shadow, paccache, keyring), user
  cron (unrelated projects), git hooks (none), file watchers, Watchtower (not running),
  and Claude sessions (none active in that window).
- Why it matters: `--build` builds from the **working tree**, so any uncommitted edit goes
  straight to production with no review gate. There is no real production branch
  (`origin/production` has been dead since May 2025). Also seen: a restart at 13:57 on
  10-15, and `docker-compose.yml`/`Dockerfile` edited at 06:04 that day.
- Side effect: the 23:43 rebuild shipped schema migration 10 to the production DB
  (`user_version=10`) with no automated backup. There is still no scheduled DB backup.

## 2. Exact cause of the Fidelity browser-launch failure

**The live Fidelity browser launch is not broken.** The failure I first reported was an
artifact of how I invoked it.

- Running the CLI form (`auto_rsa_bot holdings all`) leaves `docker_mode=False`.
  Fidelity then starts Chromium via zendriver with `sandbox=True`; as non-root in the
  container this fails with `No usable sandbox`, which zendriver reports as
  `Failed to connect to browser`. The live bot runs `auto_rsa_bot docker`
  (`docker_mode=True` -> `sandbox=False`).
- Re-run Fidelity-only with `docker_mode=True` (holdings only, read-only): it logged in
  from the saved profile with no 2FA, passed `Fidelity session verified`, and returned
  **25 accounts, 0 errors**, then wrote a fresh `auto_rsa_holdings.json`.
- Runtime verified healthy: `DISPLAY=:99`, Xvfb running, Chromium 155.0.8059.39 with a
  matching chromedriver, `/dev/shm` 64 MB, a clean isolated headless launch against a
  non-broker page succeeded (with `--no-sandbox`), a headed launch on Xvfb succeeded.
  Minor: defunct `chrome_crashpad` zombies accumulate (container has no init reaper).

### Related, genuinely broken: Chase and Wells Fargo

- **Chase**: two stacked defects. (1) `auto-rsa/creds/chase_1` contained Chromium
  `Singleton*` lock symlinks created on host `archdesk` on 2026-08-14 ("profile in use
  by another computer"); I removed those three symlinks only. (2) The container had
  `HEADLESS=false`, which sends the `chase` library down a headed branch that never
  passes `--no-sandbox`; I set `HEADLESS=true` (previous file backed up outside the repo)
  and recreated only the auto-rsa container. After both fixes the browser launches, but
  Chase says `Timed out waiting for network response` and finds **zero accounts**.
  Unexplained; possibly a Chase-side change or an unauthenticated session.
- **Wells Fargo**: the earlier "Driver not found" was the same CLI artifact. In docker
  mode it reaches device approval and waits 3 minutes for a human phone approval.
- **Vanguard**: login prompts for an SMS code via `input()`; no stdin in a CLI run, so it
  fails with `EOFError`. In the real bot it asks for the code in Discord.
- Schwab: `Page.goto` timeout. Webull/BBAE/DSPAC/Firstrade/Tastytrade/Tornado/Tradier:
  `Function did not complete successfully` (not credentialed or not working).

## 3. Trace of one historical order (FRGT autobuy, 2026-10-15 13:23 ET)

Source: `volumes/logs/app.log` plus `rsa_order_send_log` row 208.

| # | Step | Evidence | Outcome |
|---|---|---|---|
| 1 | Alert arrives (MonitoRSS embed, Nasdaq ECA2026-735) | `on_message` 13:23:10 | ok |
| 2 | Reverse split detected, LLM policy analysis | `policy_resolver`, OpenAI HTTP 200 | ok |
| 3 | Split watch recorded | `Added split watch: FRGT @ 2026-10-19` 13:23:17.9 | ok |
| 4 | Command sent to the auto-rsa channel | `order_exec` `!rsa buy 1 FRGT all false` 13:23:18.15; send-log id 208 | ok |
| 5 | Autobuy marked "scheduled" | `Scheduled autobuy: FRGT x1 ... (uuid)` 13:23:18.29 | ok, but nothing downstream confirms it |
| 6 | auto-rsa replies in channel | 13:23:30 and 13:23:31 (two bot messages) | **dropped: "Ignoring message from untrusted bot ID"** |
| 7 | Parse -> price -> `OrderHistory` | no `Matched order`, `Processing complete order`, `Order data saved` lines | **never reached** |
| 8 | Broker acknowledgement | not visible anywhere in RSAssistant | **not recorded** |

Two independent defects stopped every confirmation from reaching `OrderHistory`:

- **A. Trusted-bot gate (since ~10-14).** `on_message.py` (commit `bfe2d23`, 10-03)
  ignores every non-embed bot message unless the sender id equals
  `TRUSTED_AUTORSA_BOT_ID`. It was **unset** in the live container, so all auto-rsa order
  replies were rejected (127 events, one sender id "Money Printer 5000", 10-14..10-16).
  Fails closed and silently (WARNING only). That same id also gates `..updatebot` and
  `..revertupdate`.
- **B. Price lookup drops orders (since at least Aug; explains the July-30 gap).**
  `handle_complete_order` returned without persisting when `get_last_stock_price` was
  `None`. The image pinned `yfinance==0.2.40`, which returns `JSONDecodeError` for every
  ticker (verified live incl. AAPL). 237 "Price fetch failed" events since 08-16 and
  zero saves. `yfinance 1.7.0` works. A confirmed fill was being discarded because an
  unrelated quote call failed.
- Observed scale: `OrderHistory` has **no rows after 2026-07-30** while the send log has
  151 sends since 2026-08-05 (209 total, 2026-05-14..2026-10-15).
- Other reply noise: Fennel orders fail with HTTP 429 (rate limit); Fidelity logs
  `Order button clicked but confirmation not detected` ~1,100 times, so some Fidelity
  orders are **ambiguous** (may or may not have filled). Success replies such as
  `sell 1.0 of ZCMD in xxxx9752: Success` also hit `No match found` in the regex parser.
- Structural gap (for the design): the pipeline has no durable states between "command
  sent" and "row in OrderHistory". There is no requested/submitted/accepted/filled/
  reconciled lifecycle, no correlation id between a sent command and the replies, and
  the autobuy "scheduled" log line is the last thing RSAssistant knows.

## 4. Legacy vs canonical holdings sources

| Source | Role | State today |
|---|---|---|
| `volumes/db/auto_rsa_holdings.json` | auto-rsa export (legacy handoff) | Fresh (written 02:08 today by my Fidelity run), 545 entries: Fennel 6, Public 2, Robinhood 3, Fidelity 21, Wells Fargo 5, Vanguard 1 accounts |
| `HoldingsLive` | append-only history | Fennel/Public/Robinhood to 03:10Z; **Fidelity last 2026-08-28**; Wells Fargo/Vanguard 2026-08-20 |
| `holdings_current` | intended canonical "replace" table | **1 row, and it is test pollution**: source `/tmp/pytest-of-.../holdings.csv`, observed 2026-10-12 |
| `volumes/logs/holdings_log.csv` | compatibility CSV | stale (rows dated 2026-08-20) |
| `HistoricalHoldings` | daily history | 43,132 rows |

Findings:

- **Test pollution in production.** A pytest run wrote into the production DB on
  2026-10-12 (fixture accounts `B` and `BrokerA`, the one `holdings_current` row).
  Cause: `VOLUMES_DIR` resolves at import time and defaults to the real `volumes/`.
- **Silent import failures.** `save_holdings_to_csv` swallowed every exception and
  `holdings_importer` still logged `Imported N holdings entries`. Real errors in
  `app.log`: `Invalid holdings observed_at in row 1: ''`, `Row 2: invalid Timestamp
  value ''`, `database is locked`.
- **Two root bugs behind those errors.** (1) `_normalize_holding_row` dropped the
  `Timestamp` of CSV-shaped rows, so the existing polluted row failed validation on every
  refresh. (2) `update_holdings_live_batch` opened a write transaction and then called a
  nickname lookup that upserts on a *second* connection, deadlocking itself for any
  account without a saved nickname (Fidelity's accounts). Only live `!rsa holdings`
  refresh paths (10-15) ever succeeded.
- **Two writers, no single source of truth**, failures reported as success.
- Importer dedupe caveat: it records the snapshot's mtime as imported even when the save
  failed (fixed for new failures, but the 02:08 file was already marked imported, so
  Fidelity will not update until auto-rsa rewrites the snapshot).

## 5. The `Accounts` table is unreliable (user asked to audit it)

- 225 rows but only **38 identities** in the live snapshot.
- The same real account appears under several spellings: `CHASE`/`Chase 1` vs
  `Chase`/`1`; broker casing (`Fidelity` vs `FIDELITY`); orders use last-4 or
  `Account N` labels while the snapshot uses full ids or names (Fennel `aaaaaaaad`,
  Fidelity 9-digit and long hash-like ids, Wells Fargo names). Collapsing case and
  number labels gives ~150 canonical rows; ~38 are active; ~60 more exist only because
  of old order history.
- Dry run of the cleanup script: 3 test accounts + 1 pytest row + 29 accounts with no data
  anywhere (Sofi 13, Fidelity 6, Chase 4, Public 3, Webull 2, Fennel 1) are deletable.
- Proposed identity design (not built): canonical `(broker, group, last4)` plus an alias
  table mapping every observed label (full id, masked id, `Account N`, nickname) to it.

## 6. Current broker health vs the user's priority

Priority stated by the user: Fidelity > Fennel > Robinhood = Public = Wells Fargo >
Schwab > Chase > Sofi > Webull (Webull only if it can actually work). Credentials are
loaded for Fennel, Fidelity, Public (2 accounts), Robinhood, Schwab, Sofi, Vanguard,
Webull, Wells Fargo.

| Broker | Login/fetch | Notes |
|---|---|---|
| Fidelity | works in docker mode | DB stale since 08-28 (import bugs above); order confirmation ambiguous |
| Fennel | works | order calls rate-limited (HTTP 429); fills not recorded since 07-30 |
| Robinhood | works | quote lookups 400 for PIXY/XTKG/ORGN (pricing only) |
| Public | works | all 5 accounts report "No holdings" in the CLI pull; verify |
| Wells Fargo | needs phone approval each login | profile never trusted |
| Schwab | page timeout | no data since Aug 2025 |
| Chase | browser fixed, 0 accounts | unexplained |
| Vanguard | needs SMS code | interactive |
| Sofi, Webull | no data since Aug 2025 | likely stale credentials |

## 7. Other facts the design needs

- Four open split watches must survive any cutover: BTOC (2026-10-15), KNDI (10-16),
  FRGT (10-19), OBAI (10-19), all in `buying`.
- auto-rsa is a nested gitignored repo (`braydio/auto-rsa`, 2 commits ahead and 0 behind
  upstream NelsonDane); `./auto-rsa/src` is bind-mounted read-only over the image, so
  disk files are what runs. Five overlapping copies of broker code exist; the Arch GUI
  fork has uncommitted Chase/Fennel/Wells Fargo edits that may exist nowhere else.
- Three modules have zero callers (`reverse_split_parser`, `autobuy_utils`,
  `audit_watchlist_utils`); `sql_utils` is test-only (static check).
- No scheduled DB backup exists; Python versions differ (RSAssistant 3.12, auto-rsa 3.14).

## 8. Changes made during the investigation (all local; nothing pushed)

Live changes:
1. Removed three stale `Singleton*` lock symlinks from `auto-rsa/creds/chase_1`.
2. `auto-rsa/.env`: `HEADLESS=false` -> `true`; `auto-rsa` container recreated (no rebuild).
3. `config/.env`: added `TRUSTED_AUTORSA_BOT_ID` (the single id that was being ignored).
4. Rebuilt and recreated `RSAssistant` from commit `83a6b00` (user ran it). Verified healthy,
   `yfinance 1.7.0`, live AAPL price lookup now succeeds.
5. Read-only holdings pulls (Fidelity, Chase, Wells Fargo, one `holdings all`) refreshed
   `auto_rsa_holdings.json`. Backups (mode 600, outside the repo) in `~/.rsa-backups/`:
   a consistent DB copy and both prior `.env` files.

Code, commit `83a6b00` (local only):
- Persist confirmed orders with price 0.0 when the quote lookup fails; `yfinance` -> 1.7.0.
- Fix the batch-write self-deadlock; preserve `Timestamp`; `save_holdings_to_csv` returns
  success/failure and the importer no longer reports failed saves as imported.
- Root `conftest.py` isolates pytest from the production `volumes/` directory.
- `.github/dependabot.yml` (pip weekly grouped, docker weekly, github-actions monthly);
  becomes active only after the repo is pushed. auto-rsa already has `renovate.json`.
- `scripts/cleanup_accounts.py` (dry run by default; `--apply` backs up then deletes).
- Tests: 218 unittests pass; pytest 301 pass, 6 fail (same 6 as clean HEAD: all_command,
  brokerwith, order_remove x2, sell_queue x2).

State right now: account cleanup **not yet applied** (still 225 rows, `holdings_current`
still has the 1 polluted row); the earlier production DB migration to v10 is in place.

## 9. Recommended milestone 1 (matches the user's stated direction)

A verified, repairable execution pipeline before any command overhaul:

1. A durable lifecycle per order: requested -> submitted -> accepted -> filled ->
   reconciled (plus failed/ambiguous), keyed by a correlation id carried in the command
   and its replies, with no dependence on price lookups or regex parsing of free text.
2. One holdings source of truth (single writer), explicit failure reporting, and an
   idempotent importer.
3. Fidelity first: reconcile ambiguous "confirmation not detected" orders against the
   actual Fidelity order history before any retry; never auto-retry an ambiguous order.
4. A stable account identity + alias table before any schema reorg.
5. Deploy hygiene: pin what runs to a commit, drop the `redocker`-from-working-tree
   habit, scheduled DB backups, dependency automation, and a test guard against the
   production DB (done).

## 10. Questions still open

- Why Chase logs in but returns no accounts; which Schwab/Sofi/Webull credentials are
  still valid; whether Public really has no holdings.
- Which of the five broker-code copies is authoritative for Chase/Fennel/Wells Fargo.
- Whether the ULT-MA plugin's expected auto-rsa HTTP API exists (plugin disabled live).
- Fidelity orders whose confirmation was not detected: filled or not (needs Fidelity's
  own order history; not checkable from here).
