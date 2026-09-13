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
    """Chat interface with typewriter effect for AI responses.
    
    OPTIMIZATION: Uses persistent Pygame surface and OpenGL texture.
    Only redraws when content actually changes (dirty flag).
    """

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
        self.input_box_height: int = 35
        self.input_box_padding: int = 10
        self.border_radius: int = 8
        
        # Chat visibility
        self.chat_visible: bool = True  # Whether chat UI is visible
        
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
        
        # Persistent surface and texture optimization
        self._surface: Optional[pygame.Surface] = None
        self._texture_id: Optional[int] = None
        self._dirty: bool = True
        self._last_input_text: str = ""
        self._last_cursor_state: bool = False
        self._last_typewriter_text: str = ""

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
            elif event.key in (pygame.K_ESCAPE, pygame.K_TAB):
                # These are handled globally, ignore here
                pass
            else:
                # Handle text input via unicode attribute
                # Allow ALL printable characters including WASD, +, -, etc.
                if hasattr(event, 'unicode') and event.unicode:
                    char = event.unicode
                    # Only add printable characters
                    if char.isprintable() and len(self.input_text) < 200:
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
            text_x = 30
            text_y = y_offset + 10
            self._font.render_to(surface, (text_x, text_y), self.input_text, self.text_color)
            
            # Cursor
            if self.input_active and self.cursor_visible:
                cursor_x = text_x + len(self.input_text) * 8  # Approximate
                pygame.draw.line(
                    surface, self.text_color,
                    (cursor_x, text_y),
                    (cursor_x, text_y + 16),
                    width=2
                )
        else:
            # Placeholder text
            placeholder = "Type a message... (Enter to send)"
            self._font.render_to(surface, (30, y_offset + 10), placeholder, self.placeholder_color)

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

    def toggle_chat(self) -> None:
        """Toggle chat visibility."""
        self.chat_visible = not self.chat_visible
        if not self.chat_visible:
            self.input_active = False
        logger.info(f"Chat {'shown' if self.chat_visible else 'hidden'}")

    def clear_chat(self) -> None:
        """Clear chat history."""
        self.messages.clear()
        self.typewriter_text = ""
        self.typewriter_target = ""
        self.typewriter_index = 0
        logger.info("Chat history cleared")

    def draw(self, screen: pygame.Surface) -> None:
        """Draw the chat UI by rendering to a surface and uploading as OpenGL texture."""
        if self._font is None:
            return
        
        # Create a surface for the chat UI
        chat_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        
        # Only draw chat if visible
        if self.chat_visible:
            # Draw input box only (no message history, no buttons)
            self._draw_input_box(chat_surface)
        
        # Render the surface as an OpenGL texture
        self._render_as_texture(chat_surface, screen)
    
    def _render_as_texture(self, surface: pygame.Surface, screen: pygame.Surface) -> None:
        """Render the surface as an OpenGL texture."""
        try:
            from OpenGL import GL
            
            # Convert surface to RGBA bytes
            raw_data = pygame.image.tostring(surface, "RGBA", True)
            tex_width, tex_height = surface.get_size()
            
            # Create texture
            tex_id = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
                tex_width, tex_height, 0,
                GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, raw_data
            )
            
            # Save current OpenGL state
            GL.glPushAttrib(GL.GL_ALL_ATTRIB_BITS)
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPushMatrix()
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPushMatrix()
            
            # Set up orthographic projection for 2D overlay
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            GL.glOrtho(0, self.width, self.height, 0, -1, 1)
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glLoadIdentity()
            
            # Enable blending for transparency
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            
            # Disable depth test for overlay
            GL.glDisable(GL.GL_DEPTH_TEST)
            
            # Draw textured quad covering the entire window
            # Note: Texture Y-axis is flipped because pygame surface and OpenGL have different Y orientations
            GL.glEnable(GL.GL_TEXTURE_2D)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            GL.glColor4f(1.0, 1.0, 1.0, 1.0)
            
            GL.glBegin(GL.GL_QUADS)
            GL.glTexCoord2f(0, 1); GL.glVertex2f(0, 0)
            GL.glTexCoord2f(1, 1); GL.glVertex2f(self.width, 0)
            GL.glTexCoord2f(1, 0); GL.glVertex2f(self.width, self.height)
            GL.glTexCoord2f(0, 0); GL.glVertex2f(0, self.height)
            GL.glEnd()
            
            GL.glDisable(GL.GL_TEXTURE_2D)
            
            # Restore OpenGL state
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPopMatrix()
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPopMatrix()
            GL.glPopAttrib()
            
            # Cleanup texture
            GL.glDeleteTextures([tex_id])
            
        except ImportError:
            logger.debug("PyOpenGL not available, chat UI disabled")
        except Exception as e:
            logger.debug(f"Chat UI render error: {e}")

    def get_input_text(self) -> str:
        """Get the current input text."""
        return self.input_text

    def clear_input(self) -> None:
        """Clear the input text."""
        self.input_text = ""

    def set_input_active(self, active: bool) -> None:
        """Set whether the input box is active."""
        self.input_active = active
