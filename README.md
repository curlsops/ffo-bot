# FFO Discord Bot

[![CI](https://github.com/MrCurlsTTV/ffo-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/MrCurlsTTV/ffo-bot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/MrCurlsTTV/ffo-bot/graph/badge.svg?token=X4PwF9Boi9)](https://codecov.io/github/MrCurlsTTV/ffo-bot)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

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

- Python 3.12+
- PostgreSQL 16+
- Discord Bot Token
- Docker (optional)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/MrCurlsTTV/ffo-bot.git
   cd ffobot
   ```

2. **Create virtual environment**
   ```bash
   python3.12 -m venv venv
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

Run the test suite (196 tests, ~86% coverage):

```bash
# Run all tests with coverage
pytest tests/ -v --cov=bot --cov=config --cov=database --cov-report=html

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Run build script (linting + tests + Docker build)
./build.sh
```

## CI/CD

The project uses GitHub Actions for continuous integration and deployment:

- **CI Pipeline** (`ci.yml`): Runs on every push and pull request
  - Linting (flake8, black, isort)
  - Unit and integration tests with PostgreSQL
  - Coverage reporting to Codecov
  - Docker image build

- **Release Please** (`release-please.yml`): Automated semantic versioning
  - Analyzes conventional commits to determine version bump
  - Creates release PRs with changelog updates
  - On merge: creates GitHub Release and pushes Docker image to GHCR

- **Auto-merge** (`auto-merge.yml`): Automatically merges Renovate dependency PRs after CI passes

### Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/) for automatic versioning:

| Commit Type | Version Bump | Example |
|-------------|--------------|---------|
| `fix:` | Patch (0.0.x) | `fix: resolve database timeout` |
| `feat:` | Minor (0.x.0) | `feat: add new slash command` |
| `feat!:` or `BREAKING CHANGE:` | Major (x.0.0) | `feat!: change API response format` |

### Release Flow

1. Push commits to `main` using conventional commit messages
2. Release Please automatically creates/updates a release PR
3. Merge the release PR to create the release
4. Docker image is automatically built and pushed to `ghcr.io/mrcurlsttv/ffo-bot`

## Deployment

### Docker

Pull the latest image from GitHub Container Registry:

```bash
docker pull ghcr.io/mrcurlsttv/ffo-bot:latest
```

Or build locally:

```bash
docker buildx build -t ffo-bot:latest .
```

### Example Deployments

We provide ready-to-use deployment examples:

- **[Docker Compose](examples/docker-compose/)** - Simple single-host deployment
- **[Kubernetes](examples/kubernetes/)** - Production Kubernetes manifests

**Note:** The bot requires an external PostgreSQL database. The database is not bundled with the Docker image.

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

MIT License - see [LICENSE](LICENSE) for details.

