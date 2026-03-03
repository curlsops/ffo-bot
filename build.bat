@echo off
REM Build and test script for Windows

echo 🤖 FFO Discord Bot - Build and Test
echo ====================================

REM Check Python version
echo Checking Python version...
python --version
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.11+
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo ✓ Virtual environment created
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
echo ✓ Dependencies installed

REM Run linters
echo.
echo Running linters...
echo - flake8
flake8 bot/ config/ database/ main.py --count --statistics

echo - black
black --check bot/ config/ database/ main.py

echo - isort
isort --check-only bot/ config/ database/ main.py

echo ✓ All linters passed

REM Run tests
echo.
echo Running tests...
pytest tests/ -v --cov=bot --cov=config --cov=database --cov-report=term --cov-report=html

echo.
echo ✓ All tests passed

REM Build Docker image
echo.
echo Building Docker image...
docker build -t ffobot:test .
echo ✓ Docker image built successfully

REM Smoke test - verify container can import all modules
echo.
echo Running container smoke test...
docker run --rm --entrypoint python ffobot:test smoke_test.py
echo ✓ Container smoke test passed

echo.
echo 🎉 Build and test completed successfully!
echo.
echo Next steps:
echo   1. Copy .env.example to .env and configure
echo   2. Start PostgreSQL: docker-compose up -d postgres
echo   3. Run migrations: alembic upgrade head
echo   4. Start bot: python main.py

