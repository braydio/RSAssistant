# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12

# ---- builder: resolve and install dependencies into an isolated prefix ----
FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime: slim image with only the installed packages and the app ----
FROM python:${PYTHON_VERSION}-slim
WORKDIR /app

# git is required at runtime for utils/update_utils.py (self-update).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . /app/
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
