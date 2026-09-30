# Packet 02: Command Authorization

Commit: `security: gate operational discord commands`

## Files

- `rsassistant/bot/checks.py` (new)
- `utils/config_utils.py`
- `config/.env.example`
- `rsassistant/bot/cogs/admin.py`
- `rsassistant/bot/cogs/orders.py`
- `rsassistant/bot/cogs/accounts.py`
- `rsassistant/bot/cogs/holdings.py`
- relevant cog tests

## Changes

Add env key:

```
DISCORD_OPERATOR_USER_IDS=
```

Parse comma-separated integer IDs into `frozenset[int]`.

Create `operator_only()` in `rsassistant/bot/checks.py`:

```python
def operator_only():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return ctx.author.id in DISCORD_OPERATOR_USER_IDS
    return commands.check(predicate)
```

Apply `@operator_only()` to mutating/executing commands, at minimum:

- `restart`, `shutdown`, `patchautorsa`
- `order`, `liquidate`, `remove`
- queue execution/reschedule commands if present
- account-mapping mutation commands
- destructive/reset holdings commands

Do not gate harmless read-only status/list commands unless already restricted.

While editing `admin.py`, fix `batchclear`:
- reject `limit <= 0`
- reject `limit > 10000` and return
- report `messages_deleted`, not the decremented `limit`

Use existing command error handling for failed checks.

## Tests

- configured operator succeeds
- bot owner succeeds
- ordinary user fails the check and protected callback does not run
- read-only command remains available
