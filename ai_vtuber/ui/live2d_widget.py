"""AI VTuber - Live2D OpenGL Widget

Provides an OpenGL widget for rendering Live2D avatars with mouse interaction support.
"""

import logging
from typing import Optional

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent

logger = logging.getLogger("ai_vtuber")


class Live2DGLWidget(QOpenGLWidget):
    """OpenGL widget for rendering Live2D avatar.
    
    This widget provides an OpenGL context for the Live2D renderer
    and handles mouse interactions for avatar positioning.
    """
    
    # Signals for mouse events to be handled by the app
    mouse_pressed = Signal(int, int)  # x, y
    mouse_released = Signal(int, int)
    mouse_moved = Signal(int, int)  # x, y
    mouse_dragged = Signal(int, int)  # delta_x, delta_y
    wheel_scrolled = Signal(bool)  # True for zoom in, False for zoom out
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_mouse_pos: Optional[QPointF] = None
        self._is_dragging = False
        self.setMinimumSize(400, 300)
        self._render_callback = None
        # Default clear color (black)
        self._clear_color = (0.0, 0.0, 0.0, 1.0)
        # Set size policy to expand
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Enable mouse tracking for smooth eye movement
        self.setMouseTracking(True)
        # Note: background is now set in QtMainWindow._setup_ui() for consistency
        
    def update_clear_color(self, r: float, g: float, b: float, a: float = 1.0):
        """Update the OpenGL clear color."""
        self._clear_color = (r, g, b, a)
        # Only call glClearColor if OpenGL context is already initialized
        try:
            import OpenGL.GL as gl
            gl.glClearColor(r, g, b, a)
        except Exception:
            # OpenGL context not ready yet, color will be set in initializeGL()
            pass
        
    def get_widget_size(self) -> tuple[int, int]:
        """Get current widget width and height."""
        return self.width(), self.height()
        
    def initializeGL(self) -> None:
        """Called when OpenGL context is ready."""
        logger.debug("Live2D GL widget initialized")
        import OpenGL.GL as gl
        gl.glClearColor(*self._clear_color)
        gl.glEnable(gl.GL_BLEND)
        # Straight-alpha blending: works for both opaque and transparent clear colors,
        # since the destination alpha channel is preserved either way.
        gl.glBlendFuncSeparate(
            gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA,
            gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA
        )
        
    def paintGL(self) -> None:
        """Render the Live2D avatar."""
        import OpenGL.GL as gl
        # Clear the viewport
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        
        # Call the render callback if set
        if self._render_callback:
            try:
                self._render_callback()
            except Exception as e:
                logger.debug(f"Render callback error: {e}")
        
    def resizeGL(self, width: int, height: int) -> None:
        """Handle widget resize."""
        if hasattr(self.parent(), 'on_avatar_resize'):
            self.parent().on_avatar_resize(width, height)
    
    def set_render_callback(self, callback):
        """Set the render callback function."""
        self._render_callback = callback
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for avatar dragging."""
        if event.button() == Qt.LeftButton:
            self._last_mouse_pos = event.position()
            self._is_dragging = True
            self.mouse_pressed.emit(int(event.position().x()), int(event.position().y()))
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.mouse_released.emit(int(event.position().x()), int(event.position().y()))
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for eye tracking and dragging."""
        pos = event.position()
        self.mouse_moved.emit(int(pos.x()), int(pos.y()))
        
        if self._is_dragging and self._last_mouse_pos is not None:
            delta = pos - self._last_mouse_pos
            self.mouse_dragged.emit(int(delta.x()), int(delta.y()))
            self._last_mouse_pos = pos
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for zooming."""
        if event.angleDelta().y() > 0:
            self.wheel_scrolled.emit(True)  # Zoom in
        else:
            self.wheel_scrolled.emit(False)  # Zoom out
