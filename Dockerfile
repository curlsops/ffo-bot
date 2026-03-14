# Multi-stage build for optimized Discord bot image
# Stage 1: Builder
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir --no-warn-script-location -r requirements.txt

# Stage 2: Runtime
FROM python:3.14-slim

ARG FFO_BOT_VERSION=unknown
ARG IMAGE_SOURCE="https://github.com/MrCurlsTTV/ffo-bot"
ENV FFO_BOT_VERSION=$FFO_BOT_VERSION

LABEL org.opencontainers.image.source="${IMAGE_SOURCE}"
LABEL org.opencontainers.image.description="FFO Discord Bot"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash discord && \
    mkdir -p /app /media /tmp/bot && \
    chown -R discord:discord /app /media /tmp/bot

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder --chown=discord:discord /root/.local /home/discord/.local

# Copy application code
COPY --chown=discord:discord bot/ ./bot/
COPY --chown=discord:discord database/ ./database/
COPY --chown=discord:discord config/ ./config/
COPY --chown=discord:discord main.py .
COPY --chown=discord:discord scripts/entrypoint.sh scripts/smoke_test.py .
COPY --chown=discord:discord alembic.ini .
RUN chmod +x entrypoint.sh

# Switch to non-root user
USER discord

# Add local Python packages to PATH
ENV PATH=/home/discord/.local/bin:$PATH

# Set Python to run in unbuffered mode
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose ports
EXPOSE 8080 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

# Run application with migrations
ENTRYPOINT ["./entrypoint.sh"]
