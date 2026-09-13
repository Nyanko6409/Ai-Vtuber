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
    
    OPTIMIZATION: Uses persistent OpenGL texture for UI overlay.
    Texture is only updated when content changes (dirty flag).
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
        
        # Persistent UI texture optimization
        self._overlay_surface: Optional[pygame.Surface] = None
        self._overlay_texture_id: Optional[int] = None
        self._overlay_dirty: bool = True
        self._last_status_hash: int = 0
        self._last_error_msg: Optional[str] = None

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
        
        # Create persistent overlay surface
        self._overlay_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        
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
                # No keyboard avatar controls - mouse only
        return True

    def begin_frame(self) -> None:
        """Begin a new frame - clear buffer and setup matrices for 3D rendering."""
        # Clear the OpenGL color buffer and setup matrices
        try:
            from OpenGL import GL
            
            # Setup projection matrix for Live2D coordinate system
            # Live2D uses normalized device coordinates (-1 to 1)
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            # Use orthographic projection matching window size
            # This creates a coordinate system where (0,0) is center of screen
            GL.glOrtho(-self.width/2, self.width/2, -self.height/2, self.height/2, -1000, 1000)
            
            # Setup modelview matrix - reset to identity for clean transform state
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glLoadIdentity()
            
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
        
        # NOTE: Do NOT reset avatar transforms here - they must persist across frames
        # The avatar's draw() method will apply its own zoom/offset via projection matrix

    def draw_overlay(self, status: dict, error_msg: Optional[str] = None) -> None:
        """Draw UI overlay on top of the avatar.

        Renders text using Pygame freetype onto a persistent transparent surface,
        then uploads it as an OpenGL texture for display.
        
        OPTIMIZATION: Only redraws and re-uploads texture when content changes.
        Uses dirty flag to avoid redundant work.

        Args:
            status: Status dict from App.get_status()
            error_msg: Optional error message to display.
        """
        # Check if content has changed (use hash for quick comparison)
        status_hash = hash(
            (status.get("state", ""), status.get("emotion", ""), 
             status.get("response", "")[:100], status.get("transcription", "")[:100])
        )
        
        # Also check if FPS/debug visibility changed
        fps_dirty = self.show_fps or self.show_debug
        
        # Check if we need to redraw
        content_changed = (
            self._overlay_surface is None or
            status_hash != self._last_status_hash or
            error_msg != self._last_error_msg or
            self._overlay_dirty
        )
        
        if not content_changed:
            # Content unchanged, just render existing texture
            self._render_existing_texture()
            return
        
        # Mark dirty for next frame if FPS is shown (it changes every second)
        if self.show_fps:
            self._overlay_dirty = True
        
        # Redraw overlay to persistent surface
        self._overlay_surface.fill((0, 0, 0, 0))  # Clear with transparency
        
        # Draw status bar at top
        self._draw_status_bar(self._overlay_surface, status)

        # Draw FPS/debug info
        if self.show_fps:
            self._draw_fps(self._overlay_surface)

        # Draw compact error notification (if any)
        if error_msg:
            self._draw_error(self._overlay_surface, error_msg)
        
        # Draw avatar controls help
        self._draw_avatar_controls(self._overlay_surface)
        
        # Update tracking
        self._last_status_hash = status_hash
        self._last_error_msg = error_msg
        self._overlay_dirty = False

        # Render overlay to screen as OpenGL texture
        self._render_overlay_texture(self._overlay_surface)

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
        
        # Add debug info if enabled
        if self.show_debug and hasattr(self, '_avatar'):
            debug_y = self.height - 40
            debug_text = f"Avatar: zoom={self._avatar.zoom:.2f}, pos=({self._avatar.offset_x:.0f}, {self._avatar.offset_y:.0f})"
            self._small_font.render_to(surface, (10, debug_y), debug_text, (255, 255, 100))

    def _render_overlay_texture(self, surface: pygame.Surface) -> None:
        """Render the overlay surface as an OpenGL texture.

        Uses OpenGL to draw the Pygame surface as a textured quad
        in an orthographic 2D projection over the 3D scene.
        
        OPTIMIZATION: Creates persistent texture on first call,
        then updates it with glTexSubImage2D on subsequent calls.
        """
        try:
            from OpenGL import GL

            # Convert surface to RGBA bytes
            raw_data = pygame.image.tostring(surface, "RGBA", True)
            tex_width, tex_height = surface.get_size()

            # Create texture on first use
            if self._overlay_texture_id is None:
                self._overlay_texture_id = GL.glGenTextures(1)
            
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._overlay_texture_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            
            # Upload texture data
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
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._overlay_texture_id)
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

            # NOTE: Do NOT delete texture - reuse it next frame

        except ImportError:
            # PyOpenGL not available, skip overlay rendering
            logger.debug("PyOpenGL not available, overlay disabled")
        except Exception as e:
            logger.debug(f"Overlay render error: {e}")
    
    def _render_existing_texture(self) -> None:
        """Render the existing cached texture without re-uploading.
        
        OPTIMIZATION: Skips CPU->GPU upload when content hasn't changed.
        """
        if self._overlay_texture_id is None:
            return
            
        try:
            from OpenGL import GL

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

            # Draw textured quad using cached texture
            GL.glEnable(GL.GL_TEXTURE_2D)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._overlay_texture_id)
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

        except ImportError:
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
        # Clean up persistent OpenGL texture
        if self._overlay_texture_id is not None:
            try:
                from OpenGL import GL
                GL.glDeleteTextures([self._overlay_texture_id])
            except Exception:
                pass
            self._overlay_texture_id = None
        
        pygame.freetype.quit()
        pygame.quit()
        logger.info("Pygame UI cleaned up")
