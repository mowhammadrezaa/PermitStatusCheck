# Permesso di Soggiorno Tracker Bot

A Telegram bot that checks the status of Italian residence permits (Permesso di Soggiorno) by querying the official Polizia di Stato portal.

## Status Meanings

| Status | Meaning |
|--------|---------|
| Ready for Pickup | Your permit is ready — book an appointment at your Questura |
| Being Processed | Your application is in progress — check back later |
| Not Yet Started | No info found — processing hasn't begun or code is wrong |

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** you receive

### 2. Local Development

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/mamad_permesso.git
cd mamad_permesso

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set environment variable
copy .env.example .env
# Edit .env and add your BOT_TOKEN

# Run the bot
python bot.py
```

### 3. Deploy on Railway

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) and create a new project
3. Select **Deploy from GitHub repo** and pick this repository
4. Go to **Variables** and add:
   - `BOT_TOKEN` = your Telegram bot token
5. Railway will auto-deploy. The bot starts as a **worker** process (no web port needed)

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show the main menu |
| `/check` | Check a permit code |
| `/help`  | Show help & status meanings |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |

## License

MIT
