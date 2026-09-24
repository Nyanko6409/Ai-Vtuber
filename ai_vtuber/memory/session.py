"""AI VTuber - Session store.

One session per application boot.  Every message is appended to the
session's Markdown file *as it happens* (flush + fsync), so a crash never
loses more than the in-flight exchange.  The human-readable files under
``data/sessions/`` are the single source of truth - nothing important is
kept only in RAM.

File format (one file per session)::

    # Session: <session_id>
    Status: open|closed
    Started: YYYY-MM-DD HH:MM:SS

    ## User
    [HH:MM:SS]
    text...

    ## Airi
    [HH:MM:SS] [emotion]
    text...

    <!-- SUMMARY -->
    ...generated summary...
    <!-- /SUMMARY -->
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import Session, SessionMessage

logger = logging.getLogger(__name__)

_ROLE_HEADERS = {"user": "## User", "assistant": "## Airi"}
_HEADER_TO_ROLE = {v: k for k, v in _ROLE_HEADERS.items()}

_SUMMARY_OPEN = "<!-- SUMMARY -->"
_SUMMARY_CLOSE = "<!-- /SUMMARY -->"


class SessionStore:
    """Crash-safe storage for conversation sessions (Markdown files)."""

    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._current: Optional[Session] = None
        self._current_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # creation / lifecycle
    # ------------------------------------------------------------------

    def generate_session_id(self, now: Optional[datetime] = None) -> str:
        """Return a unique, not-yet-created session id.

        Format: ``session_YYYY-MM-DD_HH-MM-SS``.  If a file with that name
        already exists (rapid restarts within one second), a numeric suffix
        is added so previous sessions are NEVER overwritten.
        """
        with self._lock:
            return self._unique_session_id(now or datetime.now())

    def create_session(self) -> Session:
        """Create (and activate) a brand-new session. Never overwrites."""
        with self._lock:
            now = datetime.now()
            session_id = self._unique_session_id(now)
            path = self._path_for(session_id)
            header = (
                f"# Session: {session_id}\n"
                f"Status: open\n"
                f"Started: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )
            # 'x' mode would fail on collision; we already ensured uniqueness,
            # but write atomically anyway.
            path.write_text(header, encoding="utf-8")
            self._current = Session(
                session_id=session_id,
                started=now.strftime("%Y-%m-%d %H:%M:%S"),
                closed=False,
            )
            self._current_path = path
            logger.info(f"Created session {session_id} at {path}")
            return self._current

    def _unique_session_id(self, now: datetime) -> str:
        base = f"session_{now.strftime('%Y-%m-%d_%H-%M-%S')}"
        candidate = base
        n = 1
        while self._path_for(candidate).exists():
            candidate = f"{base}_{n}"
            n += 1
        return candidate

    def get_current_session(self) -> Optional[Session]:
        """Return the active session, creating one on first use."""
        with self._lock:
            if self._current is None:
                # Recover an interrupted session if one exists, else start fresh.
                open_sessions = [
                    s for s in (self.load_session(sid) for sid in self.list_sessions())
                    if s is not None and not s.closed
                ]
                if open_sessions:
                    latest = max(open_sessions, key=lambda s: s.started)
                    self._current = latest
                    self._current_path = self._path_for(latest.session_id)
                    logger.info(
                        f"Recovered interrupted session {latest.session_id} "
                        f"({latest.message_count} messages)"
                    )
                else:
                    self.create_session()
            return self._current

    def append_message(self, role: str, content: str,
                       emotion: Optional[str] = None) -> bool:
        """Persist one message to the current session immediately.

        Crash safety: the append is flushed and fsynced before returning,
        so the transcript survives power loss / hard kills.
        """
        if role not in _ROLE_HEADERS:
            raise ValueError(f"Unsupported session message role: {role!r}")
        with self._lock:
            session = self.get_current_session()
            assert session is not None and self._current_path is not None
            now = datetime.now().strftime("%H:%M:%S")
            tag = f"[{now}]"
            if emotion:
                tag += f" [{emotion}]"
            block = f"{_ROLE_HEADERS[role]}\n{tag}\n{content.strip()}\n\n"
            try:
                with open(self._current_path, "a", encoding="utf-8") as f:
                    f.write(block)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error(f"Failed to persist session message: {e}")
                return False
            session.messages.append(
                SessionMessage(role=role, content=content.strip(),
                               timestamp=now, emotion=emotion)
            )
            return True

    def close_session(self, session_id: Optional[str] = None) -> bool:
        """Mark a session closed (default: the current one)."""
        with self._lock:
            sid = session_id or (self._current.session_id if self._current else None)
            if sid is None:
                return False
            path = self._path_for(sid)
            if not path.exists():
                return False
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"^Status:\s*open\s*$", "Status: closed",
                          text, count=1, flags=re.MULTILINE)
            closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if "Closed:" not in text.split(_SUMMARY_OPEN)[0]:
                text = text.replace("\n\n", "\n\n", 1)
                # insert Closed: line right after Status line
                text = re.sub(
                    r"(Status:\s*closed\s*\n)",
                    rf"\1Closed: {closed_at}\n",
                    text, count=1,
                )
            self._atomic_write(path, text)
            if self._current and self._current.session_id == sid:
                self._current.closed = True
                self._current = None
                self._current_path = None
            logger.info(f"Closed session {sid}")
            return True

    def is_open(self, session_id: str) -> bool:
        s = self.load_session(session_id)
        return s is not None and not s.closed

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def list_sessions(self) -> List[str]:
        """All session ids, oldest first."""
        if not self.sessions_dir.exists():
            return []
        names = [p.stem for p in self.sessions_dir.glob("session_*.md")]
        return sorted(names)

    def session_path(self, session_id: str) -> Path:
        return self._path_for(session_id)

    def load_session(self, session_id: str) -> Optional[Session]:
        path = self._path_for(session_id)
        if not path.exists():
            return None
        try:
            return self._parse(path.read_text(encoding="utf-8"), session_id)
        except Exception as e:  # corrupt file should never crash the app
            logger.error(f"Failed to parse session {session_id}: {e}")
            return Session(session_id=session_id, closed=True)

    def recent_sessions(self, limit: int = 3, exclude_current: bool = True) -> List[Session]:
        out: List[Session] = []
        ids = self.list_sessions()
        current_id = self._current.session_id if self._current else None
        for sid in reversed(ids):
            if exclude_current and sid == current_id:
                continue
            s = self.load_session(sid)
            if s is not None:
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def save_summary(self, session_id: str, summary: str) -> bool:
        """Write/replace the summary block inside a session file."""
        path = self._path_for(session_id)
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8")
        block = f"{_SUMMARY_OPEN}\n{summary.strip()}\n{_SUMMARY_CLOSE}\n"
        pattern = re.compile(
            re.escape(_SUMMARY_OPEN) + r".*?" + re.escape(_SUMMARY_CLOSE),
            re.DOTALL,
        )
        if pattern.search(text):
            text = pattern.sub(lambda _m: block, text, count=1)
        else:
            text = text.rstrip() + "\n\n" + block
        self._atomic_write(path, text)
        if self._current and self._current.session_id == session_id:
            self._current.summary = summary
        return True

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _path_for(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.md"

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def _parse(text: str, session_id: str) -> Session:
        status_closed = bool(re.search(r"^Status:\s*closed", text, re.MULTILINE))
        m = re.search(r"^Started:\s*(.+)$", text, re.MULTILINE)
        started = m.group(1).strip() if m else ""

        summary = ""
        sm = re.search(
            re.escape(_SUMMARY_OPEN) + r"(.*?)" + re.escape(_SUMMARY_CLOSE),
            text, re.DOTALL,
        )
        if sm:
            summary = sm.group(1).strip()
            body = text[: sm.start()] + text[sm.end():]
        else:
            body = text

        messages: List[SessionMessage] = []
        current_header = None
        buf: List[str] = []
        stamp = ""
        emotion = None

        def flush():
            if current_header and "".join(buf).strip():
                messages.append(SessionMessage(
                    role=_HEADER_TO_ROLE[current_header],
                    content="".join(buf).strip(),
                    timestamp=stamp,
                    emotion=emotion,
                ))

        lines = body.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped in _HEADER_TO_ROLE:
                flush()
                current_header = stripped
                buf = []
                stamp = ""
                emotion = None
                # next line may carry [time] [emotion] tags
                if i + 1 < len(lines):
                    tag_m = re.match(r"^\s*(?:\[(\d{2}:\d{2}:\d{2})\])?\s*(?:\[([\w-]+)\])?\s*$",
                                      lines[i + 1])
                    rest = lines[i + 1].strip()
                    if rest.startswith("["):
                        tm = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]", rest)
                        em = re.search(r"\[([\w-]+)\]\s*$", rest)
                        if tm or em:
                            stamp = tm.group(1) if tm else ""
                            emotion = em.group(1) if em else None
                            i += 1
                            continue
            elif current_header is not None:
                if stripped.startswith("# ") or stripped.startswith("Status:") \
                        or stripped.startswith("Started:") or stripped.startswith("Closed:"):
                    flush()
                    current_header = None
                    buf = []
                else:
                    buf.append(line + "\n")
            i += 1
        flush()

        return Session(session_id=session_id, started=started,
                       closed=status_closed, messages=messages, summary=summary)
