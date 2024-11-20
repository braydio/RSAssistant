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

# Copy necessary directories and files into the container
COPY ./deploy /app/deploy
COPY ./src ./src
COPY .gitignore /app/.gitignore
COPY ./config /app/config
COPY LICENSE /app/LICENSE
COPY README.md /app/README.md

# Ensure logs directory is writable
RUN mkdir -p /app/volumes/logs && chmod -R 777 /app/volumes/logs

# Set environment variables
ENV ENVIRONMENT=production

# Entrypoint script using bash
ENTRYPOINT ["bash", "deploy/entrypoint.sh"]
