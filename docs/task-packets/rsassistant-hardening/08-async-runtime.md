# Packet 08: Async Runtime Cleanup

Commit: `refactor: keep blocking work off discord event loop`

## Files

- `rsassistant/bot/tasks.py`
- `rsassistant/bot/handlers/on_message.py`
- `utils/policy_resolver.py` only as required by the call boundary
- `utils/openai_utils.py` for logging reduction
- directly affected async tests
- `requirements.txt` only if required

## Scheduler

Replace:

```python
from apscheduler.schedulers.background import BackgroundScheduler
```

with `AsyncIOScheduler`.

Instantiate with `MARKET_TZ`. Remove background-thread lambdas whose only purpose is `bot.loop.create_task(...)`; schedule async callbacks in the asyncio scheduler.

Preserve reminder times and behavior.

Replace the current profanity/debug logs around primary-channel resolution with one useful DEBUG-level line.

## Blocking policy analysis

Find the async Discord call path that directly runs synchronous `SplitPolicyResolver.full_analysis()` / equivalent network-heavy analysis. Move the blocking call boundary into:

```python
await asyncio.to_thread(...)
```

Do not rewrite the resolver to aiohttp in this packet.

## OpenAI logging

Do not INFO-log complete notice text, `system_prompt`, `user_prompt`, or raw prompt payloads.

Retain operational metadata only:
- call_id
- model
- text length
- source URL
- ticker
- duration
- result/failure status

## Tests

- scheduler jobs still register and fire through asyncio
- no BackgroundScheduler/thread bridge remains
- policy analysis runs through `asyncio.to_thread`
- prompt/notice body is absent from INFO logs
