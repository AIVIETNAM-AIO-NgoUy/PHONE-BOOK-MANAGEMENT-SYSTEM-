FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/sh --create-home appuser \
    && mkdir -p /app/backend/staticfiles /app/backend/media /app/staticfiles /app/media \
    && chown -R appuser:appuser /app/backend/staticfiles /app/backend/media /app/staticfiles /app/media \
    && chmod +x /app/deploy/docker-entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
