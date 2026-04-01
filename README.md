# opener-clawer

A minimal, self-hosted AI agent gateway. Bring your own identity, run your own agent.

---

## What it is

A Telegram bot that runs a Claude-backed agent from a Docker container.
The agent's personality, memory, and live state are defined by your `workspace/` — Python modules that generate context at runtime.

No SaaS. No cloud sync. No vendor lock-in beyond the LLM API.

---

## Architecture

```
workspace/
├── soul.py       ← who is your agent (identity, voice, stances)
├── agents.py     ← routing rules + hard safety limits
├── user.py       ← about your human
├── bootstrap.py  ← live state (prices, todos, system status — reloaded every message)
└── memory.py     ← recent session context (reloaded every message)

gateway.py        ← Telegram bot loop + Anthropic calls
memory.py         ← BM25 search over workspace files (no LLM dependency)
```

Context files are `.py` by default — they can call APIs, read files, compute state.
Drop-in `.md` fallback is supported for static content.

---

## Memory search

`memory.py` provides BM25-based search over workspace files.
- **Always works.** No external API required.
- **Optionally enhanced** with OpenAI embeddings for re-ranking if an API key is available.
- Never fails because an LLM is down.

```python
from memory import search
results = search("what did we decide about X?", Path("./workspace"))
```

Or from the command line:
```bash
python3 memory.py ./workspace "what did we decide about X?"
```

---

## Setup

**1. Clone and configure**
```bash
git clone https://github.com/stellamariesays/opener-clawer
cd opener-clawer
cp config.json.example config.json
# edit config.json with your tokens
```

**2. Fill in your workspace**

Edit the files in `workspace/`. Each has instructions at the top.
At minimum: `soul.py` (who is your agent) and `user.py` (who is your human).

**3. Run**
```bash
# Docker (recommended)
docker compose up -d

# Or directly
pip install -r requirements.txt
python3 gateway.py
```

---

## Workspace files

| File | Reloaded | Purpose |
|------|----------|---------|
| `soul.py` | startup | identity, voice |
| `agents.py` | startup | routing, safety rules |
| `user.py` | startup | about your human |
| `bootstrap.py` | every message | live state (prices, tasks, etc.) |
| `memory.py` | every message | recent session context |

Static modules are loaded once. Live modules are reloaded on every message so they always reflect current state.

---

## Design principles

- Memory search must never depend on an LLM to function
- Context is code, not config — `.py` over `.md`
- Topology over literals — the structure is the contribution, not the content
- Self-hosted first — your data stays on your machine

---

## Requirements

- Python 3.12+
- Telegram bot token ([BotFather](https://t.me/BotFather))
- Anthropic API key

---

## License

MIT
