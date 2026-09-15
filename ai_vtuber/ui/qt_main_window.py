#!/usr/bin/env python3
"""AI VTuber - Qt Main Window with OpenGL Live2D Rendering

This module provides a complete Qt-based UI for the AI VTuber application,
replacing the Pygame-based UI. It features:
- QOpenGLWidget for Live2D avatar rendering
- Status bar with FPS counter and microphone status
- Overlay buttons for chat, mic toggle, and settings
- Integrated chat widget
- Settings dialog integration

COLOR REFERENCE (All colors defined here for consistency):
================================================================================
BACKGROUND COLORS:
- #000000 (Pure Black): Main window background, OpenGL clear color, Live2D widget
- rgba(25, 25, 35, 230) (Dark Gray): Chat input field background
- rgba(35, 35, 50, 240) (Lighter Dark Gray): Chat input focused background
- transparent: Chat input container (no surrounding box)

BUTTON COLORS:
- rgba(50, 100, 200, 200) (Blue): Send button background
- rgba(70, 130, 230, 220) (Lighter Blue): Send button hover
- rgba(40, 90, 180, 200) (Darker Blue): Send button pressed
- rgba(60, 60, 90, 200) to rgba(40, 40, 70, 200) (Blue-Gray): Status bar buttons

TEXT COLORS:
- white/#ffffff: Primary text, button text
- rgba(180, 180, 200, 150) (Light Gray): Placeholder text in input fields
- #a0b0ff (Light Blue): FPS label, value labels
- #81C784 (Green): Microphone ON indicator
- #EF5350 (Red): Microphone OFF indicator

BORDER COLORS:
- rgba(100, 150, 255, 60) (Faint Blue): Input field border default
- rgba(120, 170, 255, 120) (Brighter Blue): Input field border focused

STATUS BAR COLORS:
- rgba(20, 20, 30, 200) to rgba(30, 30, 45, 220) (Dark Blue-Gray Gradient): Background
- rgba(40, 40, 60, 180) (Dark Blue-Gray): FPS counter container
- rgba(100, 150, 255, 60) (Faint Blue): Separator line
================================================================================
"""

import logging
from typing import Optional, Callable, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent

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
        from PySide6.QtWidgets import QSizePolicy
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


# ChatOverlayWidget class removed - replaced with simpler chat input widget without message history


