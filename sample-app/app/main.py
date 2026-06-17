"""Flask application factory with observability instrumentation."""

import os
import platform
import random
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from app import __version__
from app.logging_config import setup_logging

logger = setup_logging()

# Track app start time
APP_START_TIME = time.monotonic()
APP_START_UTC = datetime.now(timezone.utc)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    application = Flask(__name__)

    # Prometheus metrics instrumentation
    try:
        from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
        REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
        REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency',
                                    ['method', 'endpoint'],
                                    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0])
        REQUESTS_IN_PROGRESS = Gauge('http_requests_in_progress', 'Requests currently being processed')
        ERROR_COUNT = Counter('http_errors_total', 'Total HTTP errors', ['method', 'endpoint', 'error_type'])

        @application.before_request
        def _metrics_before():
            REQUESTS_IN_PROGRESS.inc()

        @application.after_request
        def _metrics_after_request(response):
            REQUESTS_IN_PROGRESS.dec()
            REQUEST_COUNT.labels(request.method, request.path, response.status_code).inc()
            duration = time.monotonic() - getattr(request, "_start_time", time.monotonic())
            REQUEST_LATENCY.labels(request.method, request.path).observe(duration)
            if response.status_code >= 400:
                error_type = 'client_error' if response.status_code < 500 else 'server_error'
                ERROR_COUNT.labels(request.method, request.path, error_type).inc()
            return response

        @application.route("/metrics")
        def metrics():
            return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
    except ImportError:
        logger.warning("prometheus-client not installed, /metrics disabled")

    @application.before_request
    def _before_request():
        request._start_time = time.monotonic()
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
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        return response

    # ----- Routes -----

    @application.route("/")
    def index():
        """Dashboard landing page."""
        now = datetime.now(timezone.utc)
        uptime_secs = int(time.monotonic() - APP_START_TIME)
        uptime_str = _format_uptime(uptime_secs)
        hostname = os.environ.get("HOSTNAME", platform.node())

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Platform Sample App</title>
  <style>
    * {{{{ margin: 0; padding: 0; box-sizing: border-box; }}}}
    body {{{{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}}}
    .header {{{{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); padding: 2rem; border-bottom: 2px solid #3b82f6; }}}}
    .header h1 {{{{ font-size: 1.8rem; font-weight: 700; color: #fff; }}}}
    .header p {{{{ color: #94a3b8; margin-top: 0.3rem; }}}}
    .container {{{{ max-width: 1000px; margin: 0 auto; padding: 2rem; }}}}
    .cards {{{{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}}}
    .card {{{{ background: #1e293b; border-radius: 12px; padding: 1.2rem; border: 1px solid #334155; }}}}
    .card .label {{{{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 0.3rem; }}}}
    .card .value {{{{ font-size: 1.4rem; font-weight: 600; color: #f8fafc; }}}}
    .card .value.green {{{{ color: #22c55e; }}}}
    .card .value.blue {{{{ color: #3b82f6; }}}}
    .card .value.amber {{{{ color: #f59e0b; }}}}
    .endpoints {{{{ margin: 2rem 0; }}}}
    .endpoints h2 {{{{ font-size: 1.2rem; margin-bottom: 1rem; color: #cbd5e1; }}}}
    .endpoint-list {{{{ list-style: none; }}}}
    .endpoint-list li {{{{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 0.8rem 1rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.8rem; }}}}
    .method {{{{ background: #22c55e; color: #000; font-size: 0.7rem; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 4px; min-width: 40px; text-align: center; }}}}
    .path {{{{ font-family: 'SF Mono', 'Fira Code', monospace; color: #93c5fd; }}}}
    .desc {{{{ color: #64748b; margin-left: auto; font-size: 0.85rem; }}}}
    .actions {{{{ margin: 2rem 0; }}}}
    .actions h2 {{{{ font-size: 1.2rem; margin-bottom: 1rem; color: #cbd5e1; }}}}
    .btn-row {{{{ display: flex; gap: 0.8rem; flex-wrap: wrap; }}}}
    .btn {{{{ padding: 0.6rem 1.2rem; border-radius: 8px; border: none; font-size: 0.9rem; font-weight: 500; cursor: pointer; text-decoration: none; display: inline-block; }}}}
    .btn-blue {{{{ background: #3b82f6; color: #fff; }}}}
    .btn-green {{{{ background: #22c55e; color: #000; }}}}
    .btn-amber {{{{ background: #f59e0b; color: #000; }}}}
    .btn-red {{{{ background: #ef4444; color: #fff; }}}}
    .btn:hover {{{{ opacity: 0.85; }}}}
    #result {{{{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 1rem; margin-top: 1rem; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; min-height: 60px; color: #a5f3fc; display: none; }}}}
    .footer {{{{ text-align: center; padding: 2rem; color: #475569; font-size: 0.8rem; }}}}
  </style>
</head>
<body>
  <div class="header">
    <div class="container" style="padding:0">
      <h1>&#9881; Platform Sample App</h1>
      <p>Deployed via Jenkins &bull; Managed by ArgoCD &bull; Monitored with Prometheus + Grafana</p>
    </div>
  </div>
  <div class="container">
    <div class="cards">
      <div class="card">
        <div class="label">Status</div>
        <div class="value green">&#9679; Healthy</div>
      </div>
      <div class="card">
        <div class="label">Version</div>
        <div class="value blue">{__version__}</div>
      </div>
      <div class="card">
        <div class="label">Uptime</div>
        <div class="value amber">{uptime_str}</div>
      </div>
      <div class="card">
        <div class="label">Pod</div>
        <div class="value" style="font-size:0.9rem;color:#94a3b8">{hostname}</div>
      </div>
    </div>

    <div class="endpoints">
      <h2>API Endpoints</h2>
      <ul class="endpoint-list">
        <li><span class="method">GET</span><span class="path">/</span><span class="desc">This dashboard</span></li>
        <li><span class="method">GET</span><span class="path">/health</span><span class="desc">Kubernetes health check</span></li>
        <li><span class="method">GET</span><span class="path">/info</span><span class="desc">Runtime &amp; environment info</span></li>
        <li><span class="method">GET</span><span class="path">/metrics</span><span class="desc">Prometheus metrics</span></li>
        <li><span class="method">GET</span><span class="path">/slow?ms=N</span><span class="desc">Simulate slow response</span></li>
        <li><span class="method">GET</span><span class="path">/error?code=N</span><span class="desc">Simulate HTTP error</span></li>
        <li><span class="method">GET</span><span class="path">/load?n=N</span><span class="desc">Generate CPU load</span></li>
      </ul>
    </div>

    <div class="actions">
      <h2>Try It</h2>
      <div class="btn-row">
        <button class="btn btn-green" onclick="callApi('/health')">Health Check</button>
        <button class="btn btn-blue" onclick="callApi('/info')">App Info</button>
        <button class="btn btn-amber" onclick="callApi('/slow?ms=500')">Slow (500ms)</button>
        <button class="btn btn-red" onclick="callApi('/error?code=500')">Error 500</button>
        <button class="btn btn-amber" onclick="callApi('/load?n=100000')">CPU Load</button>
      </div>
      <div id="result"></div>
    </div>
  </div>
  <div class="footer">
    {now.strftime("%Y-%m-%d %H:%M:%S UTC")} &bull; {hostname}
  </div>
  <script>
    async function callApi(path) {{{{
      const el = document.getElementById('result');
      el.style.display = 'block';
      el.textContent = 'Loading...';
      const t0 = performance.now();
      try {{{{
        const res = await fetch(path);
        const dur = (performance.now() - t0).toFixed(1);
        const traceId = res.headers.get('X-Trace-Id') || 'n/a';
        const body = await res.text();
        let parsed;
        try {{{{ parsed = JSON.stringify(JSON.parse(body), null, 2); }}}} catch {{{{ parsed = body; }}}}
        el.textContent = `HTTP ${{{{res.status}}}} | ${{{{dur}}}}ms | trace: ${{{{traceId}}}}\n\n${{{{parsed}}}}`;
        el.style.color = res.ok ? '#a5f3fc' : '#fca5a5';
      }}}} catch (e) {{{{
        el.textContent = 'Error: ' + e.message;
        el.style.color = '#fca5a5';
      }}}}
    }}}}
  </script>
</body>
</html>"""

    @application.route("/health")
    def health():
        """Health check for Kubernetes probes."""
        uptime_secs = int(time.monotonic() - APP_START_TIME)
        return jsonify({
            "status": "ok",
            "version": __version__,
            "uptime_seconds": uptime_secs,
            "hostname": os.environ.get("HOSTNAME", platform.node()),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        })

    @application.route("/info")
    def info():
        """Runtime and environment info for observability."""
        uptime_secs = int(time.monotonic() - APP_START_TIME)
        return jsonify({
            "app": {
                "name": "sample-app",
                "version": __version__,
                "started_at": APP_START_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "uptime_seconds": uptime_secs,
                "uptime_human": _format_uptime(uptime_secs),
            },
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "hostname": os.environ.get("HOSTNAME", platform.node()),
                "pid": os.getpid(),
            },
            "kubernetes": {
                "pod": os.environ.get("HOSTNAME", "unknown"),
                "namespace": os.environ.get("POD_NAMESPACE", "default"),
                "node": os.environ.get("NODE_NAME", "unknown"),
                "service_account": os.environ.get("SERVICE_ACCOUNT", "default"),
            },
        })

    @application.route("/slow")
    def slow():
        """Simulate a slow response for latency testing."""
        delay_ms = min(int(request.args.get("ms", 1000)), 10000)
        time.sleep(delay_ms / 1000.0)
        return jsonify({
            "message": f"Responded after {delay_ms}ms delay",
            "delay_ms": delay_ms,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        })

    @application.route("/error")
    def error_endpoint():
        """Simulate HTTP errors for alerting/dashboard testing."""
        code = int(request.args.get("code", 500))
        code = max(400, min(code, 599))
        messages = {
            400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
            404: "Not Found", 429: "Too Many Requests", 500: "Internal Server Error",
            502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
        }
        return jsonify({
            "error": messages.get(code, "Simulated Error"),
            "code": code,
            "simulated": True,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }), code

    @application.route("/load")
    def load():
        """Generate CPU load for resource monitoring."""
        n = min(int(request.args.get("n", 100000)), 5000000)
        t0 = time.monotonic()
        total = sum(random.random() for _ in range(n))
        elapsed_ms = (time.monotonic() - t0) * 1000
        return jsonify({
            "message": f"Computed {n} random numbers",
            "iterations": n,
            "sum": round(total, 2),
            "elapsed_ms": round(elapsed_ms, 2),
        })

    @application.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Not Found", "code": 404}), 404

    return application


def _format_uptime(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _generate_trace_id() -> str:
    """Generate a random 32-hex-char trace ID."""
    import secrets
    return secrets.token_hex(16)
