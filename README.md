# Cuncun Core

English | [中文](README_zh.md)

[![CI](https://github.com/likikyou/open-cuncun/actions/workflows/ci.yml/badge.svg)](https://github.com/likikyou/open-cuncun/actions/workflows/ci.yml)
[![Python 3.10-3.12](https://img.shields.io/badge/Python-3.10--3.12-3776AB.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Turn Feishu/Lark into a self-hosted AI companion with durable memory, provider
fallback, privacy-aware vision, and safe automation.**

Cuncun Core is a Feishu-first Python runtime for developers who want to own their
companion's data and deployment while retaining the freedom to choose AI providers.

## Why Cuncun Core

- **Memory is a lifecycle, not a transcript dump**: reflection, consolidation,
  importance scoring, and forgetting are built into the runtime.
- **Provider failures are expected**: routing, fallback, circuit breaking, and health
  signals keep the conversation path observable and resilient.
- **Images stay local by default**: external vision is opt-in and degrades safely.
- **The core has explicit boundaries**: transport, AI, persistence, presentation, and
  future client integrations can evolve without sharing private personas or data.

## Project status

Cuncun Core 5.8 is currently in release-candidate stage. Feishu/Lark is the first
maintained transport, and the current deployment model is intended for personal or
private single-user use rather than multi-tenant SaaS. See the
[open-source roadmap](docs/OPEN_SOURCE_ROADMAP.md) and [security policy](SECURITY.md).

> Project direction: `open-cuncun` is the canonical public Cuncun Core. Private
> deployments should consume tagged releases and keep personas, credentials,
> runtime data, operator configuration, and owned assets outside this repository.
> See the [open-source roadmap](docs/OPEN_SOURCE_ROADMAP.md).

## Features

- **Multi-Provider AI**: Supports Cerebras, Groq, and DeepSeek with automatic fallback and circuit breaker
- **Opt-in Gemma Vision**: Keeps images local by default; explicit Cerebras Gemma or legacy Qwen mode includes safe fallback and privacy-preserving shadow metadata
- **Streaming Replies**: Real-time streaming card replies with text fallback
- **Bionic Memory**: Post-conversation reflection, nightly consolidation, and Ebbinghaus forgetting curve decay
- **Multi-Layer Context**: Persona, user profile, relationship, long-term memory, bionic memory, knowledge, and web search
- **Multi-Conversation**: Create and switch between independent conversation contexts
- **Story Mode**: Open independent story-scenario conversations
- **Voice Matching**: Vector similarity search on voice library with emotion/theme filtering
- **Scheduled Tasks**: Morning/night reminders, database backup, memory maintenance
- **Observation System**: Real-time status snapshots and presence monitoring

## Quick Start

### Prerequisites

- Python 3.10-3.12
- Feishu (Lark) Open Platform account
- At least one AI provider API key (Cerebras, Groq, or DeepSeek)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/likikyou/open-cuncun.git
   cd open-cuncun
   ```

2. Install dependencies:
   ```bash
   # Using uv (recommended)
   uv sync --extra dev --extra server

   # Or using pip
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   pip install "gunicorn>=23,<24"  # Required for production serving
   ```

   The commands below use `uv run`. If you chose the pip path, keep `.venv`
   activated and omit the `uv run` prefix.

3. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` with your configuration:
   - Feishu credentials (APP_ID, APP_SECRET, ENCRYPT_KEY)
   - AI provider API keys
   - Bot name and other settings

5. Customize your prompt template:
   ```bash
   cp data/prompts/example_prompt_template.txt data/prompts/prompt_template.txt
   # Edit data/prompts/prompt_template.txt with your character definition
   # Set PROMPT_PATH=data/prompts/prompt_template.txt in .env
   ```

6. Validate the installation without sending data to AI providers or Feishu:
   ```bash
   uv run python scripts/verify.py --offline
   ```

### Running

#### Development Mode
```bash
uv run python run.py
```

#### Production Mode
```bash
# Start web server
uv run gunicorn -w 1 --threads 8 -b 0.0.0.0:8081 wsgi:app

# Start scheduler (in separate terminal)
uv run python run_scheduler.py
```

## Configuration

All configuration is via environment variables in `.env`. See `.env.example` for available options.

### Third-party services

AI and search providers have their own terms and data policies. Text requests are
sent to the providers you configure. Images stay local in the default `safe_text`
mode and leave the server only when `gemma` or `qwen` is explicitly enabled.

### Key Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_NAME` | Bot display name | `Companion` |
| `AI_PROVIDER` | AI provider (`cerebras`, `groq`, `deepseek`) | `cerebras` |
| `PROMPT_PATH` | Path to prompt template | `data/prompts/example_prompt_template.txt` |
| `DEFAULT_WEATHER_LOCATION` | Default weather location | `中国北京` |

## Commands

| Command | Description |
|---------|-------------|
| `/status` | View data dashboard |
| `/observe` | Real-time observation snapshot |
| `/model` | Switch AI model |
| `/reply` | Set reply mode |
| `/reset` | Start new conversation |
| `/clear` | Clear context |
| `/pure` | Toggle pure chat test mode |
| `/chat` | Multi-conversation management |
| `/story` | Story mode |
| `/memory` | View bionic memory |
| `/help` | Show help |

## Current limitations

- Designed for personal or private single-user deployments, not multi-tenant hosting.
- Production serving should keep one web worker; some deduplication, circuit-breaker,
  and recent observability state is process-local.
- There is no built-in rate limiter. Put a TLS reverse proxy and request controls in
  front of internet-facing deployments.
- SQLite and local vector storage favor modest self-hosted workloads over high write
  concurrency.

## Architecture

The project follows a modular monolith pattern with four layers:

```
Entrypoints (webhook, scheduler)
  → Application (orchestration services)
    → Domain (pure business rules)
    → Infrastructure (AI, Feishu, SQLite, ChromaDB)
    → Presentation (event parsing, card builders)
```

## Testing

Run the offline verification suite:
```bash
uv run python scripts/verify.py --offline
```

Run linting:
```bash
uv run ruff check app scripts tests
```

Run the public-release safety audit:
```bash
uv run python scripts/oss_release_audit.py
```

Run vision smoke tests:
```bash
uv run pytest tests/vision_gemma_primary_smoke.py tests/vision_shadow_smoke.py
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - Layered architecture and call chains
- [Modules](docs/MODULES.md) - Module boundaries and environment variables
- [Deployment](docs/DEPLOYMENT.md) - Deployment guide
- [Changelog](docs/CHANGELOG.md) - Version history
- [Project History](docs/PROJECT_HISTORY.md) - Retrospective from 210 internal development commits
- [Technical Evolution](docs/TECHNICAL_EVOLUTION.md) - Key commits and architectural decisions
- [Observation System](docs/OBSERVATION_SYSTEM.md) - Real-time status snapshots and presence monitoring
- [Reading Order](docs/READING_ORDER.md) - Recommended reading order for new contributors
- [Stability Checklist](docs/STABILITY_CHECKLIST.md) - Daily ops, smoke tests, and stability checks
- [Open-source Roadmap](docs/OPEN_SOURCE_ROADMAP.md) - Repository boundaries and publication policy
- [Core API v1](docs/CORE_API_V1.md) - Stable boundary for future Console and voice clients

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions of code, tests, documentation, and reproducible bug reports are welcome.
See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[open Issues](https://github.com/likikyou/open-cuncun/issues).

For setup and usage questions, use
[GitHub Discussions](https://github.com/likikyou/open-cuncun/discussions) or read
[SUPPORT.md](SUPPORT.md).

## Security

See [SECURITY.md](SECURITY.md) for security policy and vulnerability reporting.
