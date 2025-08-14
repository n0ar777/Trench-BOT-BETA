
FROM python:3.11-slim

# Create non-root user
RUN useradd -ms /bin/bash appuser

WORKDIR /app

# System deps (curl/ca-certificates for TLS, gcc optional if wheels missing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the app
COPY . /app

# Ensure data path exists (mounted at runtime)
RUN mkdir -p /data && chown -R appuser:appuser /data /app

USER appuser

ENV PYTHONUNBUFFERED=1
# TRACKER_STORE can be set in fly.toml or secrets; default to mounted path
ENV TRACKER_STORE="/data/tracker_state.json"

# Start
CMD ["bash", "start.sh"]
