# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 5.7.x   | :white_check_mark: |
| < 5.7   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Email security concerns to: [your-email@example.com]
3. Include a detailed description of the vulnerability
4. Provide steps to reproduce if possible

## Security Measures

### API Keys and Secrets

- All API keys and secrets are stored in environment variables
- `.env` files are excluded from version control via `.gitignore`
- `.env.example` provides a template with placeholder values

### Feishu Integration

- Webhook requests are verified using SHA256 signatures
- Message payloads are decrypted using AES
- Event deduplication prevents replay attacks

### Data Protection

- User data is stored in SQLite databases excluded from version control
- Vector databases (ChromaDB) are excluded from version control
- Logs are excluded from version control
- Backups are excluded from version control

### Best Practices

1. **Never commit secrets**: Always use environment variables for sensitive data
2. **Rotate keys regularly**: Change API keys periodically
3. **Limit access**: Use `ADMIN_OPEN_ID` to restrict admin functions
4. **Monitor logs**: Check logs for suspicious activity
5. **Keep dependencies updated**: Regularly update Python packages

## Security Configuration

### Required Environment Variables

```bash
# Feishu credentials (required)
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_ENCRYPT_KEY=your_encrypt_key

# At least one AI provider key
CEREBRAS_API_KEY=your_key
GROQ_API_KEY=your_key
DEEPSEEK_API_KEY=your_key
```

### Optional Security Settings

```bash
# Health endpoint authentication
HEALTH_AUTH_TOKEN=your_token

# Presence endpoint authentication
PRESENCE_AUTH_TOKEN=your_token

# Admin user ID
ADMIN_OPEN_ID=your_open_id
```

## Known Security Considerations

1. **Single-user design**: This bot is designed for personal/private use, not multi-tenant
2. **No built-in rate limiting**: Consider adding rate limiting for production deployments
3. **SQLite concurrency**: SQLite has limited concurrent write support; consider PostgreSQL for high-traffic deployments

## Updates

Security updates will be released as patch versions. Always use the latest version for security fixes.
