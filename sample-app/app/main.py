"""Flask application factory with observability instrumentation."""

import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from app import __version__
from app.logging_config import setup_logging

logger = setup_logging()


def create_app() -> Flask:
    """Create and configure the Flask application."""
    application = Flask(__name__)

    # Prometheus metrics instrumentation
    try:
        from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
        REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
        REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])

        @application.after_request
        def _metrics_after_request(response):
            REQUEST_COUNT.labels(request.method, request.path, response.status_code).inc()
            duration = time.monotonic() - getattr(request, "_start_time", time.monotonic())
            REQUEST_LATENCY.labels(request.method, request.path).observe(duration)
            return response

        @application.route("/metrics")
        def metrics():
            return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
    except ImportError:
        logger.warning("prometheus-client not installed, /metrics disabled")

    @application.before_request
    def _before_request():
        request._start_time = time.monotonic()
        # Parse W3C traceparent header
        traceparent = request.headers.get("traceparent", "")
        if traceparent:
            parts = traceparent.split("-")
            request._trace_id = parts[1] if len(parts) >= 3 else _generate_trace_id()
        else:
            request._trace_id = _generate_trace_id()

    @application.after_request
    def _after_request(response):
        duration_ms = (time.monotonic() - getattr(request, "_start_time", time.monotonic())) * 1000
        trace_id = getattr(request, "_trace_id", "")
        logger.info(
            "Request handled",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "trace_id": trace_id,
            },
        )
        return response

    # ----- Routes -----

    @application.route("/")
    def index():
        """Landing page."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"""<!DOCTYPE html>
<html>
<head><title>Sample App</title></head>
<body>
  <h1>Sample App</h1>
  <p>Version: {__version__}</p>
  <p>Deployed: {now}</p>
  <p>Status: Running</p>
</body>
</html>"""

    @application.route("/health")
    def health():
        """Health check for Kubernetes probes."""
        return jsonify({
            "status": "ok",
            "version": __version__,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        })

    @application.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Not Found"}), 404

    return application


def _generate_trace_id() -> str:
    """Generate a random 32-hex-char trace ID."""
    import secrets
    return secrets.token_hex(16)
