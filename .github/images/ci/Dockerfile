FROM python:3.14-alpine3.22

RUN apk add --no-cache \
    bash \
    git \
    build-base \
    postgresql-dev \
    libffi-dev \
    curl \
    gcompat \
    nodejs \
    npm

WORKDIR /deps

COPY requirements.txt requirements-dev.txt ./

RUN pip install --no-cache-dir -r requirements-dev.txt

WORKDIR /app
