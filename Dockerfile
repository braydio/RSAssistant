FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies

COPY . /app/.

RUN pip install --no-cache-dir -r requirements.txt

# Start the application directly using CMD
CMD ["python", "RSAssistant.py"]
