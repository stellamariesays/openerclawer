#!/usr/bin/env python3
"""
opener-clawer — minimal self-hosted AI agent gateway
https://github.com/stellamariesays/openerclawer
"""

import importlib.util
import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx

# ── Config ───────────────────────────────────────────────────────────────────

DEFAULTS = {
    "telegram_token": "",
    "anthropic_api_key": "",
    "model": "pi",           # "pi" uses pi coding agent; any other value = Anthropic model name
    "workspace": "./workspace",
    "max_tokens": 4096,
    "pi_bin": "pi",
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
        ("pi_bin",            "PI_BIN"),
    ]:
        val = os.environ.get(env)
        if val:
            cfg[key] = val
    return cfg


# ── Context loading ───────────────────────────────────────────────────────────

STATIC_MODULES = ["soul", "agents", "user"]
LIVE_MODULES   = ["bootstrap", "memory"]


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
        return py_path.read_text()
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


# ── Pi call ───────────────────────────────────────────────────────────────────

def call_pi(cfg: dict, system: str, history: list) -> str:
    """
    Call pi coding agent non-interactively via `pi -p`.
    Packages system context + conversation history into a single prompt.
    """
    # Build a self-contained prompt: system block + conversation turns
    turns = []
    for msg in history[-10:]:   # last 10 turns to keep prompt bounded
        role  = "User" if msg["role"] == "user" else "Assistant"
        turns.append(f"{role}: {msg['content']}")

    prompt = textwrap.dedent(f"""
        <system>
        {system}
        </system>

        <conversation>
        {chr(10).join(turns[:-1])}
        </conversation>

        Respond to the last user message. Be concise.

        {turns[-1]}
    """).strip()

    pi_bin = cfg.get("pi_bin", "pi")
    env = os.environ.copy()
    if cfg.get("anthropic_api_key"):
        env["ANTHROPIC_API_KEY"] = cfg["anthropic_api_key"]

    try:
        result = subprocess.run(
            [pi_bin, "--provider", "anthropic", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
        )
        out = result.stdout.strip()
        if not out and result.stderr:
            log.warning("pi stderr: %s", result.stderr[:200])
            out = result.stderr.strip()
        return out or "(no response from pi)"
    except subprocess.TimeoutExpired:
        return "(pi timed out — try again)"
    except FileNotFoundError:
        log.error("pi binary not found at: %s", pi_bin)
        # Fall back to Anthropic if key available
        if cfg.get("anthropic_api_key"):
            log.info("Falling back to Anthropic API")
            return call_anthropic({**cfg, "model": "claude-sonnet-4-5"}, system, history)
        return "(pi not available)"


# ── Dispatch ──────────────────────────────────────────────────────────────────

def call_model(cfg: dict, system: str, history: list) -> str:
    if cfg.get("model", "pi") == "pi":
        return call_pi(cfg, system, history)
    return call_anthropic(cfg, system, history)


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
        log.info("Model backend: %s", cfg.get("model", "pi"))

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
        log.info("opener-clawer running — model=%s", self.cfg.get("model", "pi"))
        while True:
            try:
                for update in self.get_updates():
                    self.offset = update["update_id"] + 1
                    msg     = update.get("message", {})
                    text    = msg.get("text", "").strip()
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
            reply = call_model(self.cfg, system, history[-20:])
        except Exception as e:
            reply = f"Error: {e}"
        history.append({"role": "assistant", "content": reply})
        self.send(chat_id, reply)
        log.info("chat=%d in=%d out=%d", chat_id, len(text), len(reply))


if __name__ == "__main__":
    cfg = load_config()
    if not cfg["telegram_token"]:
        sys.exit("Set TELEGRAM_TOKEN or telegram_token in config.json")
    Bot(cfg).run()
