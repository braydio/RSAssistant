FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/ /app/src/
COPY ./entrypoint.sh /app/entrypoint.sh

# Start the application directly using CMD
CMD ["python", "src/RSAssistant.py"]
