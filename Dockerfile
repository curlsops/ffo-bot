FROM python:3.14-alpine3.22 AS builder

WORKDIR /build

RUN apk add --no-cache \
    build-base \
    postgresql-dev \
    libffi-dev \
    git

COPY requirements.txt scripts/patch_tls_client_alpine.py ./
RUN pip install --user --no-cache-dir --no-warn-script-location -r requirements.txt && \
    python patch_tls_client_alpine.py /root/.local/lib/python3.14/site-packages

FROM python:3.14-alpine3.22

ARG FFO_BOT_VERSION=unknown
ARG IMAGE_SOURCE="https://github.com/MrCurlsTTV/ffo-bot"
ENV FFO_BOT_VERSION=$FFO_BOT_VERSION

LABEL org.opencontainers.image.source="${IMAGE_SOURCE}"
LABEL org.opencontainers.image.description="FFO Discord Bot"
LABEL org.opencontainers.image.licenses="CC-BY-NC-SA-4.0"

# UID/GID 1000 must match Kubernetes securityContext (runAsUser/fsGroup) or site-packages are unreadable.
RUN addgroup -g 1000 discord && \
    adduser -D -u 1000 -G discord discord && \
    mkdir -p /app /tmp/bot && \
    chown -R discord:discord /app /tmp/bot

WORKDIR /app

# gcompat: SpotAPI/tls_client wheels expect glibc (e.g. libresolv.so.2) on musl Alpine.
RUN apk add --no-cache \
    postgresql-libs \
    ca-certificates \
    gcompat

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
