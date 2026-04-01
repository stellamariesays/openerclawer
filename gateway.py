#!/usr/bin/env python3
"""
opener-clawer — minimal self-hosted AI agent gateway
https://github.com/stellamariesays/opener-clawer
"""

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

import httpx

# ── Config ───────────────────────────────────────────────────────────────────

DEFAULTS = {
    "telegram_token": "",
    "anthropic_api_key": "",
    "model": "claude-sonnet-4-5",
    "workspace": "./workspace",
    "max_tokens": 4096,
}

CONFIG_PATH = Path(__file__).parent / "config.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("opener-clawer")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    for key, env in [
        ("telegram_token",    "TELEGRAM_TOKEN"),
        ("anthropic_api_key", "ANTHROPIC_API_KEY"),
        ("model",             "AGENT_MODEL"),
        ("workspace",         "AGENT_WORKSPACE"),
    ]:
        val = os.environ.get(env)
        if val:
            cfg[key] = val
    return cfg


# ── Context loading ───────────────────────────────────────────────────────────
#
# Workspace files can be either:
#   - <name>.py  — Python module with a context() -> str function (dynamic)
#   - <NAME>.md  — Plain text / markdown (static)
#
# .py is preferred. This lets context be live (pull from APIs, files, DBs)
# rather than just static markdown.

STATIC_MODULES = ["soul", "agents", "user"]   # loaded once at startup
LIVE_MODULES   = ["bootstrap", "memory"]       # reloaded every message


def load_module(ws: Path, name: str) -> str:
    """Load a context module. .py preferred, .md fallback."""
    py_path = ws / f"{name}.py"
    md_path = ws / f"{name.upper()}.md"

    if py_path.exists():
        spec = importlib.util.spec_from_file_location(name, py_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "context"):
            return mod.context()
        return py_path.read_text()  # no context() fn: use source as text
    elif md_path.exists():
        return md_path.read_text()
    return ""


def build_system_prompt(cfg: dict, static: str) -> str:
    ws   = Path(cfg["workspace"])
    live = "".join(load_module(ws, m) for m in LIVE_MODULES)
    return static + "\n\n" + live


# ── Anthropic call ────────────────────────────────────────────────────────────

def call_anthropic(cfg: dict, system: str, history: list) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":          cfg["anthropic_api_key"],
            "anthropic-version":  "2023-06-01",
            "content-type":       "application/json",
        },
        json={
            "model":      cfg["model"],
            "max_tokens": cfg["max_tokens"],
            "system":     system,
            "messages":   history,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


# ── Telegram bot loop ─────────────────────────────────────────────────────────

class Bot:
    def __init__(self, cfg: dict):
        self.cfg    = cfg
        self.token  = cfg["telegram_token"]
        self.base   = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self.history: dict[int, list] = {}
        ws = Path(cfg["workspace"])
        self.static = "".join(load_module(ws, m) for m in STATIC_MODULES)
        log.info("Static context loaded (%d chars)", len(self.static))

    def get_updates(self):
        r = httpx.get(
            f"{self.base}/getUpdates",
            params={"offset": self.offset, "timeout": 30},
            timeout=35,
        )
        return r.json().get("result", [])

    def send(self, chat_id: int, text: str):
        httpx.post(
            f"{self.base}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )

    def run(self):
        log.info("opener-clawer running — model=%s", self.cfg["model"])
        while True:
            try:
                for update in self.get_updates():
                    self.offset = update["update_id"] + 1
                    msg    = update.get("message", {})
                    text   = msg.get("text", "").strip()
                    chat_id = msg.get("chat", {}).get("id")
                    if not text or not chat_id:
                        continue
                    self.handle(chat_id, text)
            except Exception as e:
                log.error("Loop error: %s", e)

    def handle(self, chat_id: int, text: str):
        history = self.history.setdefault(chat_id, [])
        history.append({"role": "user", "content": text})
        system = build_system_prompt(self.cfg, self.static)
        try:
            reply = call_anthropic(self.cfg, system, history[-20:])
        except Exception as e:
            reply = f"Error: {e}"
        history.append({"role": "assistant", "content": reply})
        self.send(chat_id, reply)
        log.info("chat=%d in=%d out=%d", chat_id, len(text), len(reply))


if __name__ == "__main__":
    cfg = load_config()
    if not cfg["telegram_token"]:
        sys.exit("Set TELEGRAM_TOKEN or telegram_token in config.json")
    if not cfg["anthropic_api_key"]:
        sys.exit("Set ANTHROPIC_API_KEY or anthropic_api_key in config.json")
    Bot(cfg).run()
