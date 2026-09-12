"""AI VTuber - Pygame UI Module"""

import logging
import time
import pygame
import pygame.freetype
from typing import Optional

from core.state import State

logger = logging.getLogger(__name__)

# State display colors
STATE_COLORS = {
    State.IDLE: (100, 200, 100),       # Green
    State.LISTENING: (100, 150, 255),   # Blue
    State.TRANSCRIBING: (200, 200, 100), # Yellow
    State.THINKING: (255, 180, 50),     # Orange
    State.SPEAKING: (100, 255, 150),    # Light green
    State.ERROR: (255, 80, 80),         # Red
}

STATE_LABELS = {
    State.IDLE: "● IDLE - Waiting for speech",
    State.LISTENING: "● LISTENING - Recording...",
    State.TRANSCRIBING: "● TRANSCRIBING - Processing speech...",
    State.THINKING: "● THINKING - Generating response...",
    State.SPEAKING: "● SPEAKING - Talking...",
    State.ERROR: "✖ ERROR",
}

EMOTION_EMOJI = {
    "neutral": "😐",
    "happy": "😊",
    "excited": "😄",
    "thinking": "🤔",
    "surprised": "😲",
    "sad": "😢",
    "angry": "😠",
    "sleepy": "😴",
}


class PygameUI:
    """Pygame-based UI for the VTuber application.
    
    Displays:
    - Live2D avatar (via OpenGL)
    - Status bar with state indicator
    - Current transcription
    - Current response
    - FPS/debug information
    """

    def __init__(self, config: dict) -> None:
        self.width: int = config["avatar"]["window_width"]
        self.height: int = config["avatar"]["window_height"]
        self.fps: int = config["avatar"]["fps"]
        self.show_fps: bool = config["ui"]["show_fps"]
        self.show_debug: bool = config["ui"]["show_debug"]
        self.bg_color: tuple = tuple(config["ui"]["background_color"])
        self.text_color: tuple = tuple(config["ui"]["text_color"])
        self.font_size: int = config["ui"]["font_size"]
        self.status_bar_height: int = config["ui"]["status_bar_height"]

        self._screen = None
        self._font = None
        self._small_font = None
        self._clock = None
        self._fps_value: float = 0.0
        self._frame_count: int = 0
        self._fps_timer: float = 0.0

    def init(self) -> None:
        """Initialize Pygame and create window."""
        pygame.init()
        pygame.freetype.init()

        # Create OpenGL-capable window
        self._screen = pygame.display.set_mode(
            (self.width, self.height),
            pygame.DOUBLEBUF | pygame.OPENGL | pygame.RESIZABLE
        )
        pygame.display.set_caption("AI VTuber")

        # Initialize fonts
        self._font = pygame.freetype.Font(None, self.font_size)
        self._small_font = pygame.freetype.Font(None, max(10, self.font_size - 2))

        self._clock = pygame.time.Clock()
        logger.info(f"Pygame UI initialized ({self.width}x{self.height} @ {self.fps}fps)")

    def handle_events(self, avatar=None) -> bool:
        """Handle Pygame events.
        
        Args:
            avatar: Optional Live2DAvatar instance for zoom/move controls
            
        Returns:
            False if window was closed, True otherwise.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.VIDEORESIZE:
                self.width = event.w
                self.height = event.h
                self._screen = pygame.display.set_mode(
                    (self.width, self.height),
                    pygame.DOUBLEBUF | pygame.OPENGL | pygame.RESIZABLE
                )
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_f:
                    self.show_fps = not self.show_fps
                elif event.key == pygame.K_d:
                    self.show_debug = not self.show_debug
                # Zoom controls
                elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS:
                    if avatar:
                        avatar.zoom_in(0.2)
                elif event.key == pygame.K_MINUS:
                    if avatar:
                        avatar.zoom_out(0.2)
                elif event.key == pygame.K_r:
                    if avatar:
                        avatar.reset_zoom()
                # Movement controls
                elif event.key == pygame.K_UP or event.key == pygame.K_w:
                    if avatar:
                        avatar.move_up(20.0)
                elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                    if avatar:
                        avatar.move_down(20.0)
                elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                    if avatar:
                        avatar.move_left(20.0)
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                    if avatar:
                        avatar.move_right(20.0)
        return True

    def begin_frame(self) -> None:
        """Begin a new frame - clear buffer and update timing."""
        # Clear the OpenGL color buffer
        try:
            from OpenGL import GL
            GL.glClearColor(
                self.bg_color[0] / 255.0,
                self.bg_color[1] / 255.0,
                self.bg_color[2] / 255.0,
                1.0
            )
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        except ImportError:
            # PyOpenGL not available, skip clearing
            pass
        except Exception as e:
            logger.debug(f"OpenGL clear failed: {e}")

        # Update FPS counter
        delta = self._clock.tick(self.fps) / 1000.0
        self._frame_count += 1
        self._fps_timer += delta
        if self._fps_timer >= 1.0:
            self._fps_value = self._frame_count / self._fps_timer
            self._frame_count = 0
            self._fps_timer = 0.0

    def draw_overlay(self, status: dict, error_msg: Optional[str] = None) -> None:
        """Draw UI overlay on top of the avatar.

        Renders text using Pygame freetype onto a transparent surface,
        then uploads it as an OpenGL texture for display.

        Args:
            status: Status dict from App.get_status()
            error_msg: Optional error message to display.
        """
        # Create a transparent overlay surface
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        # Draw status bar at top
        self._draw_status_bar(overlay, status)

        # Draw FPS/debug info
        if self.show_fps:
            self._draw_fps(overlay)

        # Draw compact error notification (if any)
        if error_msg:
            self._draw_error(overlay, error_msg)
        
        # Draw avatar controls help
        self._draw_avatar_controls(overlay)

        # Render overlay to screen as OpenGL texture
        self._render_overlay_texture(overlay)

    def _draw_status_bar(self, surface: pygame.Surface, status: dict) -> None:
        """Draw the status bar at the top of the screen."""
        # Background
        bar_rect = pygame.Rect(0, 0, self.width, self.status_bar_height)
        pygame.draw.rect(surface, (20, 20, 30, 200), bar_rect)

        # State indicator
        state_name = status.get("state", "IDLE")
        try:
            state = State[state_name]
        except KeyError:
            state = State.IDLE

        color = STATE_COLORS.get(state, (200, 200, 200))
        label = STATE_LABELS.get(state, f"● {state_name}")

        # Add emotion
        emotion = status.get("emotion", "neutral")
        emoji = EMOTION_EMOJI.get(emotion, "😐")
        full_label = f"{label}  {emoji}"

        self._font.render_to(surface, (10, 8), full_label, color)

    def _draw_wrapped_text(self, surface: pygame.Surface, text: str,
                           pos: tuple, max_width: int, color: tuple) -> None:
        """Draw text with word wrapping."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            # Approximate width check
            if len(test_line) * 7 > max_width:  # Rough char width estimate
                if current_line:
                    lines.append(current_line)
                current_line = word
            else:
                current_line = test_line

        if current_line:
            lines.append(current_line)

        y = pos[1]
        for line in lines[:5]:  # Max 5 lines
            self._small_font.render_to(surface, (pos[0], y), line, color)
            y += 16

    def _draw_fps(self, surface: pygame.Surface) -> None:
        """Draw FPS counter."""
        fps_text = f"FPS: {self._fps_value:.1f}"
        self._small_font.render_to(
            surface, (self.width - 80, 10),
            fps_text, (180, 180, 180)
        )

    def _draw_error(self, surface: pygame.Surface, error_msg: str) -> None:
        """Draw compact error notification at the top."""
        # Take first line only for compact display
        first_line = error_msg.split('\n')[0]
        # Truncate if too long
        if len(first_line) > 60:
            first_line = first_line[:57] + "..."
        
        # Compact error bar at top below status bar
        bar_height = 30
        bg_rect = pygame.Rect(0, self.status_bar_height, self.width, bar_height)
        pygame.draw.rect(surface, (80, 20, 20, 230), bg_rect)
        
        # Error text
        error_text = f"⚠ {first_line}"
        self._small_font.render_to(
            surface,
            (10, self.status_bar_height + 8),
            error_text, (255, 150, 150)
        )

    def _draw_avatar_controls(self, surface: pygame.Surface) -> None:
        """Draw avatar control instructions."""
        controls_text = [
            "🖱️ Avatar Controls:",
            "  Left-click + drag: Move avatar",
            "  Scroll wheel: Zoom in/out",
        ]
        
        # Draw in bottom-right corner
        x = self.width - 220
        y = self.height - 80
        
        # Semi-transparent background
        bg_rect = pygame.Rect(x - 5, y - 5, 220, 75)
        pygame.draw.rect(surface, (20, 20, 30, 180), bg_rect, border_radius=5)
        
        # Draw text
        for i, line in enumerate(controls_text):
            color = (200, 200, 200) if i == 0 else (180, 180, 180)
            self._small_font.render_to(surface, (x, y + i * 18), line, color)

    def _render_overlay_texture(self, surface: pygame.Surface) -> None:
        """Render the overlay surface as an OpenGL texture.

        Uses OpenGL to draw the Pygame surface as a textured quad
        in an orthographic 2D projection over the 3D scene.
        """
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
            # PyOpenGL not available, skip overlay rendering
            logger.debug("PyOpenGL not available, overlay disabled")
        except Exception as e:
            logger.debug(f"Overlay render error: {e}")

    def end_frame(self) -> None:
        """End the current frame - swap buffers."""
        pygame.display.flip()

    def get_mouse_pos(self) -> tuple[int, int]:
        """Get current mouse position."""
        return pygame.mouse.get_pos()

    def cleanup(self) -> None:
        """Clean up Pygame resources."""
        pygame.freetype.quit()
        pygame.quit()
        logger.info("Pygame UI cleaned up")
