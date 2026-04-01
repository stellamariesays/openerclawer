"""
workspace/memory.py — Recent session context, injected every message.

Pull from daily log files, terrain notes, or wherever your agent
writes its memory. Return the most relevant recent context.

This is injected live — keep it tight. Not a full history dump.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path


def context() -> str:
    lines = []

    # Example: load today's daily log if it exists
    tz_offset  = timedelta(hours=8)  # adjust to your timezone
    today      = (datetime.now(timezone.utc) + tz_offset).strftime("%Y-%m-%d")
    daily_path = Path(__file__).parent.parent / "memory" / f"{today}.md"

    if daily_path.exists():
        lines.append(f"## Today ({today})\n")
        lines.append(daily_path.read_text().strip())
        lines.append("")

    # Example: load terrain delta (ongoing state summary)
    terrain = Path(__file__).parent.parent / "memory" / "terrain-delta.md"
    if terrain.exists():
        lines.append("## Terrain\n")
        lines.append(terrain.read_text().strip())
        lines.append("")

    return "\n".join(lines)
