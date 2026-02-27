# FFO Discord Bot

High-availability Discord bot for automated reactions, media archival, and community management.

## Features

- 🤖 **Automated Phrase Reactions**: Configure regex patterns to automatically react to messages
- 📁 **Media Archival**: Download and archive media from monitored channels
- 🔔 **Notifiarr Monitoring**: Monitor Notifiarr notifications and alert on failures
- 👥 **Reaction Roles**: Self-service role assignment via reactions
- 🔐 **Granular Permissions**: Role-based access control with super admin, admin, and moderator tiers
- 📊 **Prometheus Metrics**: Comprehensive observability and monitoring
- 🏥 **Health Checks**: Kubernetes-ready liveness and readiness probes
- 🔄 **High Availability**: Active-active deployment with 99% uptime target

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Discord Bot Token
- Docker (optional)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_ORG/ffobot.git
   cd ffobot
   ```

2. **Create virtual environment**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Discord credentials
   ```

5. **Start PostgreSQL** (using Docker Compose)
   ```bash
   docker-compose up -d postgres
   ```

6. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

7. **Start the bot**
   ```bash
   python main.py
   ```

### Docker Deployment

1. **Build image**
   ```bash
   docker build -t ffobot:latest .
   ```

2. **Run with docker-compose**
   ```bash
   docker-compose up -d
   ```

## Project Structure

```
ffobot/
├── bot/                    # Bot application code
│   ├── auth/              # Authentication and permissions
│   ├── cache/             # In-memory caching
│   ├── commands/          # Slash commands
│   ├── handlers/          # Event handlers
│   ├── processors/        # Message processors
│   └── utils/             # Utilities and helpers
├── config/                # Configuration management
├── database/              # Database layer and migrations
├── tests/                 # Test suite
├── .github/               # GitHub Actions workflows
├── Dockerfile             # Multi-stage Docker build
├── docker-compose.yml     # Local development compose
├── requirements.txt       # Python dependencies
├── requirements-dev.txt   # Development dependencies
└── main.py               # Application entry point
```

## Testing

Run the test suite:

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests with coverage
pytest -v --cov=bot --cov=config --cov=database --cov-report=html
```

## CI/CD

The project uses GitHub Actions for continuous integration and deployment:

- **CI Pipeline**: Runs on every push and pull request
  - Linting (flake8, black, isort)
  - Unit and integration tests
  - Security scanning (bandit, safety, trivy)
  - Docker image build and push

- **Daily Build**: Automatic daily Docker builds at 2 AM UTC

- **Release**: Triggered on version tags (v*)

## Kubernetes Deployment

See the [Discord Bot System Design Document](discord-bot-design.md) for comprehensive Kubernetes deployment instructions.

## Configuration

All configuration is done via environment variables. See [.env.example](.env.example) for available options.

### Required Environment Variables

- `DISCORD_BOT_TOKEN`: Discord bot token
- `DISCORD_PUBLIC_KEY`: Discord application public key
- `DATABASE_URL`: PostgreSQL connection string

### Optional Configuration

- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `LOG_FORMAT`: Log format (json, text)
- `MEDIA_STORAGE_PATH`: Path for media archival
- Feature flags for enabling/disabling functionality

## Monitoring

The bot exposes Prometheus metrics on port 8080:

- `/metrics`: Prometheus metrics
- `/healthz`: Liveness probe
- `/readyz`: Readiness probe

## Security

- Input validation and sanitization
- SQL injection prevention via parameterized queries
- ReDoS protection for regex patterns
- Rate limiting per user and server
- Audit logging for all administrative actions
- Secrets encrypted with SOPS

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run the test suite and linting
5. Submit a pull request

## License

[Add your license here]

## Support

[Add support information here]

