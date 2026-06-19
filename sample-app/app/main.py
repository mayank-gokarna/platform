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
        """Catalog landing page with sections."""
        hostname = os.environ.get("HOSTNAME", platform.node())

        catalog = {
            "Food": [
                {"name": "Pizza", "img": "https://loremflickr.com/300/200/pizza,food"},
                {"name": "Sushi", "img": "https://loremflickr.com/300/200/sushi,japanese"},
                {"name": "Burger", "img": "https://loremflickr.com/300/200/burger,grill"},
                {"name": "Pasta", "img": "https://loremflickr.com/300/200/pasta,italian"},
                {"name": "Tacos", "img": "https://loremflickr.com/300/200/tacos,mexican"},
                {"name": "Ice Cream", "img": "https://loremflickr.com/300/200/icecream,dessert"},
            ],
            "Movies": [
                {"name": "Action", "img": "https://loremflickr.com/300/200/action,movie"},
                {"name": "Comedy", "img": "https://loremflickr.com/300/200/comedy,film"},
                {"name": "Sci-Fi", "img": "https://loremflickr.com/300/200/scifi,space"},
                {"name": "Horror", "img": "https://loremflickr.com/300/200/horror,dark"},
                {"name": "Drama", "img": "https://loremflickr.com/300/200/drama,theater"},
                {"name": "Animation", "img": "https://loremflickr.com/300/200/animation,cartoon"},
            ],
            "Clothes": [
                {"name": "Jackets", "img": "https://loremflickr.com/300/200/jacket,fashion"},
                {"name": "Sneakers", "img": "https://loremflickr.com/300/200/sneakers,shoes"},
                {"name": "Dresses", "img": "https://loremflickr.com/300/200/dress,fashion"},
                {"name": "Jeans", "img": "https://loremflickr.com/300/200/jeans,denim"},
                {"name": "T-Shirts", "img": "https://loremflickr.com/300/200/tshirt,casual"},
                {"name": "Suits", "img": "https://loremflickr.com/300/200/suit,formal"},
            ],
            "Cities": [
                {"name": "Tokyo", "img": "https://loremflickr.com/300/200/tokyo,city"},
                {"name": "Paris", "img": "https://loremflickr.com/300/200/paris,eiffel"},
                {"name": "New York", "img": "https://loremflickr.com/300/200/newyork,skyline"},
                {"name": "London", "img": "https://loremflickr.com/300/200/london,bigben"},
                {"name": "Dubai", "img": "https://loremflickr.com/300/200/dubai,skyscraper"},
                {"name": "Sydney", "img": "https://loremflickr.com/300/200/sydney,opera"},
            ],
        }

        sections_html = ""
        for section, items in catalog.items():
            cards_html = ""
            for item in items:
                cards_html += f'''
              <div class="catalog-card">
                <img src="{item['img']}" alt="{item['name']}" loading="lazy">
                <div class="catalog-card-name">{item['name']}</div>
              </div>'''
            sections_html += f'''
        <div class="section">
          <h2 class="section-title">{section}</h2>
          <div class="catalog-grid">{cards_html}
          </div>
        </div>'''

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Platform Catalog</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
    .header {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); padding: 1.5rem 2rem; border-bottom: 2px solid #3b82f6; position: sticky; top: 0; z-index: 100; }}
    .header h1 {{ font-size: 1.6rem; font-weight: 700; color: #fff; display: inline; }}
    .header .version {{ color: #3b82f6; font-size: 0.85rem; margin-left: 0.8rem; }}
    .nav {{ display: flex; gap: 1rem; margin-top: 0.8rem; flex-wrap: wrap; }}
    .nav a {{ color: #94a3b8; text-decoration: none; font-size: 0.9rem; padding: 0.3rem 0.8rem; border-radius: 6px; transition: all 0.2s; }}
    .nav a:hover, .nav a.active {{ color: #fff; background: #334155; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
    .section {{ margin-bottom: 2.5rem; }}
    .section-title {{ font-size: 1.4rem; font-weight: 600; color: #f8fafc; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #334155; }}
    .catalog-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }}
    .catalog-card {{ background: #1e293b; border-radius: 12px; overflow: hidden; border: 1px solid #334155; transition: transform 0.2s, border-color 0.2s; cursor: pointer; }}
    .catalog-card:hover {{ transform: translateY(-4px); border-color: #3b82f6; }}
    .catalog-card img {{ width: 100%; height: 140px; object-fit: cover; display: block; }}
    .catalog-card-name {{ padding: 0.7rem; font-size: 0.9rem; font-weight: 500; text-align: center; color: #cbd5e1; }}
    .footer {{ text-align: center; padding: 2rem; color: #475569; font-size: 0.8rem; border-top: 1px solid #1e293b; }}
    .footer a {{ color: #3b82f6; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>&#128722; Platform Catalog</h1><span class="version">v{__version__}</span>
    <div class="nav">
      <a href="#food" class="active">Food</a>
      <a href="#movies">Movies</a>
      <a href="#clothes">Clothes</a>
      <a href="#cities">Cities</a>
      <a href="/health">Health</a>
      <a href="/metrics">Metrics</a>
    </div>
  </div>
  <div class="container">
    {sections_html}
  </div>
  <div class="footer">
    <p>Deployed via Jenkins &bull; Managed by ArgoCD &bull; Pod: {hostname}</p>
    <p style="margin-top:0.5rem"><a href="/health">/health</a> &bull; <a href="/info">/info</a> &bull; <a href="/metrics">/metrics</a></p>
  </div>
  <script>
    document.querySelectorAll('.nav a[href^="#"]').forEach(link => {{
      link.addEventListener('click', e => {{
        e.preventDefault();
        const id = link.getAttribute('href').substring(1);
        const section = document.querySelectorAll('.section')[['food','movies','clothes','cities'].indexOf(id)];
        if (section) section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
        link.classList.add('active');
      }});
    }});
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
