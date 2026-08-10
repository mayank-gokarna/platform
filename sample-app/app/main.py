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

# Catalog of clickable UI items. Defined at module scope so it can be reused
# both to render the page and to validate click events (bounding metric label
# cardinality to known values).
CATALOG = {
    "Food": [
        {"name": "Pizza", "emoji": "\U0001F35F", "color": "#dc2621"},
        {"name": "Sushi", "emoji": "\U0001F363", "color": "#0891b2"},
        {"name": "Burger", "emoji": "\U0001F354", "color": "#d97706"},
        {"name": "Pasta", "emoji": "\U0001F35D", "color": "#ca8a04"},
        {"name": "Tacos", "emoji": "\U0001F32E", "color": "#16a34a"},
        {"name": "Ice Cream", "emoji": "\U0001F366", "color": "#db2777"},
    ],
    "Movies": [
        {"name": "Action", "emoji": "\U0001F4A5", "color": "#dc2626"},
        {"name": "Comedy", "emoji": "\U0001F602", "color": "#f59e0b"},
        {"name": "Sci-Fi", "emoji": "\U0001F680", "color": "#6366f1"},
        {"name": "Horror", "emoji": "\U0001F47B", "color": "#1e293b"},
        {"name": "Drama", "emoji": "\U0001F3AD", "color": "#7c3aed"},
        {"name": "Animation", "emoji": "\U0001F3AC", "color": "#0ea5e9"},
    ],
    "Clothes": [
        {"name": "Jackets", "emoji": "\U0001F9E5", "color": "#78350f"},
        {"name": "Sneakers", "emoji": "\U0001F45F", "color": "#059669"},
        {"name": "Dresses", "emoji": "\U0001F457", "color": "#e11d48"},
        {"name": "Jeans", "emoji": "\U0001F456", "color": "#1d4ed8"},
        {"name": "T-Shirts", "emoji": "\U0001F455", "color": "#0d9488"},
        {"name": "Suits", "emoji": "\U0001F935", "color": "#334155"},
    ],
    "Cities": [
        {"name": "Tokyo", "emoji": "\U0001F5FC", "color": "#dc2626"},
        {"name": "Paris", "emoji": "\U0001F5FC", "color": "#7c3aed"},
        {"name": "New York", "emoji": "\U0001F5FD", "color": "#059669"},
        {"name": "London", "emoji": "\U0001F3A1", "color": "#1d4ed8"},
        {"name": "Dubai", "emoji": "\U0001F3D9\uFE0F", "color": "#d97706"},
        {"name": "Sydney", "emoji": "\U0001F309", "color": "#0891b2"},
    ],
}

# Set of valid (section, item) pairs for validating click events.
VALID_CLICKS = {(section, item["name"]) for section, items in CATALOG.items() for item in items}


