<p align="center">
  <h1 align="center">FFO Discord Bot</h1>
  <p align="center">Giveaways, automated reactions, reaction roles, media archival.</p>
</p>

<p align="center">
  <a href="https://github.com/curlsops/ffo-bot/actions/workflows/ci.yml"><img src="https://github.com/curlsops/ffo-bot/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://app.codecov.io/github/curlsops/ffo-bot"><img src="https://codecov.io/github/curlsops/ffo-bot/graph/badge.svg" alt="codecov"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-green.svg" alt="License"></a>
  <a href="https://github.com/curlsops/ffo-bot/pkgs/container/ffo-bot"><img src="https://img.shields.io/badge/ghcr.io-ffo--bot-blue?logo=docker" alt="Docker"></a>
</p>

---

## Quick Start

```bash
docker pull ghcr.io/curlsops/ffo-bot:latest
```

**Required env:** `DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`, `DATABASE_URL`

```bash
# Docker Compose
cd examples/docker-compose && cp .env.example .env
docker compose run --rm ffo-bot alembic upgrade head && docker compose up -d

# Kubernetes
kubectl apply -f examples/kubernetes/

# Local
pip install -r requirements.txt && alembic upgrade head && python main.py
```

---

## Bot Permissions

Add the bot with: Send Messages, Embed Links, Add Reactions, Read Message History, Use External Emojis, View Channels, Create Private Threads.

Generate invite: [Discord Developer Portal](https://discord.com/developers/applications) → OAuth2 → URL Generator → `bot` + `applications.commands`
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=277025704000&scope=bot%20applications.commands
```

---

## Features

| Feature | Description |
|---------|-------------|
| 🎉 Giveaways | Role requirements, bonus entries, private prize threads |
| 🤖 Reactions | Regex patterns → auto-reactions |
| 👥 Reaction Roles | Self-service role assignment |
| 📁 Media | Optional archival (disabled by default) |
| 🔐 Permissions | Super admin, admin, moderator roles |
| 📊 Metrics | `/metrics` on port 8080 (Prometheus) |

---

## Config

| Variable | Default |
|----------|---------|
| `HEALTH_CHECK_PORT` | 8080 |
| `FEATURE_MEDIA_DOWNLOAD` | false |
| `FEATURE_GIVEAWAYS` | true |
| `FEATURE_REACTION_ROLES` | true |
| `FEATURE_VOICE_TRANSCRIPTION` | false |

Endpoints: `/healthz`, `/readyz`, `/metrics`

---

## Roadmap

| Feature | Issue |
|---------|-------|
| Quotebook submissions | [#92](https://github.com/curlsops/ffo-bot/issues/92) |
| Minecraft FAQ & whitelist management | [#93](https://github.com/curlsops/ffo-bot/issues/93) |
| Voice transcription (mobile audio) | [#94](https://github.com/curlsops/ffo-bot/issues/94) |
| Currency & measurement conversion | [#95](https://github.com/curlsops/ffo-bot/issues/95) |
| Polls with more options | [#96](https://github.com/curlsops/ffo-bot/issues/96) |
| Reaction roles (Arcane replacement) | [#98](https://github.com/curlsops/ffo-bot/issues/98) |
| Ticketing system | [#97](https://github.com/curlsops/ffo-bot/issues/97) |

---

## Development

```bash
pytest tests/ -v
./build.sh
```

[CC BY-NC-SA 4.0](LICENSE) · [curlsops](https://github.com/curlsops)
