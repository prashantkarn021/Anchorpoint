# Build context is the repo root (see docker-compose.yml), so imports resolve as backend.app...
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY contract ./contract
# The seed generators (and /demo/inject) read the persona specs.
COPY scripts/personas ./scripts/personas

RUN mkdir -p /data
EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