def create_app() -> Flask:
    """Create and configure the Flask application."""
    application = Flask(__name__)

    # Metric handles that routes reference. Initialized to None so the routes
    # stay functional even if prometheus-client is unavailable (except branch).
    PAGE_VIEWS = None
    PAGE_VIEW_TS = None

    # Prometheus metrics instrumentation
    try:
        from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
        REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
        REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency',
                                    ['method', 'endpoint'],
                                    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0])
        REQUESTS_IN_PROGRESS = Gauge('http_requests_in_progress', 'Requests currently being processed', multiprocess_mode='livesum')
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
            # When running under gunicorn with multiple workers, collect from the
            # shared multiprocess directory so metrics aggregate across workers.
            if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
                from prometheus_client import CollectorRegistry, multiprocess
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
                return generate_latest(registry), 200, {'Content-Type': CONTENT_TYPE_LATEST}
            return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

        BUTTON_CLICKS = Counter('ui_button_clicks_total', 'Total UI button/card clicks', ['section', 'item'])

        # Page views from real browsers hitting a rendered HTML page, kept
        # separate from http_requests_total so probe/scrape traffic doesn't
        # inflate the count. Label cardinality is bounded to known pages.
        PAGE_VIEWS = Counter('sample_app_page_views_total', 'Catalog page views from the browser', ['page'])

        # Unix time (seconds) of the most recent browser page view, so a
        # dashboard can show WHEN the endpoint was last hit. 'max' aggregation
        # reports the latest hit time across all gunicorn workers.
        PAGE_VIEW_TS = Gauge('sample_app_last_page_view_timestamp_seconds', 'Unix time of the most recent catalog page view', multiprocess_mode='max')

        # Items added to the cart, per catalog item. Label cardinality is bounded
        # to known (section, item) pairs.
        CART_ITEMS = Counter('sample_app_cart_items_added_total', 'Items added to the cart', ['section', 'item'])

        # Items removed from the cart. Current cart size is derived as
        # added - removed, which aggregates correctly across pods/workers
        # (an in-memory gauge would split-brain across replicas).
        CART_REMOVED = Counter('sample_app_cart_items_removed_total', 'Items removed from the cart', ['section', 'item'])

        @application.route("/api/click", methods=["POST"])
        def track_click():
            """Record a UI click as a Prometheus metric.

            Only known (section, item) pairs are counted to keep label
            cardinality bounded and prevent metric-label injection.
            """
            data = request.get_json(silent=True) or {}
            section = str(data.get("section", ""))
            item = str(data.get("item", ""))
            if (section, item) not in VALID_CLICKS:
                return jsonify({"error": "unknown item"}), 400
            BUTTON_CLICKS.labels(section, item).inc()
            return "", 204

        @application.route("/api/cart/add", methods=["POST"])
        def add_to_cart():
            """Record an add-to-cart event as a Prometheus metric.

            Only known (section, item) pairs are counted to keep label
            cardinality bounded and prevent metric-label injection.
            """
            data = request.get_json(silent=True) or {}
            section = str(data.get("section", ""))
            item = str(data.get("item", ""))
            if (section, item) not in VALID_CLICKS:
                return jsonify({"error": "unknown item"}), 400
            CART_ITEMS.labels(section, item).inc()
            return jsonify({"status": "added", "section": section, "item": item}), 200

        @application.route("/api/cart/remove", methods=["POST"])
        def remove_from_cart():
            """Record a remove-from-cart event; decrements current cart size."""
            data = request.get_json(silent=True) or {}
            section = str(data.get("section", ""))
            item = str(data.get("item", ""))
            if (section, item) not in VALID_CLICKS:
                return jsonify({"error": "unknown item"}), 400
            CART_REMOVED.labels(section, item).inc()
            return jsonify({"status": "removed", "section": section, "item": item}), 200
    except ImportError:
        logger.warning("prometheus-client not installed, /metrics disabled")

        @application.route("/api/click", methods=["POST"])
        def track_click():
            return "", 204

        @application.route("/api/cart/add", methods=["POST"])
        def add_to_cart():
            return "", 204

        @application.route("/api/cart/remove", methods=["POST"])
        def remove_from_cart():
            return "", 204

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
        if PAGE_VIEWS is not None:
            PAGE_VIEWS.labels("catalog").inc()
            PAGE_VIEW_TS.set(time.time())
        hostname = os.environ.get("HOSTNAME", platform.node())

        catalog = CATALOG

        sections_html = ""
        for section, items in catalog.items():
            cards_html = ""
            for item in items:
                cards_html += f'''
              <div class="catalog-card" data-section="{section}" data-item="{item['name']}">
                <div class="catalog-card-img" style="background:{item['color']}">{item['emoji']}</div>
                <div class="catalog-card-name">{item['name']}</div>
                <button class="add-cart-btn" data-section="{section}" data-item="{item['name']}">&#128722; Add to Cart</button>
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
    .catalog-card-img {{ width: 100%; height: 140px; display: flex; align-items: center; justify-content: center; font-size: 3.5rem; }}
    .catalog-card-name {{ padding: 0.7rem; font-size: 0.9rem; font-weight: 500; text-align: center; color: #cbd5e1; }}
    .footer {{ text-align: center; padding: 2rem; color: #475569; font-size: 0.8rem; border-top: 1px solid #1e293b; }}
    .footer a {{ color: #3b82f6; text-decoration: none; }}
    .header-top {{ display: flex; justify-content: space-between; align-items: center; }}
    .cart-badge {{ background: #3b82f6; color: #fff; padding: 0.45rem 1rem; border-radius: 20px; font-weight: 600; font-size: 0.9rem; white-space: nowrap; }}
    .cart-remove-btn {{ background: rgba(255,255,255,0.25); color: #fff; border: none; border-radius: 50%; width: 1.35rem; height: 1.35rem; font-size: 1.1rem; line-height: 1; cursor: pointer; margin-left: 0.4rem; vertical-align: middle; }}
    .cart-remove-btn:hover {{ background: rgba(255,255,255,0.45); }}
    .add-cart-btn {{ width: 100%; border: none; background: #3b82f6; color: #fff; padding: 0.55rem; font-size: 0.8rem; font-weight: 600; cursor: pointer; border-top: 1px solid #334155; transition: background 0.2s; }}
    .add-cart-btn:hover {{ background: #2563eb; }}
    .toast {{ position: fixed; bottom: 1.5rem; right: 1.5rem; background: #16a34a; color: #fff; padding: 0.8rem 1.2rem; border-radius: 8px; opacity: 0; transform: translateY(10px); transition: opacity 0.3s, transform 0.3s; z-index: 200; pointer-events: none; }}
    .toast.show {{ opacity: 1; transform: translateY(0); }}
  </style>
</head>
<body>
  <div class="header">
    <div class="header-top">
      <div><h1>&#128722; Platform Catalog</h1><span class="version">v{__version__}</span></div>
      <div class="cart-badge">&#128722; Cart: <span id="cart-count">0</span> <button id="cart-remove" class="cart-remove-btn" title="Remove last item from cart">&minus;</button></div>
    </div>
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
  <div id="toast" class="toast"></div>
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
    }});    document.querySelectorAll('.catalog-card').forEach(card => {{
        card.addEventListener('click', () => {{
        fetch('/api/click', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ section: card.dataset.section, item: card.dataset.item }})
        }});
        }});
    }});
    const cart = [];
    const toast = document.getElementById('toast');
    const cartCountEl = document.getElementById('cart-count');
    function renderCart() {{ cartCountEl.textContent = cart.length; }}
    function showToast(msg) {{
      toast.textContent = msg;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 1600);
    }}
    document.querySelectorAll('.add-cart-btn').forEach(btn => {{
      btn.addEventListener('click', e => {{
        e.stopPropagation();
        const entry = {{ section: btn.dataset.section, item: btn.dataset.item }};
        fetch('/api/cart/add', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(entry)
        }}).then(r => {{
          if (r.ok) {{
            cart.push(entry);
            renderCart();
            showToast(entry.item + ' added to cart');
          }}
        }});
      }});
    }});
    document.getElementById('cart-remove').addEventListener('click', () => {{
      const entry = cart.pop();
      if (!entry) {{ showToast('Cart is empty'); return; }}
      fetch('/api/cart/remove', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(entry)
      }}).then(r => {{
        if (r.ok) {{ renderCart(); showToast(entry.item + ' removed from cart'); }}
        else {{ cart.push(entry); }}
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
