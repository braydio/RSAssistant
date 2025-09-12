#!/bin/bash

# Remove any Xvfb lock if it exists
rm -f /tmp/.X99-lock

# Check if override exists and copy it to replace autoRSA.py
if [ -f "/app/custom-overrides/autoRSA.py" ]; then
    echo "Found override for autoRSA.py. Copying..."
    cp /app/custom-overrides/autoRSA.py /app/autoRSA.py
else
    echo "No override for autoRSA.py found."
fi

# Check if override exists and copy it to replace fennelAPI
if [ -f "/app/custom-overrides/fennelAPI" ]; then
    echo "Found override for fennelAPI. Copying..."
    cp /app/custom-overrides/fennelAPI /app/fennelAPI
else
    echo "No override for fennelAPI found."
fi

# Start X virtual framebuffer in the background
echo "Starting X virtual framebuffer (Xvfb) in background..."
Xvfb -ac :99 -screen 0 1280x1024x16 &

# Set the DISPLAY environment variable
export DISPLAY=:99

# Start the Auto RSA bot
echo "Starting Auto RSA Bot..."
python autoRSA.py docker
