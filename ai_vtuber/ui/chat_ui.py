"""AI VTuber - Chat UI Module

Provides text-based chat interface with typewriter effect.
"""

import logging
import pygame
import pygame.freetype
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ChatUI:
    """Chat interface with typewriter effect for AI responses."""

    def __init__(self, width: int, height: int, font_size: int = 14) -> None:
        self.width = width
        self.height = height
        self.font_size = font_size
        
        # Chat state
        self.input_text: str = ""
        self.input_active: bool = True
        self.cursor_visible: bool = True
        self.cursor_timer: float = 0.0
        
        # Message history
        self.messages: list[dict] = []  # [{"role": "user"/"ai", "text": "...", "time": ...}]
        self.max_messages: int = 10
        
        # Typewriter effect for AI responses
        self.typewriter_text: str = ""
        self.typewriter_target: str = ""
        self.typewriter_index: int = 0
        self.typewriter_speed: float = 0.03  # seconds per character
        self.typewriter_timer: float = 0.0
        self.is_typing: bool = False
        
        # UI dimensions
        self.input_box_height: int = 50
        self.input_box_padding: int = 15
        self.message_area_height: int = 200
        self.border_radius: int = 12
        
        # Colors
        self.bg_color = (30, 30, 40, 200)
        self.input_bg_color = (40, 40, 50, 230)
        self.text_color = (255, 255, 255)
        self.placeholder_color = (150, 150, 150)
        self.user_color = (100, 200, 255)
        self.ai_color = (200, 255, 150)
        self.border_color = (80, 80, 100)
        
        # Fonts
        self._font: Optional[pygame.freetype.Font] = None
        self._small_font: Optional[pygame.freetype.Font] = None
        
        # Callback for sending messages
        self.on_send_message: Optional[Callable[[str], None]] = None

    def init_fonts(self) -> None:
        """Initialize fonts after Pygame is initialized."""
        self._font = pygame.freetype.Font(None, self.font_size)
        self._small_font = pygame.freetype.Font(None, max(10, self.font_size - 2))

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle Pygame events for chat input.
        
        Returns:
            The message text if Enter was pressed, None otherwise.
        """
        if not self.input_active:
            return None
            
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                # Send message
                if self.input_text.strip():
                    message = self.input_text.strip()
                    self.add_message("user", message)
                    self.input_text = ""
                    return message
            elif event.key == pygame.K_BACKSPACE:
                # Delete character
                self.input_text = self.input_text[:-1]
            elif event.key <= 127:  # Printable ASCII
                # Add character
                char = chr(event.key)
                if len(self.input_text) < 200:  # Limit input length
                    self.input_text += char
        
        return None

    def add_message(self, role: str, text: str) -> None:
        """Add a message to the chat history."""
        self.messages.append({
            "role": role,
            "text": text,
            "time": time.time()
        })
        
        # Keep only last N messages
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        
        # Start typewriter effect for AI messages
        if role == "ai":
            self.start_typewriter(text)

    def start_typewriter(self, text: str) -> None:
        """Start typewriter effect for AI response."""
        self.typewriter_target = text
        self.typewriter_text = ""
        self.typewriter_index = 0
        self.typewriter_timer = 0.0
        self.is_typing = True

    def update(self, delta_time: float, current_response: str = "") -> None:
        """Update chat state (cursor blink, typewriter effect).
        
        Args:
            delta_time: Time since last frame in seconds
            current_response: Current AI response text to display with typewriter effect
        """
        # Update cursor blink
        self.cursor_timer += delta_time
        if self.cursor_timer >= 0.5:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0.0
        
        # Update typewriter effect for AI response
        if current_response and current_response != self.typewriter_target:
            # New response started
            self.start_typewriter(current_response)
        
        # Update typewriter effect
        if self.is_typing:
            self.typewriter_timer += delta_time
            if self.typewriter_timer >= self.typewriter_speed:
                if self.typewriter_index < len(self.typewriter_target):
                    self.typewriter_text += self.typewriter_target[self.typewriter_index]
                    self.typewriter_index += 1
                    self.typewriter_timer = 0.0
                else:
                    self.is_typing = False

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the chat UI on the given surface."""
        if self._font is None:
            return
        
        # Draw message area
        self._draw_message_area(surface)
        
        # Draw input box
        self._draw_input_box(surface)

    def _draw_message_area(self, surface: pygame.Surface) -> None:
        """Draw the message history area."""
        y_offset = self.height - self.input_box_height - self.message_area_height - 20
        
        # Background
        bg_rect = pygame.Rect(
            20, y_offset,
            self.width - 40, self.message_area_height
        )
        pygame.draw.rect(surface, self.bg_color, bg_rect, border_radius=self.border_radius)
        pygame.draw.rect(surface, self.border_color, bg_rect, width=2, border_radius=self.border_radius)
        
        # Draw messages
        y = y_offset + 15
        for msg in self.messages[-6:]:  # Show last 6 messages
            role = msg["role"]
            text = msg["text"]
            
            # Color based on role
            color = self.user_color if role == "user" else self.ai_color
            prefix = "You: " if role == "user" else "AI: "
            
            # For AI messages, show typewriter effect
            if role == "ai" and self.is_typing:
                display_text = self.typewriter_text
            else:
                display_text = text
            
            # Word wrap
            lines = self._wrap_text(prefix + display_text, self.width - 80)
            for line in lines[:3]:  # Max 3 lines per message
                self._small_font.render_to(surface, (35, y), line, color)
                y += 18
            
            y += 8  # Space between messages
            
            if y > y_offset + self.message_area_height - 20:
                break

    def _draw_input_box(self, surface: pygame.Surface) -> None:
        """Draw the text input box at the bottom."""
        y_offset = self.height - self.input_box_height - 10
        
        # Background
        bg_rect = pygame.Rect(
            20, y_offset,
            self.width - 40, self.input_box_height
        )
        pygame.draw.rect(surface, self.input_bg_color, bg_rect, border_radius=self.border_radius)
        
        # Border (highlight if active)
        border_color = (100, 150, 255) if self.input_active else self.border_color
        pygame.draw.rect(surface, border_color, bg_rect, width=2, border_radius=self.border_radius)
        
        # Text or placeholder
        if self.input_text:
            text_x = 35
            self._font.render_to(surface, (text_x, y_offset + 15), self.input_text, self.text_color)
            
            # Cursor
            if self.input_active and self.cursor_visible:
                cursor_x = text_x + len(self.input_text) * 8  # Approximate
                pygame.draw.line(
                    surface, self.text_color,
                    (cursor_x, y_offset + 15),
                    (cursor_x, y_offset + 35),
                    width=2
                )
        else:
            # Placeholder text
            placeholder = "Type a message... (Enter to send, Tab to toggle focus)"
            self._font.render_to(surface, (35, y_offset + 15), placeholder, self.placeholder_color)
        
        # Hint text
        hint = "Press Enter to send | Tab to toggle chat | Voice input also active"
        self._small_font.render_to(surface, (35, y_offset + 35), hint, (120, 120, 140))

    def _wrap_text(self, text: str, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        if not self._small_font:
            return [text]
        
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            # Approximate width check (8 pixels per character)
            if len(test_line) * 8 > max_width:
                if current_line:
                    lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]

    def get_input_text(self) -> str:
        """Get the current input text."""
        return self.input_text

    def clear_input(self) -> None:
        """Clear the input text."""
        self.input_text = ""

    def set_input_active(self, active: bool) -> None:
        """Set whether the input box is active."""
        self.input_active = active
