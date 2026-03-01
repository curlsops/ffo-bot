#!/bin/bash
# Build and test script for local development

set -e

echo "🤖 FFO Discord Bot - Build and Test"
echo "===================================="

# Check Python version
echo "Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
echo "✓ Dependencies installed"

# Run linters and formatters
echo ""
if [ "$1" = "--check" ] || [ "$1" = "-c" ]; then
    echo "Running linters (check only, use without --check to auto-format)..."
    echo "- flake8"
    flake8 bot/ config/ database/ main.py --count --statistics
    echo "- black"
    black --check bot/ config/ database/ main.py
    echo "- isort"
    isort --check-only bot/ config/ database/ main.py
    echo "✓ All linters passed"
else
    echo "Formatting code..."
    echo "- isort (fixing imports)"
    isort bot/ config/ database/ main.py
    echo "- black (formatting)"
    black bot/ config/ database/ main.py
    echo "✓ Code formatted"
    echo ""
    echo "Running flake8 check..."
    flake8 bot/ config/ database/ main.py --count --statistics
    echo "✓ Flake8 passed"
fi

# Run tests
echo ""
echo "Running tests..."
pytest tests/ -v --cov=bot --cov=config --cov=database --cov-report=term --cov-report=html

echo ""
echo "✓ All tests passed"

# Build Docker image
echo ""
echo "Building Docker image..."
docker buildx build -t ffobot:test .
echo "✓ Docker image built successfully"

# Smoke test - verify container starts and can import modules
echo ""
echo "Running container smoke test..."
docker run --rm ffobot:test python -c "
import bot
import config
import database
from bot.client import FFOBot
from config.settings import Settings
from bot.commands.giveaway import GiveawayCommands, GiveawayView
from bot.tasks.giveaway_manager import GiveawayManager
from bot.commands.reactbot import ReactBotCommands
from bot.processors.phrase_matcher import PhraseMatcher
from bot.auth.permissions import PermissionChecker
from bot.utils.notifier import AdminNotifier
print('All modules imported successfully')
"
echo "✓ Container smoke test passed"

echo ""
echo "🎉 Build and test completed successfully!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and configure"
echo "  2. Start PostgreSQL: docker-compose up -d postgres"
echo "  3. Run migrations: alembic upgrade head"
echo "  4. Start bot: python main.py"

