FROM python:3.12.16-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project --no-dev



FROM python:3.12.16-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libpq5 \
    tini \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY . .

RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["tini", "--"]
CMD ["/app/docker-entrypoint.sh"]
