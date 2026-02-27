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
if [ "$1" = "--fix" ] || [ "$1" = "-f" ]; then
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
else
    echo "Running linters (use --fix to auto-format)..."
    echo "- flake8"
    flake8 bot/ config/ database/ main.py --count --statistics
    echo "- black"
    black --check bot/ config/ database/ main.py
    echo "- isort"
    isort --check-only bot/ config/ database/ main.py
    echo "✓ All linters passed"
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

echo ""
echo "🎉 Build and test completed successfully!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and configure"
echo "  2. Start PostgreSQL: docker-compose up -d postgres"
echo "  3. Run migrations: alembic upgrade head"
echo "  4. Start bot: python main.py"

