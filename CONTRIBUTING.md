# Contributing to Feishu AI Companion

Thank you for your interest in contributing to Feishu AI Companion! This document provides guidelines and instructions for contributing.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Open a new issue with:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)

### Suggesting Features

1. Open a new issue with the `enhancement` label
2. Describe the feature and its use case
3. Explain why it would be valuable

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `python scripts/verify.py --offline`
5. Run linting: `python -m ruff check app scripts`
6. Commit with clear message
7. Push to your fork
8. Open a Pull Request

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/feishu-ai-companion.git
   cd feishu-ai-companion
   ```

2. Install dependencies:
   ```bash
   uv sync --extra dev --extra server
   ```

3. Create `.env` from example:
   ```bash
   cp .env.example .env
   ```

4. Run verification:
   ```bash
   python scripts/verify.py --offline
   ```

## Code Style

- Follow PEP 8
- Use Ruff for linting: `python -m ruff check app scripts`
- Maximum line length: 100 characters
- Use type hints where appropriate

## Architecture Guidelines

Follow the layered architecture:

- **Entrypoints**: HTTP handlers, scheduler jobs
- **Application**: Use-case orchestration
- **Domain**: Pure business rules (no I/O)
- **Infrastructure**: External adapters (AI, Feishu, database)
- **Presentation**: Event parsing, card builders, formatters

### Import Rules

- `application/` cannot import from `main`, `bootstrap`, or `entrypoints`
- `domain/` cannot import from `application`, `presentation`, or `infrastructure`
- Never import deleted facade modules

## Testing

Run the offline verification suite before submitting:
```bash
python scripts/verify.py --offline
```

This runs 24+ checks including:
- Architecture guardrails
- Import validation
- Context assembly
- Command handling
- Webhook processing
- Health checks

## Documentation

Update documentation when adding features:
- `docs/ARCHITECTURE.md` for architectural changes
- `docs/MODULES.md` for new modules
- `docs/CHANGELOG.md` for version history

## Questions?

Open a discussion in the GitHub Discussions tab for questions about contributing.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
