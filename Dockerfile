# Production Dockerfile for CROUS Discord Room Availability Monitor
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables for clean container output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY pytest.ini .
COPY tests/ ./tests/

# Create persistent data and screenshot directories
RUN mkdir -p /app/data /app/debug/screenshots

# Volume for SQLite database persistence
VOLUME ["/app/data"]

# Default command starts continuous monitoring
CMD ["python", "-m", "src.main"]
