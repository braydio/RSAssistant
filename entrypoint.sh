#!/bin/sh

# Entrypoint for the RSAssistant container.
# Sets up persistent directories, waits for dependencies, and starts the bot.
set -e

echo "Initializing RSAssistant environment..."

# Optionally set the DISPLAY environment variable in development mode
export DISPLAY=:99

# Check for required directories in volumes and create them if they don't exist
REQUIRED_DIRECTORIES="/app/volumes/logs /app/volumes/excel /app/volumes/db /app/volumes/config"

for DIR in $REQUIRED_DIRECTORIES; do
  if [ ! -d "$DIR" ]; then
    echo "Creating directory: $DIR"
    mkdir -p "$DIR"
  fi
done

# Set permissions to ensure the container user has appropriate access
chmod -R 755 /app/volumes

# Set ownership (if running as a non-root user)
# chown -R appuser:appuser /app/volumes

# Initialize log files (if necessary)
LOG_FILE="/app/volumes/logs/rsassistant.log"
if [ ! -f "$LOG_FILE" ]; then
  echo "Initializing log file: $LOG_FILE"
  touch "$LOG_FILE"
fi

# Start the main script
echo "Starting RSAssistant script..."
exec python /app/RSAssistant.py
