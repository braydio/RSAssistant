# Dockerfile for RSAssistant

# Python base image
FROM python:3.10-slim

# Working directory in the container
WORKDIR /app

# Requirements and dependencies
COPY deploy/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# MISC directories and files into the container
COPY ./deploy /app/deploy
COPY ./src ./src
COPY .gitignore /app/.gitignore
COPY ./config /app/config
COPY LICENSE /app/LICENSE
COPY README.md /app/README.md

# Logs directory is writable
RUN mkdir -p /app/volumes/logs && chmod -R 777 /app/volumes/logs

# Set environment variables
ENV ENVIRONMENT=production

# Entrypoint script
ENTRYPOINT ["sh", "deploy/entrypoint.sh"]
