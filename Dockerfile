# Build from python slim image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only necessary files to the container (excluding /logs)
COPY . /app
RUN mkdir -p /app/logs

# Install any required Python packages
RUN pip install -r requirements.txt

# Run your main script
CMD ["python", "RSAssistant.py"]
