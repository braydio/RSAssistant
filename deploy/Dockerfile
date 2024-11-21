# Dockerfile for RSAssistant

# Use a lightweight Python base image
FROM python:3.10-slim

# Set working directory in the container
WORKDIR /app

# Install bash (since python:3.10-slim doesn't come with bash by default)
RUN apt-get update && apt-get install -y bash

# Copy requirements file and install dependencies
COPY deploy/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY src /app/src
COPY config /app/config
COPY logs /app/logs

# Ensure logs directory is writable
RUN mkdir -p /app/logs && chmod -R 777 /app/logs

# Set environment variables
ENV ENVIRONMENT=production

# Entrypoint script
ENTRYPOINT ["sh", "deploy/entrypoint.sh"]