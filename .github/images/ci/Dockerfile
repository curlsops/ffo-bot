FROM python:3.14-alpine3.22

RUN apk add --no-cache \
    bash \
    git \
    build-base \
    postgresql-dev \
    libffi-dev \
    curl \
    gcompat \
    libstdc++ \
    nodejs \
    npm

WORKDIR /deps

COPY requirements.txt requirements-dev.txt scripts/patch_tls_client_alpine.py ./

RUN pip install --no-cache-dir -r requirements-dev.txt && \
    python patch_tls_client_alpine.py /usr/local/lib/python3.14/site-packages

WORKDIR /app
