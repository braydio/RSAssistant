FROM python:3.10-slim

WORKDIR /app

# Install system and Python dependencies
COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y \
        build-essential \
        libxml2-dev \
        libxslt-dev \
        libssl-dev \
        cmake \
        curl \
        netcat \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get remove -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/
RUN chmod +x /app/entrypoint.sh

# Launch RSAssistant via the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
