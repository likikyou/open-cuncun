# Feishu AI Companion

English | [中文](README_zh.md)

An AI companion chatbot running on Feishu (Lark), the Chinese enterprise messaging platform.

## Features

- **Multi-Provider AI**: Supports Cerebras, Groq, and DeepSeek with automatic fallback and circuit breaker
- **Streaming Replies**: Real-time streaming card replies with text fallback
- **Bionic Memory**: Post-conversation reflection, nightly consolidation, and Ebbinghaus forgetting curve decay
- **Multi-Layer Context**: Persona, user profile, relationship, long-term memory, bionic memory, knowledge, and web search
- **Multi-Conversation**: Create and switch between independent conversation contexts
- **Story Mode**: Open independent story-scenario conversations
- **Voice Matching**: Vector similarity search on voice library with emotion/theme filtering
- **Scheduled Tasks**: Morning/night reminders, database backup, memory maintenance
- **Observation System**: Real-time status snapshots and presence monitoring

## Screenshots

| Chat Demo | Morning Weather Reminder |
|:---:|:---:|
| ![Chat](docs/images/chat-demo.jpg) | ![Morning](docs/images/morning-weather-reminder.jpg) |

| Evening Weather Reminder | Brush Teeth Reminder |
|:---:|:---:|
| ![Evening](docs/images/evening-weather-reminder.jpg) | ![Brush](docs/images/brush-teeth-reminder.jpg) |

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
   pip install -r requirements.txt
   ```

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
   ```

### Running

#### Development Mode
```bash
python run.py
```

#### Production Mode
```bash
# Start web server
gunicorn -w 1 --threads 8 -b 0.0.0.0:8081 wsgi:app

# Start scheduler (in separate terminal)
python run_scheduler.py
```

## Configuration

All configuration is via environment variables in `.env`. See `.env.example` for available options.

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
python scripts/verify.py --offline
```

Run linting:
```bash
python -m ruff check app scripts
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - Layered architecture and call chains
- [Modules](docs/MODULES.md) - Module boundaries and environment variables
- [Deployment](docs/DEPLOYMENT.md) - Deployment guide
- [Changelog](docs/CHANGELOG.md) - Version history
- [Project History](docs/PROJECT_HISTORY.md) - How the project evolved over 210 commits
- [Technical Evolution](docs/TECHNICAL_EVOLUTION.md) - Key commits and architectural decisions
- [Observation System](docs/OBSERVATION_SYSTEM.md) - Real-time status snapshots and presence monitoring
- [Reading Order](docs/READING_ORDER.md) - Recommended reading order for new contributors
- [Stability Checklist](docs/STABILITY_CHECKLIST.md) - Daily ops, smoke tests, and stability checks

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for security policy and vulnerability reporting.
