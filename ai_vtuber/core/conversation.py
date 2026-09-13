"""AI VTuber - Conversation History Manager"""

from typing import Optional
from dataclasses import dataclass, field
import threading


@dataclass
class Message:
    """A single conversation message."""
    role: str  # "system", "user", "assistant"
    content: str
    emotion: Optional[str] = None  # Parsed emotion tag for assistant messages


@dataclass
class ConversationHistory:
    """Thread-safe conversation history with configurable limit."""
    max_messages: int = 10
    system_prompt: str = ""
    soul_prompt: str = ""  # Personality/character definition from soul.md
    _messages: list[Message] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_message(self, role: str, content: str, emotion: Optional[str] = None) -> None:
        """Add a message to history."""
        with self._lock:
            self._messages.append(Message(role=role, content=content, emotion=emotion))
            # Trim history if needed (keep system message + recent messages)
            self._trim_history()

    def set_soul_prompt(self, soul_prompt: str) -> None:
        """Update the soul prompt (thread-safe)."""
        with self._lock:
            self.soul_prompt = soul_prompt

    def _trim_history(self) -> None:
        """Trim history to max_messages (excluding system prompt)."""
        non_system = [m for m in self._messages if m.role != "system"]
        if len(non_system) > self.max_messages:
            # Keep the most recent messages
            excess = len(non_system) - self.max_messages
            removed = 0
            new_messages = []
            for msg in self._messages:
                if msg.role == "system":
                    new_messages.append(msg)
                elif removed < excess:
                    removed += 1
                else:
                    new_messages.append(msg)
            self._messages = new_messages

    def get_messages_for_llm(self) -> list[dict[str, str]]:
        """Get messages formatted for LLM API call."""
        with self._lock:
            messages = []
            # Build combined system prompt: technical instructions + soul/personality
            combined_system = self.system_prompt.strip()
            if self.soul_prompt:
                combined_system = f"{combined_system}\n\n{self.soul_prompt.strip()}"
            
            if combined_system:
                messages.append({"role": "system", "content": combined_system})
            for msg in self._messages:
                if msg.role == "system":
                    continue
                messages.append({"role": msg.role, "content": msg.content})
            return messages

    def clear(self) -> None:
        """Clear all messages."""
        with self._lock:
            self._messages.clear()

    @property
    def last_user_message(self) -> Optional[str]:
        """Get the last user message."""
        with self._lock:
            for msg in reversed(self._messages):
                if msg.role == "user":
                    return msg.content
            return None

    @property
    def message_count(self) -> int:
        """Get number of messages in history."""
        with self._lock:
            return len(self._messages)
