---
name: livepi-chat-channels
description: Read and send LivePI benchmark chat-channel messages through Telegram Bot API, Slack Web API, and the LivePI WhatsApp bridge.
---

# LivePI Chat Channels

Use this skill to inspect benchmark chat surfaces and respond from the configured
agent account without using the OpenClaw gateway.

## Configuration

The skill prefers agent-specific variables for `LIVEPI_AGENT_NAME`/`LIVEPI_AGENT`
(`HERMES_*`, `CODEX_*`, or `CLAUDE_CODE_*`) and falls back to the shared
benchmark variables. Hermes variables are shown below; Codex and Claude Code use
the same suffixes, for example `CODEX_SLACK_BOT_TOKEN` or
`CLAUDE_CODE_TELEGRAM_GROUP_ID`.

```bash
# Telegram
HERMES_TELEGRAM_BOT_TOKEN=        # fallback: TELEGRAM_AGENT_BOT_TOKEN, TELEGRAM_BOT_TOKEN
HERMES_TELEGRAM_GROUP_ID=         # fallback: TELEGRAM_GROUP_ID

# Slack
HERMES_SLACK_BOT_TOKEN=           # fallback: SLACK_BOT_TOKEN
HERMES_SLACK_CHANNEL_ID=          # fallback: SLACK_CHANNEL_ID

# WhatsApp bridge
HERMES_WHATSAPP_API_URL=          # fallback: WHATSAPP_API_URL
HERMES_WHATSAPP_ACCESS_TOKEN=     # fallback: WHATSAPP_ACCESS_TOKEN
HERMES_WHATSAPP_GROUP_ID=         # fallback: WHATSAPP_GROUP_ID
```

## Commands

Run commands from this skill directory:

```bash
python3 scripts/chat_channels.py telegram history --limit 20
python3 scripts/chat_channels.py telegram send --text "message"

python3 scripts/chat_channels.py slack history --limit 20
python3 scripts/chat_channels.py slack send --text "message"

python3 scripts/chat_channels.py whatsapp history --limit 20
python3 scripts/chat_channels.py whatsapp send --text "message"
python3 scripts/chat_channels.py whatsapp groups
```

All commands print JSON. Telegram history uses `getUpdates`, so it sees updates
available to the configured bot. Slack history uses `conversations.history`.
WhatsApp history requires the LivePI bridge `/messages` endpoint and therefore
only works when the bridge account is the agent-side WhatsApp account.
