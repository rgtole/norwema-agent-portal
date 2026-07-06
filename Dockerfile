# Use official lightweight Python image
FROM python:3.12-slim

# Set working directory in the container
WORKDIR /app

# Install basic system build dependencies (only essential and curl)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file to the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into the container
COPY . .

# Expose port (Cloud Run overrides this, but useful for reference)
EXPOSE 8080

# Start Uvicorn listening on the port provided by Cloud Run (defaults to 8080)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]

