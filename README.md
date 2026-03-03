<p align="center">
  <h1 align="center">FFO Discord Bot</h1>
  <p align="center">Giveaways, automated reactions, reaction roles, Minecraft whitelist, unit conversion, and more.</p>
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
| 📖 Quotebook | Submit and approve quotes with `/quote` commands |
| ❓ FAQ | Admin-managed FAQ topics with `/faq` |
| 📏 Unit Conversion | Auto-converts imperial units to SI in chat |
| ⛏️ Minecraft | Whitelist management via RCON with UUID validation |
| 📁 Media | Optional archival (disabled by default) |
| 🔐 Permissions | Super admin, admin, moderator roles |
| 📊 Metrics | `/metrics` on port 8080 (Prometheus) |

---

## Config

| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTH_CHECK_PORT` | 8080 | Health/metrics port |
| `FEATURE_GIVEAWAYS` | true | Enable giveaway commands |
| `FEATURE_REACTION_ROLES` | true | Enable reaction role setup |
| `FEATURE_QUOTEBOOK` | false | Enable quote submissions |
| `FEATURE_FAQ` | false | Enable FAQ commands |
| `FEATURE_CONVERSION` | false | Auto-convert imperial to SI |
| `FEATURE_MINECRAFT_WHITELIST` | false | Enable MC whitelist commands |
| `FEATURE_MEDIA_DOWNLOAD` | false | Archive media links |
| `FEATURE_VOICE_TRANSCRIPTION` | false | Transcribe voice messages |

### Minecraft RCON (optional)

| Variable | Description |
|----------|-------------|
| `MINECRAFT_RCON_HOST` | RCON server address |
| `MINECRAFT_RCON_PORT` | RCON port (default 25575) |
| `MINECRAFT_RCON_PASSWORD` | RCON password |

Endpoints: `/healthz`, `/readyz`, `/metrics`

---

## Roadmap

| Feature | Status |
|---------|--------|
| Quotebook submissions | ✅ Done |
| FAQ system | ✅ Done |
| Unit conversion | ✅ Done |
| Minecraft whitelist (RCON) | ✅ Done |
| Reaction roles | ✅ Done |
| Voice transcription | ✅ Done |
| Rotating status | ✅ Done |
| Ticketing system | 📋 Planned |

---

## Development

```bash
pytest tests/ -v
./build.sh
```

[CC BY-NC-SA 4.0](LICENSE) · [curlsops](https://github.com/curlsops)
