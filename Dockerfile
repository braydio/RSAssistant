# use a lightweight python base image
FROM python:3.10-slim

# set working directory in the container
WORKDIR /app

# install bash (since python:3.10-slim doesn't come with bash by default)
RUN apt-get update && apt-get install -y bash

# COPY requirements file and install dependencies
COPY ./requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt
COPY ./src/ /app/src/
COPY ./entrypoint.sh /app/entrypoint.sh

# COPY application files
# do not COPY volumes, as they will be mounted by docker-compose
# ensure logs directory is writable
RUN mkdir -p /app/volumes && chmod -R 777 /app/volumes

# set environment variables
ENV environment=production

# entrypoint script
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
