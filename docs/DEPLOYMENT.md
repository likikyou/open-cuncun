# Deployment Guide

This guide covers deploying Feishu AI Companion to production.

## Prerequisites

- Python 3.10-3.12
- Gunicorn (for production web server)
- PM2 or systemd (for process management)
- Caddy or Nginx (for reverse proxy, optional)

## Production Deployment

### 1. Server Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/feishu-ai-companion.git
cd feishu-ai-companion

# Install dependencies
uv sync --extra dev --extra server

# Create and configure .env
cp .env.example .env
# Edit .env with your production values
```

### 2. Database Initialization

The SQLite database is automatically created on first run. Ensure the `data/db/` directory exists:

```bash
mkdir -p data/db data/db_local logs backups
```

### 3. Starting Services

#### Option A: Using PM2

```bash
# Start web server
pm2 start .venv/bin/gunicorn --interpreter none --name feishu-companion-web -- \
  -w 1 --threads 8 -b 0.0.0.0:8081 wsgi:app

# Start scheduler
pm2 start run_scheduler.py --name feishu-companion-scheduler --interpreter .venv/bin/python

# Save PM2 configuration
pm2 save

# Set PM2 to start on boot
pm2 startup
```

#### Option B: Using systemd

Create `/etc/systemd/system/feishu-companion-web.service`:
```ini
[Unit]
Description=Feishu AI Companion Web Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/feishu-ai-companion
Environment="PATH=/path/to/feishu-ai-companion/.venv/bin"
ExecStart=/path/to/feishu-ai-companion/.venv/bin/gunicorn \
  -w 1 --threads 8 -b 0.0.0.0:8081 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/feishu-companion-scheduler.service`:
```ini
[Unit]
Description=Feishu AI Companion Scheduler
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/feishu-ai-companion
Environment="PATH=/path/to/feishu-ai-companion/.venv/bin"
ExecStart=/path/to/feishu-ai-companion/.venv/bin/python run_scheduler.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl enable feishu-companion-web feishu-companion-scheduler
sudo systemctl start feishu-companion-web feishu-companion-scheduler
```

### 4. Reverse Proxy (Optional)

#### Caddy

Create `/etc/caddy/Caddyfile`:
```
your-domain.com {
    reverse_proxy localhost:8081
}
```

Start Caddy:
```bash
sudo systemctl enable caddy
sudo systemctl start caddy
```

#### Nginx

Create `/etc/nginx/sites-available/feishu-companion`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Enable and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/feishu-companion /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

## Health Check

Verify the deployment:
```bash
curl http://localhost:8081/health
```

With authentication for detailed info:
```bash
curl -H "Authorization: Bearer YOUR_HEALTH_AUTH_TOKEN" http://localhost:8081/health
```

## Environment Variables

See `.env.example` for all available configuration options.

### Critical Variables

```bash
# Feishu credentials (required)
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_ENCRYPT_KEY=your_encrypt_key

# AI provider (at least one required)
CEREBRAS_API_KEY=your_key
GROQ_API_KEY=your_key
DEEPSEEK_API_KEY=your_key

# Bot configuration
BOT_NAME=Companion
ADMIN_OPEN_ID=your_open_id
```

## Backup

Database backups are automatically created in `backups/` directory. Configure backup schedule in `.env`:

```bash
SCHEDULE_BACKUP=02:00  # Daily at 2 AM
```

## Monitoring

### Logs

Logs are written to `logs/feishu-companion.log` by default. Configure in `.env`:

```bash
LOG_FILE=logs/feishu-companion.log
```

### Health Endpoint

The `/health` endpoint provides system status:
- AI engine readiness
- Voice database status
- Provider circuit breaker state
- Recent AI run statistics

### Presence Endpoint

The `/presence` endpoint provides real-time observation data (requires `PRESENCE_AUTH_TOKEN`).

## Troubleshooting

### Common Issues

1. **Webhook not receiving events**
   - Verify Feishu app credentials
   - Check webhook URL configuration in Feishu Open Platform
   - Ensure server is accessible from internet

2. **AI responses failing**
   - Check API key validity
   - Verify provider circuit breaker state via `/health`
   - Check logs for error messages

3. **Voice matching not working**
   - Ensure voice library is configured: `VOICE_LIB=path/to/voices`
   - Verify ChromaDB is initialized: check `data/db_local/`

4. **Memory not persisting**
   - Check `DB_PATH` configuration
   - Verify SQLite database permissions
   - Check `data/db/` directory exists

## Updating

```bash
# Pull latest changes
git pull

# Update dependencies
uv sync --extra dev --extra server

# Restart services
pm2 restart feishu-companion-web feishu-companion-scheduler
# OR
sudo systemctl restart feishu-companion-web feishu-companion-scheduler
```

## Security Considerations

1. **Never commit `.env`**: Always use environment variables for secrets
2. **Use HTTPS**: Configure reverse proxy with SSL certificates
3. **Limit access**: Use `HEALTH_AUTH_TOKEN` and `PRESENCE_AUTH_TOKEN`
4. **Regular updates**: Keep dependencies updated for security patches
