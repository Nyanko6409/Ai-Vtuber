#!/usr/bin/env python3
"""AI VTuber - Qt Main Window with OpenGL Live2D Rendering

This module provides a complete Qt-based UI for the AI VTuber application,
replacing the Pygame-based UI. It features:
- QOpenGLWidget for Live2D avatar rendering
- Status bar with FPS counter and microphone status
- Overlay buttons for chat, mic toggle, and settings
- Integrated chat widget
- Settings dialog integration
"""

import sys
import logging
from typing import Optional, Callable, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF, QPointF
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QIcon, QMouseEvent,
    QWheelEvent, QKeyEvent, QPaintEvent, QResizeEvent
)

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
        # Set size policy to expand
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Enable mouse tracking for smooth eye movement
        self.setMouseTracking(True)
        # Apply gradient background style with darker colors for better contrast
        self.setStyleSheet("""
            QOpenGLWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a0f, stop:0.5 #0d0d14, stop:1 #101018);
                border-radius: 0px;
            }
        """)
        
    def get_widget_size(self) -> tuple[int, int]:
        """Get current widget width and height."""
        return self.width(), self.height()
        
    def initializeGL(self) -> None:
        """Called when OpenGL context is ready."""
        logger.debug("Live2D GL widget initialized")
        # Set clear color for debugging (will be overwritten by Live2D)
        import OpenGL.GL as gl
        gl.glClearColor(0.0, 0.0, 0.0, 0.0)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        
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


# ChatOverlayWidget class removed - replaced with simpler chat input widget without message history


