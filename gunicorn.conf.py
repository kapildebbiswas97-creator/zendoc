"""Gunicorn configuration for ZENDOC.

Concurrency is environment-driven so the same application can run on a small
pilot instance or a larger multi-worker deployment without changing code.
"""
import os


def _int(name, default, minimum=1, maximum=256):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = _int("ZENDOC_GUNICORN_WORKERS", 2, 1, 32)
threads = _int("ZENDOC_GUNICORN_THREADS", 4, 1, 32)
worker_class = os.environ.get("ZENDOC_GUNICORN_WORKER_CLASS", "gthread")
timeout = _int("ZENDOC_GUNICORN_TIMEOUT_SECONDS", 60, 15, 300)
graceful_timeout = _int("ZENDOC_GUNICORN_GRACEFUL_TIMEOUT_SECONDS", 30, 5, 120)
keepalive = _int("ZENDOC_GUNICORN_KEEPALIVE_SECONDS", 5, 1, 30)
max_requests = _int("ZENDOC_GUNICORN_MAX_REQUESTS", 1000, 100, 100000)
max_requests_jitter = _int("ZENDOC_GUNICORN_MAX_REQUESTS_JITTER", 100, 0, 10000)
accesslog = "-"
errorlog = "-"
capture_output = True
