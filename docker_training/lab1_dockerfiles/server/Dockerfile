FROM python:3.11-slim

WORKDIR /app

# Copy requirements FIRST to leverage Docker layer caching.
# This layer is only rebuilt when requirements.txt changes —
# not every time you change server.py.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (changes more frequently than dependencies)
COPY server.py .

# Create a non-root user and give ownership of the working directory
# Without chown, appuser can read files but cannot write data.json to /app
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app \
    && mkdir /data && chown appuser:appuser /data
USER appuser

EXPOSE 5000

# HEALTHCHECK tells Docker how to verify the container is working.
# In Kubernetes, this concept becomes liveness/readiness probes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["python3", "server.py"]
