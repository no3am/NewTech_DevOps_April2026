FROM python:3.11-slim

WORKDIR /app

# Copy requirements FIRST to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY client.py .

# Create a non-root user
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

# These can be overridden at runtime with: docker run -e SERVER_URL=...
ENV SERVER_URL=http://localhost:5000
ENV NUM_READINGS=5

CMD ["python3", "client.py"]
