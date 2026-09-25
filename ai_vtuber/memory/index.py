"""AI VTuber - Compact session-memory index (data/memory.md).

``data/memory.md`` keeps a *Session Memories* section: one small entry per
completed session (title, date, topics, bullet summary).  Historical
retrieval searches this compact index FIRST and only then opens the few
matching full transcripts - much cheaper than BM25 over every message of
every session file.

File layout (deterministic, easy for both humans and LLMs to parse)::

    # Session Memories

    ## YYYY-MM-DD - <Title>

    **Session ID:** <id>
    **Topics:** comma, separated, keywords

    - summary bullet
    - summary bullet

Entries are keyed by ``session_id`` so re-consolidation UPDATES the
existing entry instead of appending duplicates.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .retrieval import BM25Index, tokenize
from .titler import extract_keywords, sanitize_title
from ..utils.time import now_india

logger = logging.getLogger(__name__)

INDEX_HEADER = "# Session Memories"
_ENTRY_RE = re.compile(
    r"^## (?P<date>\d{4}-\d{2}-\d{2}) - (?P<title>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)",
    re.DOTALL | re.MULTILINE,
)
_SID_RE = re.compile(r"^\*\*Session ID:\*\*\s*(.+)$", re.MULTILINE)
_TOPICS_RE = re.compile(r"^\*\*Topics:\*\*\s*(.+)$", re.MULTILINE)

# Recency blend weight for ranking (see rank_entries docstring).
_RECENCY_WEIGHT = 0.3


@dataclass
class MemoryEntry:
    """One compact indexed summary of a completed session."""
    session_id: str
    title: str
    date: str                       # YYYY-MM-DD
    topics: List[str] = field(default_factory=list)
    bullets: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join([self.title] + self.topics + self.bullets)

    def render(self) -> str:
        lines = [f"## {self.date} - {self.title}", ""]
        lines.append(f"**Session ID:** {self.session_id}")
        if self.topics:
            lines.append(f"**Topics:** {', '.join(self.topics)}")
        lines.append("")
        lines.extend(f"- {b}" for b in self.bullets)
        return "\n".join(lines) + "\n"


def _parse_entry(date: str, title: str, body: str) -> MemoryEntry:
    sid_m = _SID_RE.search(body)
    topics_m = _TOPICS_RE.search(body)
    topics = [t.strip() for t in (topics_m.group(1).split(",") if topics_m else [])
              if t.strip()]
    bullets = [ln[2:].strip() for ln in body.splitlines()
               if ln.strip().startswith("- ") and not ln.strip().startswith("- **")]
    return MemoryEntry(session_id=sid_m.group(1).strip() if sid_m else "",
                       title=title.strip(), date=date, topics=topics,
                       bullets=bullets)


class MemoryIndex:
    """Read/update the Session Memories index inside data/memory.md."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    # -- reading --------------------------------------------------------

    def load(self) -> List[MemoryEntry]:
        """Parse all index entries (oldest first). Empty list if no file."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        out = []
        for m in _ENTRY_RE.finditer(text):
            e = _parse_entry(m.group("date"), m.group("title"), m.group("body"))
            if e.session_id:
                out.append(e)
        return out

    # -- writing --------------------------------------------------------

    def update_entry(self, session_id: str, title: str, date: str,
                     topics: List[str], bullets: List[str]) -> bool:
        """Insert or UPDATE (by session id) one compact index entry.

        Never appends a duplicate for the same session; other content of
        memory.md (e.g. Airi's own long-term facts) is preserved untouched.
        Atomic write: temp file + os.replace.
        """
        title = sanitize_title(title) or "session"
        entry = MemoryEntry(session_id=session_id, title=title, date=date,
                            topics=[t for t in topics if t][:8],
                            bullets=[b.strip() for b in bullets if b.strip()][:8])
        with self._lock:
            try:
                text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
            except OSError:
                text = ""
            new_block = entry.render()
            pattern = re.compile(
                r"## \d{4}-\d{2}-\d{2} - [^\n]+\n.*?\*\*Session ID:\*\*\s*"
                + re.escape(session_id) + r"\s*\n.*?(?=^## |\Z)",
                re.DOTALL | re.MULTILINE)
            if pattern.search(text):
                text = pattern.sub(lambda _m: new_block + "\n", text, count=1)
            else:
                idx = text.find(INDEX_HEADER)
                if idx == -1:
                    header = INDEX_HEADER + (
                        "\n\nCompact summaries of past sessions. Each entry names\n"
                        "the session so the full transcript under data/sessions/\n"
                        "can be opened on demand.\n")
                    if text.strip():
                        text = text.rstrip() + "\n\n" + header + "\n" + new_block
                    else:
                        text = header + "\n" + new_block
                else:
                    # append after the last existing entry (keeps chronological order)
                    end = len(text)
                    nxt = None
                    for m in re.finditer(r"^## ", text[idx + len(INDEX_HEADER):],
                                         re.MULTILINE):
                        pass
                    inserts = [m.start() for m in
                               re.finditer(r"^## \d{4}-\d{2}-\d{2} - ", text,
                                           re.MULTILINE)]
                    if inserts:
                        # find end of last entry block
                        blocks = list(_ENTRY_RE.finditer(text))
                        end = blocks[-1].end() if blocks else len(text)
                    text = (text[:end].rstrip() + "\n\n" + new_block
                            + "\n" + text[end:].lstrip("\n")).rstrip() + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".md.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
        logger.info("[Memory] Updated memory.md (entry: %s)", title)
        return True

    # -- retrieval ------------------------------------------------------

    def search(self, query: str, top_k: int = 3,
               min_score: float = 0.3) -> List[tuple[MemoryEntry, float]]:
        """Rank index entries for *query*.

        Scoring model (documented deliberately - see project rules):

            score = BM25(query, title+topics+summary)  # keyword relevance
            final = (1 - W) * norm_bm25 + W * exp(-age_days / 60)   # + recency

        Recency is a mild tie-breaker (W = 0.3): an old but strongly
        matching session still outranks a recent unrelated one, while
        equally relevant sessions surface newest-first.  No vector DB:
        the corpus is tiny and BM25 over compact entries is enough.
        """
        entries = self.load()
        if not entries:
            return []
        q = tokenize(query)
        if not q:
            return []
        docs = [tokenize(e.text) for e in entries]
        scores = BM25Index().score_all(q, docs)
        top = max(scores) if scores else 0.0
        now = now_india()
        finals = []
        for e, s in zip(entries, scores):
            rel = (s / top) if top > 0 else 0.0
            try:
                d = datetime.strptime(e.date, "%Y-%m-%d").replace(tzinfo=now.tzinfo)
                age_days = max(0.0, (now - d).total_seconds() / 86400.0)
            except ValueError:
                age_days = 3650.0
            rec = 0.5 ** (age_days / 60.0)          # half-life ~60 days
            finals.append((e, (1 - _RECENCY_WEIGHT) * rel + _RECENCY_WEIGHT * rec, s))
        finals.sort(key=lambda x: -x[1])
        hits = [(e, f) for e, f, raw in finals if raw >= min_score]
        return hits[:top_k]
