"""AI VTuber - Conversation History Manager"""

import logging
from typing import Optional, List
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)


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
    max_context: int = 64000
    reserved_output_tokens: int = 2000
    _messages: list[Message] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using character-based heuristic (~4 chars per token)."""
        return len(text) // 4

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

    def get_messages_for_llm(self, visual_context: Optional[str] = None) -> list[dict[str, str]]:
        """Get messages formatted for LLM API call.
        
        Args:
            visual_context: Optional visual context from screen vision system.
                           If provided, will be appended to the system prompt.
        """
        with self._lock:
            # Build combined system prompt: technical instructions + soul/personality
            combined_system = self.system_prompt.strip()
            if self.soul_prompt:
                combined_system = f"{combined_system}\n\n{self.soul_prompt.strip()}"
            
            # Append visual context if available (from screen vision system)
            if visual_context:
                combined_system = f"{combined_system}\n\n=== CURRENT SCREEN CONTEXT ===\n{visual_context}"
            
            # Estimate tokens for system prompt
            system_tokens = self._estimate_tokens(combined_system) if combined_system else 0
            
            # Calculate token budget available for messages
            available_tokens = self.max_context - self.reserved_output_tokens - system_tokens
            
            # Walk messages from most-recent to oldest, accumulating tokens
            # Stop when we exceed the available token budget
            accumulated_message_tokens = 0
            messages_to_include = []
            
            for msg in reversed(self._messages):
                if msg.role == "system":
                    continue
                
                msg_tokens = self._estimate_tokens(msg.content)
                
                if accumulated_message_tokens + msg_tokens <= available_tokens:
                    messages_to_include.append(msg)
                    accumulated_message_tokens += msg_tokens
                else:
                    # Message would exceed budget, skip it (and all older ones)
                    logger.debug(f"Token budget exceeded, dropping {len(self._messages) - len(messages_to_include)} older message(s)")
                    break
            
            # Reverse back to chronological order
            messages_to_include.reverse()
            
            # Build final message list
            messages = []
            if combined_system:
                messages.append({"role": "system", "content": combined_system})
            for msg in messages_to_include:
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
