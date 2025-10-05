FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY server.py .

# Set environment
ENV PYTHONUNBUFFERED=1

# Run server
CMD ["python", "server.py"]
