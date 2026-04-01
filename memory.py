#!/usr/bin/env python3
"""
memory.py — BM25-based memory search for opener-clawer

Never depends on an LLM or external API.
BM25 is the baseline — always works.
Embeddings (optional) can re-rank results if an API key is available.

Usage:
    from memory import search
    results = search("what did we decide about BRAID?", workspace_path)
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ── BM25 ─────────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    path: str
    text: str
    tokens: list[str]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def build_index(workspace: Path) -> list[Chunk]:
    """Index all .md and .py files in the workspace."""
    chunks = []
    for path in sorted(workspace.rglob("*.md")) + sorted(workspace.rglob("*.py")):
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        # Split into ~200-word chunks
        words = text.split()
        for i in range(0, max(1, len(words)), 200):
            chunk_text = " ".join(words[i:i + 200])
            chunks.append(Chunk(
                path=str(path.relative_to(workspace)),
                text=chunk_text,
                tokens=tokenize(chunk_text),
            ))
    return chunks


def bm25_scores(query: str, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> list[float]:
    q_tokens = tokenize(query)
    if not chunks or not q_tokens:
        return [0.0] * len(chunks)

    avg_len = sum(len(c.tokens) for c in chunks) / len(chunks)
    doc_freqs: Counter = Counter()
    for chunk in chunks:
        for tok in set(chunk.tokens):
            doc_freqs[tok] += 1
    N = len(chunks)

    scores = []
    for chunk in chunks:
        tf = Counter(chunk.tokens)
        dl = len(chunk.tokens)
        score = 0.0
        for tok in q_tokens:
            if tok not in tf:
                continue
            idf = math.log((N - doc_freqs[tok] + 0.5) / (doc_freqs[tok] + 0.5) + 1)
            freq = tf[tok]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avg_len))
        scores.append(score)
    return scores


# ── Optional: embeddings re-rank ──────────────────────────────────────────────

def _try_rerank(query: str, candidates: list[Chunk], api_key: Optional[str]) -> Optional[list[Chunk]]:
    """Re-rank top BM25 candidates with embeddings if API key is available."""
    if not api_key:
        return None
    try:
        import httpx
        texts = [query] + [c.text for c in candidates]
        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "text-embedding-3-small", "input": texts},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        vecs = [d["embedding"] for d in resp.json()["data"]]
        q_vec = vecs[0]
        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na  = math.sqrt(sum(x * x for x in a))
            nb  = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb + 1e-9)
        scored = sorted(
            zip(candidates, vecs[1:]),
            key=lambda x: cosine(q_vec, x[1]),
            reverse=True,
        )
        return [c for c, _ in scored]
    except Exception:
        return None  # silently fall back to BM25


# ── Public API ────────────────────────────────────────────────────────────────

def search(
    query: str,
    workspace: Path,
    top_k: int = 5,
    openai_api_key: Optional[str] = None,
) -> list[dict]:
    """
    Search workspace files for query.
    Returns list of {path, text, score} dicts.

    Always works (BM25). Optionally re-ranks with embeddings.
    """
    chunks = build_index(workspace)
    if not chunks:
        return []

    scores = bm25_scores(query, chunks)
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    top    = [c for c, s in ranked[:top_k * 3] if s > 0]  # wider net for rerank

    if openai_api_key:
        reranked = _try_rerank(query, top, openai_api_key)
        if reranked:
            top = reranked

    return [{"path": c.path, "text": c.text} for c in top[:top_k]]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: memory.py <workspace_path> <query>")
        sys.exit(1)
    ws      = Path(sys.argv[1])
    query   = " ".join(sys.argv[2:])
    results = search(query, ws)
    for r in results:
        print(f"\n--- {r['path']} ---\n{r['text'][:300]}")
