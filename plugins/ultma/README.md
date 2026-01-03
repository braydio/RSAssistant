# ULT-MA Trading Plugin

This plugin provides the ULT-MA automated trading strategy for RSAssistant.
It is optional: RSAssistant runs normally without it.

## Install

When this plugin lives in its own repository, place it on the Python path so it
can be imported as `plugins.ultma`. In this monorepo, it already resides at
`plugins/ultma/`.

## Configure

1. Copy the example config:

```bash
cp plugins/ultma/config/example.env plugins/ultma/config/.env
```

2. Update values in `plugins/ultma/config/.env` (or set `ULTMA_ENV_FILE` to a
   custom path).

## Enable in RSAssistant

Enable plugins from the RSAssistant config so the core bot controls what loads.
Set `ENABLED_PLUGINS` in `config/.env` (or your environment):

```bash
ENABLED_PLUGINS=ultma
```

If the plugin directory is missing, RSAssistant continues to run without ULT-MA.
