# Contributing to Cuncun Core

Thank you for your interest in contributing to Cuncun Core! This document provides guidelines and instructions for contributing.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

Contributions are not limited to code. Reproducible bug reports, documentation fixes,
test cases, provider compatibility notes, and onboarding improvements are valuable too.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Do not open a public issue for security vulnerabilities or private-data reports;
   follow [SECURITY.md](SECURITY.md)
3. Use the bug report form with:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)

### Suggesting Features

1. Check the [open-source roadmap](docs/OPEN_SOURCE_ROADMAP.md) and existing issues
2. Open a feature request using the repository template
3. Describe the feature, its user, and why it belongs in the reusable public Core

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `uv run python scripts/verify.py --offline && uv run pytest tests`
5. Run linting: `uv run ruff check app scripts tests`
6. Run the public-release audit: `uv run python scripts/oss_release_audit.py`
7. Commit with a clear message
8. Push to your fork
9. Open a Pull Request

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/open-cuncun.git
   cd open-cuncun
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
   uv run python scripts/verify.py --offline
   ```

## Code Style

- Follow PEP 8
- Use Ruff for linting: `uv run ruff check app scripts tests`
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
uv run python scripts/verify.py --offline
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

Open a discussion in the GitHub Discussions tab for questions about contributing or
read [SUPPORT.md](SUPPORT.md). Use Issues for reproducible bugs and scoped work, not
general setup support.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
