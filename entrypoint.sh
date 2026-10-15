#!/bin/sh

# Entrypoint for the RSAssistant container.
# Sets up persistent directories, waits for dependencies, and starts the bot.
set -e

echo "Initializing RSAssistant environment..."

# DISPLAY is intentionally not set: the bot is headless. For GUI/browser tooling,
# pass DISPLAY through the compose ``environment:`` block instead.

# Determine the volumes directory (default /app/volumes)
VOLUMES_DIR="${VOLUMES_DIR:-/app/volumes}"

# Check for required directories in volumes and create them if they don't exist
REQUIRED_DIRECTORIES="$VOLUMES_DIR/logs $VOLUMES_DIR/db $VOLUMES_DIR/cache"

for DIR in $REQUIRED_DIRECTORIES; do
  if [ ! -d "$DIR" ]; then
    echo "Creating directory: $DIR"
    mkdir -p "$DIR"
    # Only newly created directories get a mode; existing data trees are never
    # walked or re-permissioned. To repair permissions deliberately, run:
    #   docker compose run --rm --entrypoint chmod rsassistant -R u+rwX /app/volumes
    chmod 755 "$DIR"
  fi
done

# Set ownership (if running as a non-root user)
# chown -R appuser:appuser /app/volumes

# Initialize log files (if necessary)
LOG_FILE="$VOLUMES_DIR/logs/rsassistant.log"
if [ ! -f "$LOG_FILE" ]; then
  echo "Initializing log file: $LOG_FILE"
  touch "$LOG_FILE"
fi

# Start the main script
echo "Starting RSAssistant script..."
exec python /app/RSAssistant.py