class StatusBar(QFrame):
    """Status bar with FPS, mic status, and icon buttons."""
    
    chat_clicked = Signal()
    mic_clicked = Signal()
    settings_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setFixedHeight(55)
        self.setStyleSheet("""
            #statusBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(20, 20, 30, 200),
                    stop:0.5 rgba(30, 30, 45, 220),
                    stop:1 rgba(20, 20, 30, 200));
                border-top: 1px solid rgba(100, 150, 255, 60);
                border-bottom: none;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(20)
        
        # FPS counter with styled box
        fps_container = QWidget()
        fps_layout = QHBoxLayout(fps_container)
        fps_layout.setContentsMargins(10, 5, 10, 5)
        fps_container.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 60, 180);
                border-radius: 8px;
                border: 1px solid rgba(100, 150, 255, 40);
            }
        """)
        self.fps_label = QLabel("⚡ FPS: 0")
        self.fps_label.setStyleSheet("color: #a0b0ff; font-size: 14px; font-weight: bold;")
        fps_layout.addWidget(self.fps_label)
        layout.addWidget(fps_container)
        
        # Spacer
        layout.addStretch()
        
        # Mic status with icon
        self.mic_label = QLabel("🎤 ON")
        self.mic_label.setStyleSheet("color: #81C784; font-size: 15px; font-weight: bold; padding: 5px;")
        layout.addWidget(self.mic_label)
        
        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet("background-color: rgba(100, 150, 255, 60); min-width: 1px;")
        separator.setFixedWidth(1)
        layout.addWidget(separator)
        
        # Icon buttons container - horizontal layout with better styling
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Create icon buttons
        self.chat_button = self._create_icon_button("💬", "Open Chat")
        self.mic_button = self._create_icon_button("🎤", "Toggle Microphone")
        self.settings_button = self._create_icon_button("⚙", "Settings")
        
        button_layout.addWidget(self.chat_button)
        button_layout.addWidget(self.mic_button)
        button_layout.addWidget(self.settings_button)
        
        layout.addLayout(button_layout)
    
    def _create_icon_button(self, icon: str, tooltip: str) -> QPushButton:
        """Create a styled icon button."""
        btn = QPushButton(icon)
        btn.setFixedSize(36, 36)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(60, 60, 90, 200),
                    stop:1 rgba(40, 40, 70, 200));
                border: 1px solid rgba(100, 150, 255, 60);
                border-radius: 10px;
                font-size: 18px;
                color: white;
                padding: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(80, 80, 120, 220),
                    stop:1 rgba(60, 60, 100, 220));
                border: 1px solid rgba(120, 170, 255, 100);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(50, 50, 80, 200),
                    stop:1 rgba(30, 30, 60, 200));
                border: 1px solid rgba(80, 130, 235, 80);
                padding: 5px 3px 3px 5px;
            }
        """)
        return btn
    
    def update_fps(self, fps: float):
        """Update FPS display."""
        if fps > 0:
            self.fps_label.setText(f"⚡ FPS: {fps:.0f}")
        else:
            self.fps_label.setText("⚡ FPS: 0")
    
    def update_mic_status(self, is_muted: bool):
        """Update microphone status display."""
        if is_muted:
            self.mic_label.setText("🔇 OFF")
            self.mic_label.setStyleSheet("color: #EF5350; font-size: 15px; font-weight: bold; padding: 5px;")
        else:
            self.mic_label.setText("🎤 ON")
            self.mic_label.setStyleSheet("color: #81C784; font-size: 15px; font-weight: bold; padding: 5px;")


class QtMainWindow(QMainWindow):
    """Main Qt window for AI VTuber application."""
    
    def __init__(self, config: Dict[str, Any], app_instance=None):
        super().__init__()
        self.config = config
        self.app_instance = app_instance
        
        # State
        self.chat_visible = False
        self.show_fps = config.get("ui", {}).get("show_fps", True)
        self.show_debug = config.get("ui", {}).get("show_debug", False)
        
        # Callbacks
        self.on_chat_message: Optional[Callable[[str], None]] = None
        self.on_settings_save: Optional[Callable[[Dict], None]] = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("AI VTuber")
        self.setMinimumSize(800, 600)
        
        # Set window size from config
        width = self.config.get("avatar", {}).get("window_width", 800)
        height = self.config.get("avatar", {}).get("window_height", 600)
        self.resize(width, height)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # OpenGL widget for Live2D with custom styling
        self.gl_widget = Live2DGLWidget()
        self.gl_widget.setAutoFillBackground(False)
        # Set minimum size to ensure it's visible
        self.gl_widget.setMinimumSize(400, 300)
        main_layout.addWidget(self.gl_widget, 1)
        
        # Chat overlay - removed messages area, only input field remains
        self.chat_widget = QWidget()
        self.chat_widget.setObjectName("chatInputOverlay")
        self.chat_widget.setStyleSheet("""
            #chatInputOverlay {
                background-color: rgba(30, 30, 30, 220);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
        """)
        self.chat_widget.setVisible(False)
        
        chat_layout = QVBoxLayout(self.chat_widget)
        chat_layout.setContentsMargins(15, 15, 15, 15)
        chat_layout.setSpacing(10)
        
        # Title with close button
        title_layout = QHBoxLayout()
        self.chat_title_label = QLabel("💬 Chat with VTuber")
        self.chat_title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        title_layout.addWidget(self.chat_title_label)
        title_layout.addStretch()
        chat_layout.addLayout(title_layout)
        
        # Input field with send button (no message history display)
        input_layout = QHBoxLayout()
        from PySide6.QtWidgets import QLineEdit
        self.chat_input_field = QLineEdit()
        self.chat_input_field.setPlaceholderText("Type your message...")
        self.chat_input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(100, 150, 255, 150);
                background-color: rgba(60, 60, 70, 220);
            }
        """)
        self.chat_input_field.returnPressed.connect(self._send_chat_message)
        input_layout.addWidget(self.chat_input_field, 1)
        
        # Send button
        self.chat_send_button = QPushButton("➤")
        self.chat_send_button.setFixedSize(40, 40)
        self.chat_send_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(70, 130, 255, 200);
                border: none;
                border-radius: 8px;
                font-size: 18px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(90, 150, 255, 220);
            }
            QPushButton:pressed {
                background-color: rgba(50, 110, 235, 200);
            }
        """)
        self.chat_send_button.clicked.connect(self._send_chat_message)
        input_layout.addWidget(self.chat_send_button)
        chat_layout.addLayout(input_layout)
        
        # Position chat overlay in bottom-left
        self.chat_widget.setParent(self.gl_widget)
        
        # Status bar
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar, 0)  # 0 = don't stretch status bar
        
        # Connect signals - CRITICAL: connect button clicks to slots
        self.status_bar.chat_button.clicked.connect(self._toggle_chat)
        self.status_bar.mic_button.clicked.connect(self._toggle_mic)
        self.status_bar.settings_button.clicked.connect(self._open_settings)
        self.chat_widget.message_sent.connect(self._handle_chat_message)
        
        # GL widget signals
        self.gl_widget.mouse_dragged.connect(self._handle_avatar_drag)
        self.gl_widget.wheel_scrolled.connect(self._handle_wheel_scroll)
        self.gl_widget.mouse_moved.connect(self._handle_mouse_move)
        
        # Setup chat overlay geometry after GL widget is added to layout
        QTimer.singleShot(100, self._setup_chat_geometry)
        
        # FPS timer
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps)
        self.fps_timer.start(1000)
        
        self.frame_count = 0
        self.last_fps_update = 0
        
    def _setup_callbacks(self):
        """Setup rendering and interaction callbacks."""
        if self.app_instance:
            # Setup avatar rendering callback
            def render_callback():
                # Update and draw the avatar
                if self.app_instance._avatar and self.app_instance._avatar.is_initialized:
                    try:
                        delta_time = 1.0 / self.config.get("avatar", {}).get("fps", 30)
                        self.app_instance.avatar.update(delta_time)
                        self.app_instance.avatar.draw()
                    except Exception as e:
                        logger.debug(f"Avatar render error: {e}")
            
            # Set the render callback on the GL widget
            self.gl_widget.set_render_callback(render_callback)
            
            # Initialize Live2D after GL context is ready
            QTimer.singleShot(200, self._init_live2d_after_gl_ready)
    
    def _init_live2d_after_gl_ready(self):
        """Initialize Live2D model after OpenGL context is established."""
        if self.app_instance and self.app_instance._avatar:
            try:
                logger.debug("Initializing Live2D with GL context...")
                if self.app_instance._avatar.init_gl():
                    logger.info("Live2D avatar initialized successfully")
                else:
                    logger.warning("Live2D initialization returned False")
            except Exception as e:
                logger.error(f"Live2D initialization failed: {e}", exc_info=True)
    
    @Slot(float)
    def _update_fps(self):
        """Update FPS counter."""
        if self.show_fps:
            fps = self.frame_count
            self.status_bar.update_fps(fps)
        self.frame_count = 0
    
    def process_cycle(self):
        """Process VTuber cycle and trigger GL update."""
        if self.app_instance:
            self.app_instance.process_cycle()
        # Trigger OpenGL redraw
        self.gl_widget.update()
        self.increment_frame()
    
    def increment_frame(self):
        """Increment frame counter (called each render)."""
        self.frame_count += 1
    
    def _setup_chat_geometry(self):
        """Setup chat overlay geometry after GL widget is sized."""
        if self.chat_widget and self.gl_widget:
            # Position chat in bottom-left corner of GL widget
            gl_rect = self.gl_widget.geometry()
            chat_width = min(400, gl_rect.width() - 30)
            chat_height = min(300, gl_rect.height() - 80)
            self.chat_widget.setGeometry(15, gl_rect.height() - chat_height - 15, chat_width, chat_height)
            self.chat_widget.raise_()  # Bring to front
    
    def resizeEvent(self, event):
        """Handle window resize to reposition chat overlay."""
        super().resizeEvent(event)
        # Reposition chat overlay after resize
        QTimer.singleShot(50, self._setup_chat_geometry)
    
    def _toggle_chat(self):
        """Toggle chat overlay visibility."""
        self.chat_visible = not self.chat_visible
        if self.chat_widget:
            self.chat_widget.setVisible(not self.chat_widget.isVisible())
            if self.chat_widget.isVisible():
                self.chat_input_field.setFocus()
    
    def _toggle_mic(self):
        """Toggle microphone on/off."""
        if self.app_instance:
            self.app_instance.toggle_microphone()
    
    def _open_settings(self):
        """Open settings dialog."""
        if self.app_instance and self.on_settings_save:
            from .pyside_settings import show_settings_dialog
            # Pass self as parent to ensure dialog appears on top of main window
            show_settings_dialog(self.config, self.on_settings_save, parent=self)
    
    def _handle_chat_message(self, text: str):
        """Handle chat message from overlay."""
        if self.on_chat_message:
            self.on_chat_message(text)
    
    def _handle_avatar_drag(self, dx: int, dy: int):
        """Handle avatar dragging."""
        if self.app_instance and self.app_instance.avatar:
            self.app_instance.avatar.move_by(dx, -dy)
    
    def _handle_wheel_scroll(self, zoom_in: bool):
        """Handle mouse wheel zoom."""
        if self.app_instance and self.app_instance.avatar:
            if zoom_in:
                self.app_instance.avatar.zoom_in(0.2)
            else:
                self.app_instance.avatar.zoom_out(0.2)
    
    def _handle_mouse_move(self, x: int, y: int):
        """Handle mouse movement for eye tracking."""
        if self.app_instance and self.app_instance.avatar:
            try:
                # Get widget dimensions for proper coordinate normalization
                width, height = self.gl_widget.get_widget_size()
                self.app_instance.avatar.drag(x, y, width, height)
            except Exception as e:
                logger.debug(f"Mouse move handling error: {e}")
    
    def on_avatar_resize(self, width: int, height: int):
        """Handle avatar resize event."""
        if self.app_instance and self.app_instance.avatar:
            self.app_instance.avatar.resize(width, height)
    
    def update_mic_status(self, is_muted: bool):
        """Update microphone status in status bar."""
        self.status_bar.update_mic_status(is_muted)
    
    def _send_chat_message(self):
        """Send the typed message."""
        text = self.chat_input_field.text().strip()
        if text and self.on_chat_message:
            self.on_chat_message(text)
            self.chat_input_field.clear()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_F:
            self.show_fps = not self.show_fps
            if not self.show_fps:
                self.status_bar.update_fps(0)
        elif event.key() == Qt.Key_D:
            self.show_debug = not self.show_debug
        else:
            # Pass other keys to chat input if active
            if self.chat_widget.isVisible() and self.chat_widget.input_field.hasFocus():
                # Let Qt handle it normally
                super().keyPressEvent(event)
