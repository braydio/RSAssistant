# Base image
FROM python:3.12-slim

# Set environment variables
ENV TZ=America/New_York
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies and Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    dos2unix \
    git \
    tzdata && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Install Python dependencies (bind-mounted requirements.txt)
RUN pip install --no-cache-dir -r requirements.txt

# Make the entrypoint script executable
RUN dos2unix entrypoint.sh && chmod +x entrypoint.sh

# Set entrypoint
ENTRYPOINT ["./entrypoint.sh"]
