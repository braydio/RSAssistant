# ULT-MA Trading Plugin

This plugin provides the ULT-MA automated trading strategy for RSAssistant.
It is optional: RSAssistant runs normally without it.

## Install

When this plugin lives in its own repository, place it on the Python path so it
can be imported as `plugins.ultma`. In this monorepo, it already resides at
`plugins/ultma/`.

## Configure

Store ULT-MA variables in RSAssistant's `config/.env` (or your `ENV_FILE`
target). ULT-MA reads from the process environment only, so operator workflows
should keep a single source of truth in RSAssistant's centralized env loading.

## Enable in RSAssistant

Enable plugins from the RSAssistant config so the core bot controls what loads.
Set `ENABLED_PLUGINS` in `config/.env` (or your `ENV_FILE` target):

```bash
ENABLED_PLUGINS=ultma
```

If the plugin directory is missing, RSAssistant continues to run without ULT-MA.

## Discord Commands

When the plugin is enabled in RSAssistant the `..ultma` command group becomes
available. Use it to inspect status and control the trading bot:

- `..ultma status`: Show the latest indicator colors, pending trade, and whether
  the bot is paused.
- `..ultma start` / `..ultma stop`: Start or stop the monitoring tasks manually.
- `..ultma pause` / `..ultma resume`: Temporarily pause trading without
  stopping the scheduler.
- `..ultma force <long|short>`: Force an entry in the provided direction.
