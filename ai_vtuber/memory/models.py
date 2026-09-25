"""AI VTuber - Memory data models.

Shared, dependency-free dataclasses used by the session store, the
retrieval layer and the consolidation pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SessionMessage:
    """A single persisted conversation message inside a session."""
    role: str                 # "user" | "assistant"
    content: str
    timestamp: str = ""       # ISO-like "YYYY-MM-DD HH:MM:SS"
    emotion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "emotion": self.emotion,
        }


@dataclass
class Session:
    """One continuous interaction period (boot -> shutdown).

    The Markdown file under ``data/sessions/`` is the source of truth;
    this object is just a parsed view of it plus runtime metadata.
    """
    session_id: str
    started: str = ""
    closed: bool = False
    messages: List[SessionMessage] = field(default_factory=list)
    summary: str = ""         # Populated after close / summarization
    title: str = ""           # Human-readable semantic title (filename-safe)
    title_attempts: int = 0   # Budget guard: max 2 deterministic renames

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass
class SessionSearchResult:
    """A search hit inside a (possibly historical) session."""
    session_id: str
    score: float
    date: str = ""
    closed: bool = True
    excerpt: str = ""         # Rendered relevant excerpts (Markdown)
    summary: str = ""         # Session summary, if one exists
