#!/bin/sh

# Exit if a command fails
set -e

# Initialize environment
echo "Initializing RSAssistant environment..."
export DISPLAY=:99  # Optional, if graphical dependencies are used

# Check for required directories in volumes
if [ ! -d "/app/volumes/logs" ]; then
    echo "Creating logs directory..."
    mkdir -p /app/volumes/logs
fi

if [ ! -d "/app/volumes/excel" ]; then
    echo "Creating excel directory..."
    mkdir -p /app/volumes/excel
fi

# Start the main script
echo "Starting RSAssistant script..."
exec python /app/src/RSAssistant.py
