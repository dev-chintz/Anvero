# The API for the NAS (docs/DEPLOYMENT.md). The same Python line as CI.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# requirements.txt also lists the test and lint tools; one file keeps the
# versions the tests ran against identical to what runs here
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini pyproject.toml ./
COPY app app
COPY migrations migrations
COPY scripts scripts

RUN useradd --system --uid 1000 anvero
USER anvero

EXPOSE 8000

# Migrates first, so a new image never runs ahead of its schema. Behind the
# web container's proxy, so the client address (used by the rate limits) is
# read from X-Forwarded-For, and only that container can reach this port.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
