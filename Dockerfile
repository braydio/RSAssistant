FROM python:3.10-slim

WORKDIR /app

COPY . /app/.

RUN apt-get update && apt-get install -y \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    libssl-dev \
    cmake \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get remove -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*


# Install dependencies



# Start the application directly using CMD
CMD ["python", "RSAssistant.py"]
