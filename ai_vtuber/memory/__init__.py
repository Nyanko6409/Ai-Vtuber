"""Memory package for AI VTuber.

Single authoritative memory system:

- MemoryManager  : sessions + long-term user/Airi memory (one facade)
- SessionStore   : crash-safe Markdown session persistence
- retrieval      : BM25 session search + past-reference intent detection
- consolidation  : summary -> extraction -> dedupe-aware md merge
"""

from .models import Session, SessionMessage, SessionSearchResult
from .session import SessionStore
from .manager import MemoryManager

__all__ = [
    "MemoryManager",
    "SessionStore",
    "Session",
    "SessionMessage",
    "SessionSearchResult",
]
