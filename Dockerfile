FROM python:3.14-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir --no-warn-script-location -r requirements.txt

FROM python:3.14-slim-bookworm

ARG FFO_BOT_VERSION=unknown
ARG IMAGE_SOURCE="https://github.com/MrCurlsTTV/ffo-bot"
ENV FFO_BOT_VERSION=$FFO_BOT_VERSION

LABEL org.opencontainers.image.source="${IMAGE_SOURCE}"
LABEL org.opencontainers.image.description="FFO Discord Bot"
LABEL org.opencontainers.image.licenses="CC-BY-NC-SA-4.0"

# UID/GID 1000 must match Kubernetes securityContext (runAsUser/fsGroup) or site-packages are unreadable.
RUN groupadd -g 1000 discord && \
    useradd -u 1000 -g discord -m -d /home/discord discord && \
    mkdir -p /app /tmp/bot && \
    chown -R discord:discord /app /tmp/bot

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=discord:discord /root/.local /home/discord/.local

COPY --chown=discord:discord bot/ ./bot/
COPY --chown=discord:discord database/ ./database/
COPY --chown=discord:discord config/ ./config/
COPY --chown=discord:discord main.py .
COPY --chown=discord:discord scripts/entrypoint.sh scripts/smoke_test.py .
COPY --chown=discord:discord alembic.ini .
RUN chmod +x entrypoint.sh

USER discord

ENV PATH=/home/discord/.local/bin:$PATH

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080 8443

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
