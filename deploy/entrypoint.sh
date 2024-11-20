#!/bin/bash

# Exit immediately if a command fails
set -e

# Initialize environment
echo "Initializing RSAssistant environment..."
export DISPLAY=:99  # Optional, if graphical dependencies are used

# Check for required directories in volumes
if [ ! -d "/app/src/volumes/logs" ]; then
    echo "Creating logs directory..."
    mkdir -p /app/src/volumes/logs
fi

if [ ! -d "/app/src/volumes/excel" ]; then
    echo "Creating excel directory..."
    mkdir -p /app/src/volumes/excel
fi

# Start the main script
echo "Starting RSAssistant script..."
exec python /app/RSAssistant.py
