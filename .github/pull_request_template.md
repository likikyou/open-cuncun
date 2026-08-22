## Summary

Describe what this change does and the user or maintainer problem it solves.

## Scope

- Related Issue:
- Affected areas:
- Out of scope:

## Verification

List the commands you ran and any manual checks you performed.

```text
uv run python scripts/verify.py --offline
uv run pytest tests
uv run ruff check app scripts tests
uv run python scripts/oss_release_audit.py
```

## Checklist

- [ ] The change follows the documented architecture and import boundaries.
- [ ] Tests cover new or changed behavior.
- [ ] Documentation and `docs/CHANGELOG.md` are updated when needed.
- [ ] No credentials, private prompts, user data, runtime files, or unlicensed assets are included.
- [ ] Logs, screenshots, and fixtures have been reviewed for sensitive information.
- [ ] Backward compatibility and deployment impact have been considered.
