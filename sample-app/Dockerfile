FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies in a separate layer for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY wsgi.py .
COPY gunicorn.conf.py .

# Prometheus multiprocess mode: workers write metric files here so /metrics
# aggregates across all gunicorn workers instead of reporting per-worker values.
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# Non-root user for security
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    mkdir -p /tmp/prometheus_multiproc && \
    chown appuser:appgroup /tmp/prometheus_multiproc
USER appuser

EXPOSE 5000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "wsgi:app"]