class StatusBar(QFrame):
    """Status bar with FPS, mic status, and icon buttons.
    
    COLOR REFERENCE:
    - rgba(20, 20, 30, 200) to rgba(30, 30, 45, 220) (Dark Blue-Gray Gradient): Status bar background
    - rgba(40, 40, 60, 180) (Dark Blue-Gray): FPS counter container
    - #a0b0ff (Light Blue): FPS text
    - #81C784 (Green): Microphone ON indicator
    - #EF5350 (Red): Microphone OFF indicator
    - rgba(60, 60, 90, 200) to rgba(40, 40, 70, 200) (Blue-Gray Gradient): Icon buttons
    - white: Button text/icons
    - rgba(100, 150, 255, 60) (Light Blue): Borders and separators
    """
    
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
    """Main Qt window for AI VTuber application.
    
    COLOR REFERENCE (see module docstring for complete palette):
    - #000000 (Pure Black): Main window background, Live2D OpenGL widget
    - transparent: Chat input container (no surrounding box)
    - rgba(25, 25, 35, 230) (Dark Gray): Chat input field background
    - white: Input text
    - rgba(180, 180, 200, 150) (Light Gray): Placeholder text
    - rgba(50, 100, 200, 200) (Blue): Send button
    """
    
    def __init__(self, config: Dict[str, Any], app_instance=None):
        super().__init__()
        self.config = config
        self.app_instance = app_instance
        
        # State
        self.chat_visible = False
        self.show_fps = config.get("ui", {}).get("show_fps", True)
        self.show_debug = config.get("ui", {}).get("show_debug", False)
        
        # Get UI colors from config
        ui_config = config.get("ui", {})
        self.transparent = ui_config.get("transparent", False)
        bg_color = ui_config.get("background_color", [0, 0, 0])
        text_color = ui_config.get("text_color", [255, 255, 255])
        font_family = ui_config.get("font_family", "Arial")
        font_size = ui_config.get("font_size", 14)
        
        # Store color values for dynamic updates
        self.bg_r, self.bg_g, self.bg_b = bg_color[0], bg_color[1], bg_color[2]
        self.text_r, self.text_g, self.text_b = text_color[0], text_color[1], text_color[2]
        self.font_family = font_family
        self.font_size = font_size
        
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

        if self.transparent:
            # Frameless + translucent so only the rendered avatar shows.
            # Needs a compositing WM (default on GNOME/KDE; use picom on i3/sway-style setups).
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setStyleSheet(f"""
                QMainWindow {{
                    background: transparent;
                    color: #{self.text_r:02x}{self.text_g:02x}{self.text_b:02x};
                    font-family: "{self.font_family}";
                    font-size: {self.font_size}px;
                }}
            """)
        else:
            # Set main window background to configured color
            bg_hex = f"#{self.bg_r:02x}{self.bg_g:02x}{self.bg_b:02x}"
            text_hex = f"#{self.text_r:02x}{self.text_g:02x}{self.text_b:02x}"
            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {bg_hex};
                    color: {text_hex};
                    font-family: "{self.font_family}";
                    font-size: {self.font_size}px;
                }}
            """)
        
        # Central widget
        central_widget = QWidget()
        if self.transparent:
            central_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            central_widget.setStyleSheet("background: transparent;")
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # OpenGL widget for Live2D with custom styling - pure black background
        self.gl_widget = Live2DGLWidget()
        self.gl_widget.setAutoFillBackground(False)
        self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        if self.transparent:
            # The GL surface itself needs an alpha channel, or there's nothing for
            # the compositor to blend against - must be set before the widget shows.
            from PySide6.QtGui import QSurfaceFormat
            fmt = QSurfaceFormat()
            fmt.setAlphaBufferSize(8)
            self.gl_widget.setFormat(fmt)
            # WA_OpaquePaintEvent=True was forcing an opaque backing store, which
            # blocked alpha from ever reaching the compositor - must be False here.
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.gl_widget.setMinimumSize(400, 300)
            # Alpha = 0 clear color: transparent everywhere except where the avatar draws
            self.gl_widget.update_clear_color(0.0, 0.0, 0.0, 0.0)
            self.gl_widget.setStyleSheet("QOpenGLWidget { background: transparent; border-radius: 0px; }")
        else:
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.gl_widget.setMinimumSize(400, 300)
            self.gl_widget.update_clear_color(self.bg_r / 255.0, self.bg_g / 255.0, self.bg_b / 255.0, 1.0)
            self.gl_widget.setStyleSheet(f"""
                QOpenGLWidget {{
                    background-color: #{self.bg_r:02x}{self.bg_g:02x}{self.bg_b:02x};
                    border-radius: 0px;
                }}
            """)
        main_layout.addWidget(self.gl_widget, 1)
        
        # Compact chat input container - no large panel, just input + button
        self.chat_input_container = QWidget()
        self.chat_input_container.setObjectName("chatInputContainer")
        self.chat_visible = True  # Start with chat input visible
        self.chat_input_container.setVisible(True)
        
        # Style only the input field area, no surrounding box
        self.chat_input_container.setStyleSheet("""
            #chatInputContainer {
                background-color: transparent;
            }
        """)
        
        chat_input_layout = QHBoxLayout(self.chat_input_container)
        chat_input_layout.setContentsMargins(0, 0, 0, 0)
        chat_input_layout.setSpacing(10)
        chat_input_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        
        # Input field with subtle dark background
        from PySide6.QtWidgets import QLineEdit
        self.chat_input_field = QLineEdit()
        self.chat_input_field.setPlaceholderText("Type your message...")
        self.chat_input_field.setFixedHeight(40)
        self.chat_input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(25, 25, 35, 230);
                color: white;
                border: 1px solid rgba(100, 150, 255, 60);
                border-radius: 8px;
                padding: 0 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(120, 170, 255, 120);
                background-color: rgba(35, 35, 50, 240);
            }
            QLineEdit::placeholder {
                color: rgba(180, 180, 200, 150);
            }
        """)
        self.chat_input_field.returnPressed.connect(self._send_chat_message)
        chat_input_layout.addWidget(self.chat_input_field, 1)
        
        # Send button - compact
        self.chat_send_button = QPushButton("➤")
        self.chat_send_button.setFixedSize(40, 40)
        self.chat_send_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(50, 100, 200, 200);
                border: none;
                border-radius: 8px;
                font-size: 16px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(70, 130, 230, 220);
            }
            QPushButton:pressed {
                background-color: rgba(40, 90, 180, 200);
            }
        """)
        self.chat_send_button.clicked.connect(self._send_chat_message)
        chat_input_layout.addWidget(self.chat_send_button)
        
        # Position chat input container as overlay on GL widget
        self.chat_input_container.setParent(self.gl_widget)
        
        # Status bar
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar, 0)  # 0 = don't stretch status bar
        
        # Connect signals - CRITICAL: connect button clicks to slots
        self.status_bar.chat_button.clicked.connect(self._toggle_chat)
        self.status_bar.mic_button.clicked.connect(self._toggle_mic)
        self.status_bar.settings_button.clicked.connect(self._open_settings)
        # Chat input field sends message via returnPressed and button click (no custom signal needed)
        
        # GL widget signals
        self.gl_widget.mouse_dragged.connect(self._handle_avatar_drag)
        self.gl_widget.wheel_scrolled.connect(self._handle_wheel_scroll)
        self.gl_widget.mouse_moved.connect(self._handle_mouse_move)
        
        # Setup chat input geometry after GL widget is added to layout
        QTimer.singleShot(100, self._setup_chat_input_geometry)
        
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
    
    def _setup_chat_input_geometry(self):
        """Setup chat input container geometry after GL widget is sized."""
        if self.chat_input_container and self.gl_widget:
            # Position chat input at bottom center of GL widget
            gl_rect = self.gl_widget.geometry()
            input_width = min(500, gl_rect.width() - 40)
            input_height = 60  # Just enough for the input field + button
            x_pos = (gl_rect.width() - input_width) // 2
            y_pos = gl_rect.height() - input_height - 20
            self.chat_input_container.setGeometry(x_pos, y_pos, input_width, input_height)
            self.chat_input_container.raise_()  # Bring to front
    
    def resizeEvent(self, event):
        """Handle window resize to reposition chat input."""
        super().resizeEvent(event)
        # Reposition chat input after resize
        QTimer.singleShot(50, self._setup_chat_input_geometry)
    
    def _toggle_chat(self):
        """Toggle chat input visibility."""
        self.chat_visible = not self.chat_visible
        if self.chat_input_container:
            self.chat_input_container.setVisible(not self.chat_input_container.isVisible())
            if self.chat_input_container.isVisible():
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
    
    def apply_ui_settings(self, ui_config: Dict[str, Any]):
        """Apply UI settings from config (background color, text color, font)."""
        bg_color = ui_config.get("background_color", [0, 0, 0])
        text_color = ui_config.get("text_color", [255, 255, 255])
        font_family = ui_config.get("font_family", "Arial")
        font_size = ui_config.get("font_size", 14)
        
        # Update stored values
        self.bg_r, self.bg_g, self.bg_b = bg_color[0], bg_color[1], bg_color[2]
        self.text_r, self.text_g, self.text_b = text_color[0], text_color[1], text_color[2]
        self.font_family = font_family
        self.font_size = font_size
        
        # Apply new styles
        bg_hex = f"#{self.bg_r:02x}{self.bg_g:02x}{self.bg_b:02x}"
        text_hex = f"#{self.text_r:02x}{self.text_g:02x}{self.text_b:02x}"
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {bg_hex};
                color: {text_hex};
                font-family: "{self.font_family}";
                font-size: {self.font_size}px;
            }}
        """)
        
        # Update OpenGL clear color via the GL widget
        if hasattr(self.gl_widget, 'update_clear_color'):
            self.gl_widget.update_clear_color(
                self.bg_r / 255.0,
                self.bg_g / 255.0,
                self.bg_b / 255.0,
                1.0
            )
        
        logger.info(f"UI settings applied: bg={bg_hex}, text={text_hex}, font={font_family} {font_size}px")
    
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
            if self.chat_input_container.isVisible() and self.chat_input_field.hasFocus():
                # Let Qt handle it normally
                super().keyPressEvent(event)
