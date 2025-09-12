# Custom Overrides for autoRSA

This directory provides patches for the [NelsonDane/autoRSA](https://github.com/NelsonDane/autoRSA) project. Use these files to override the upstream repository when building a container.

## Usage

1. Clone the autoRSA repository and copy this `custom-overrides` directory into its root.
2. Replace the default entrypoint and compose file with the provided overrides:

   ```bash
   cp custom-overrides/override-entrypoint.sh entrypoint.sh
   cp custom-overrides/override-compose-file.yml docker-compose.yml
   ```

3. Build and start the container:

   ```bash
   docker compose up --build
   ```

The override entrypoint copies `autoRSA.py` and `fennelAPI.py` into `/app/` before the bot starts. Watch the upstream autoRSA repository for changes to ensure your overrides stay compatible.

## Contents

- `autoRSA.py` – patched main automation script.
- `fennelAPI.py` – patched Fennel brokerage integration.
- `override-entrypoint.sh` – entrypoint script that installs overrides.
- `override-compose-file.yml` – Docker Compose file referencing override files.
