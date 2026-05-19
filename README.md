<div align="center">

# FFO Discord Bot

Giveaways, automated reactions, reaction roles, Minecraft whitelist, unit conversion, and more.

[![CI](https://github.com/curlsops/ffo-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/curlsops/ffo-bot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/curlsops/ffo-bot/graph/badge.svg)](https://app.codecov.io/github/curlsops/ffo-bot)
[![License](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/ghcr.io-ffo--bot-blue?logo=docker)](https://github.com/curlsops/ffo-bot/pkgs/container/ffo-bot)

</div>

## Quick Start

```bash
docker pull ghcr.io/curlsops/ffo-bot:latest
```

**Required env:** `DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`, and either `DATABASE_URL` or `DB_HOST` / `DB_NAME` / `DB_USER` (optional: `DB_PORT`, `DB_PASSWORD`)

```bash
# Docker Compose
cd examples/docker-compose && cp .env.example .env
docker compose run --rm ffo-bot alembic upgrade head && docker compose up -d

# Kubernetes
kubectl apply -f examples/kubernetes/

# Local
pip install -r requirements.txt && alembic upgrade head && python main.py
```

## Bot Permissions

Send Messages, Embed Links, Add Reactions, Read Message History, Use External Emojis, View Channels, Create Private Threads. For music: Connect, Speak.

OAuth2 URL Generator: `bot` + `applications.commands` — [Developer Portal](https://discord.com/developers/applications)

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=277831010368&scope=bot%20applications.commands
```

## Features

| Feature | Description |
|---------|-------------|
| Giveaways | Role requirements, bonus entries, private prize threads |
| Reactions | Regex patterns → auto-reactions |
| Reaction roles | Self-service role assignment |
| Quotebook | Submit and approve quotes with `/quote` |
| FAQ | Admin-managed topics with `/faq` |
| Unit conversion | Imperial → SI in chat |
| Minecraft | Whitelist via RCON, UUID validation |
| Music | Lavalink: `/music join`, play, leave, pause, resume, skip, queue |
| Permissions | Super admin, admin, moderator |
| Metrics | `/metrics` on port 8080 (Prometheus) |
| Help | `/help` lists slash commands |
| Command registration | `/admin register_commands` |
| Cooldowns | `with_cooldown(rate, per)` |
| Collector | `wait_for_message`, `wait_for_reaction` |
| Edit tracking | Updates reply when user edits prefix command |
| Interactions endpoint | Optional `POST /interactions` (PING) |

**Planned:** ticketing.

## Config

| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTH_CHECK_PORT` | 8080 | Health / metrics port |
| `HEALTH_CHECK_HOST` | 0.0.0.0 | Bind (`0.0.0.0` = all interfaces) |
| `FEATURE_GIVEAWAYS` | true | Giveaway commands |
| `FEATURE_REACTION_ROLES` | true | Reaction role setup |
| `FEATURE_QUOTEBOOK` | false | Quote submissions |
| `FEATURE_FAQ` | false | FAQ commands |
| `FEATURE_CONVERSION` | false | Auto-convert imperial to SI |
| `FEATURE_MINECRAFT_WHITELIST` | false | Minecraft whitelist commands |
| `FEATURE_VOICE_TRANSCRIPTION` | false | Transcribe voice messages |
| `FEATURE_FAQ_SUBMISSIONS` | true | Users can submit FAQ questions |
| `FEATURE_NOTIFY_MODERATION` | true | Notify on kicks, bans, nick changes |
| `FEATURE_NOTIFY_RATE_LIMIT` | false | Notify on user rate limit |
| `INTERACTIONS_ENDPOINT_ENABLED` | false | `POST /interactions` for Interactions Endpoint URL (PING only) |
| `FEATURE_MUSIC` | false | Lavalink music commands |
| `LAVALINK_HOST` | 127.0.0.1 | Lavalink host |
| `LAVALINK_PORT` | 2333 | Lavalink port |
| `LAVALINK_PASSWORD` | — | Required when music is enabled |

HTTP: `/healthz`, `/readyz`, `/metrics`

### Lavalink (`FEATURE_MUSIC`)

[Lavalink](https://github.com/lavalink-devs/Lavalink) + [Mafic](https://github.com/ArtiArtem8/mafic) (pinned in `requirements.txt`). YouTube search/URLs; LavaSrc adds Spotify/Tidal. Play accepts Tidal track, album, playlist, and mix URLs.

### Minecraft RCON

| Variable | Description |
|----------|-------------|
| `MINECRAFT_RCON_HOST` | Server address |
| `MINECRAFT_RCON_PORT` | Port (default 25575) |
| `MINECRAFT_RCON_PASSWORD` | Password |

## Development

```bash
pytest tests/ -v
./scripts/build.sh
```

[CC BY-NC-SA 4.0](LICENSE) · [curlsops](https://github.com/curlsops)
