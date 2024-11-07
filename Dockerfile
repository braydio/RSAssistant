# Use a lightweight Python image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt /app/requirements.txt

# Install the Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the source code directory and the config file into the container
COPY src/ /app/src/

# Set the command to run your Discord bot script
CMD ["python", "/app/src/RSAssistant.py"]