#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete"

echo "Starting bot..."
exec python main.py
