# AutoRSA Broker Dry-Run Summary - 2026-06-05

Scope:
- Updated `auto-rsa/` to upstream `origin/main` at `c63971d` (`auto_rsa_bot` 2.2.0).
- Copied `AutoRSA-GUI.local/.env` to `auto-rsa/.env` for testing. `auto-rsa/.env` is ignored by git.
- Installed dependencies with `uv sync --python python3.12`.
- Initialized AutoRSA submodules.
- Installed Playwright Chromium and Firefox.
- Ran dry buy checks: `buy 1 AAPL <broker> dry`.

Configured brokers tested:
- Chase
- Fennel
- Fidelity
- Public
- Robinhood
- Schwab
- SoFi
- Vanguard
- Webull
- Wells Fargo

Results:

| Broker | Result | Notes |
| --- | --- | --- |
| Fennel | Passed dry run | Logged in and reported dry-run success across configured Fennel accounts. |
| Public | Mostly passed dry run | Logged in, skipped HYSA/non-tradable accounts, and passed preflight on several accounts. One account failed preflight due to insufficient deposit/buying power for 1 AAPL. |
| Chase | Blocked by 2FA input | Reached Chase login and prompted for code. CLI run has no interactive OTP path without Discord bot context, so login failed with EOF. |
| Fidelity | Failed login flow | After installing Firefox, Fidelity reached login but failed with: "Cannot get to login page. Maybe other 2FA method present." It also hit a Playwright sync API inside asyncio cleanup error afterward. |
| Robinhood | Failed verification/rate limit | Robinhood push verification started, then hit HTTP 429 Too Many Requests and login failed. |
| Schwab | Failed login | After installing Firefox, Schwab reached login path but reported unsuccessful login / username-password check. This may be credential format, headless/2FA behavior, or stale session state. |
| SoFi | Code bug fixed, then timed out | Upstream dispatcher called `sofi_run()` without the required `command` argument. I patched that locally. After patching, SoFi entered Chromium automation but timed out before producing log output. |
| Vanguard | Failed page load | After installing Firefox, Vanguard timed out loading the login page, then failed cleanup with an event-loop-closed Playwright error. |
| Webull | Failed login/API response parse | Webull login failed with JSON decode error from an empty/non-JSON response. |
| Wells Fargo | Failed Selenium login/init | Wells Fargo hit a Selenium timeout and did not initialize. Upstream `auto-rsa` Wells Fargo remains weaker than the local GUI Wells Fargo path. |

Local change made after pulling:
- `auto-rsa/src/brokerages/sofi_api.py`: made the legacy `command` argument optional and inferred holdings vs transaction from `StockOrder`. This is needed because `fun_run()` calls `sofi_run()` without `command`.

Raw logs:
- `/tmp/autorsa-broker-tests/*.log`

No live orders were submitted:
- All transaction commands were run with dry mode enabled.
- Dry mode was shown as `DRY: True` in the broker logs.

Recommended next fixes:
- Chase: run through a Discord bot context or add a CLI OTP path so Chase can complete 2FA in non-interactive dry tests.
- Fidelity: inspect the current Fidelity 2FA/login page and update the automation for the selected 2FA method.
- Robinhood: wait for rate limit cooldown before retesting; avoid repeated push checks.
- Schwab: validate credential format and whether headless login is blocked; test once with `HEADLESS=false`.
- SoFi: keep the dispatcher patch, then add bounded waits/logging around the Chromium login flow because it currently hangs until timeout.
- Vanguard: test login page loading outside headless mode and add better timeout cleanup.
- Webull: inspect the raw HTTP response causing JSON decode failure; likely expired/stale credentials or upstream API response change.
- Wells Fargo: prefer `AutoRSA-GUI.local` for Wells Fargo for now, because upstream `auto-rsa` Wells Fargo is Selenium-based and timed out during init.
