"""Production Gunicorn configuration for Phone Book Management System (T107, NFR-004)."""

import os

# Network binding (defaults to loopback behind Nginx reverse proxy)
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")

# Worker configuration: 4 gthread workers * 16 threads = 64 concurrent threads
worker_class = "gthread"
workers = 4
threads = 16

# Timeouts & keep-alive
timeout = 30
graceful_timeout = 30
keepalive = 5

# Worker recycling to mitigate memory growth over long uptimes
max_requests = 1000
max_requests_jitter = 100

# Structured logging to stdout/stderr for container & systemd journal capture
accesslog = "-"
errorlog = "-"
loglevel = "info"
