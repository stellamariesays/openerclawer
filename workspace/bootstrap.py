"""
bootstrap.py — Live state, injected every message.

This is where you pull dynamic context: prices, open tasks, system status.
Return empty string if nothing relevant — don't pad.

Unlike a static .md file, this can call APIs, read generated files,
check cron outputs, etc. Keep it fast (<200ms).
"""

from pathlib import Path


def context() -> str:
    lines = ["## Live State\n"]

    # Example: read a generated state file if it exists
    state_file = Path.home() / "data" / "generated" / "state.json"
    if state_file.exists():
        import json
        try:
            state = json.loads(state_file.read_text())
            for k, v in state.items():
                lines.append(f"- **{k}:** {v}")
        except Exception:
            pass

    # Add your own live data sources here:
    # - crypto prices
    # - open tasks from a todo file
    # - system health checks
    # - weather

    if len(lines) == 1:
        return ""  # nothing to show

    return "\n".join(lines) + "\n"
