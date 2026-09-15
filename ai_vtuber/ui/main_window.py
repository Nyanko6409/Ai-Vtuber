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

import logging
from typing import Optional, Callable, Dict, Any

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLineEdit
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QKeyEvent

from .live2d_widget import Live2DGLWidget
from .status_bar import StatusBar
from .chat_widget import ChatInputWidget
from .settings.dialog import show_settings_dialog

logger = logging.getLogger("ai_vtuber")


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
        
        # Get Live2D background color and opacity from avatar config
        avatar_config = config.get("avatar", {})
        live2d_bg_color = avatar_config.get("background_color", [0, 0, 0])
        live2d_opacity = avatar_config.get("opacity", 1.0)
        
        # Store color values for dynamic updates
        self.bg_r, self.bg_g, self.bg_b = bg_color[0], bg_color[1], bg_color[2]
        self.text_r, self.text_g, self.text_b = text_color[0], text_color[1], text_color[2]
        self.font_family = font_family
        self.font_size = font_size
        # Store Live2D background color values and opacity
        self.live2d_bg_r, self.live2d_bg_g, self.live2d_bg_b = live2d_bg_color[0], live2d_bg_color[1], live2d_bg_color[2]
        self.live2d_opacity = live2d_opacity
        
        # Callbacks
        self.on_chat_message: Optional[Callable[[str], None]] = None
        self.on_settings_save: Optional[Callable[[Dict], None]] = None
        self.on_settings_save = self._on_settings_saved
        
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
            # Use Live2D background color and opacity from config for the OpenGL clear color
            self.gl_widget.update_clear_color(
                self.live2d_bg_r / 255.0,
                self.live2d_bg_g / 255.0,
                self.live2d_bg_b / 255.0,
                self.live2d_opacity
            )
            live2d_bg_hex = f"#{self.live2d_bg_r:02x}{self.live2d_bg_g:02x}{self.live2d_bg_b:02x}"
            self.gl_widget.setStyleSheet(f"""
                QOpenGLWidget {{
                    background-color: {live2d_bg_hex};
                    border-radius: 0px;
                }}
            """)
        main_layout.addWidget(self.gl_widget, 1)

        # Compact chat input container - no large panel, just input + button
        self.chat_input_container = ChatInputWidget()
        self.chat_visible = True  # Start with chat input visible
        self.chat_input_container.setVisible(True)
        
        # Position chat input container as overlay on GL widget
        self.chat_input_container.setParent(self.gl_widget)
        
        # Connect chat input signal to handler
        self.chat_input_container.message_submitted.connect(self._handle_chat_message_from_widget)

        # Status bar
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar, 0)  # 0 = don't stretch status bar

        # Connect signals - CRITICAL: connect button clicks to slots
        self.status_bar.chat_button.clicked.connect(self._toggle_chat)
        self.status_bar.mic_button.clicked.connect(self._toggle_mic)
        self.status_bar.settings_button.clicked.connect(self._open_settings)

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
        # Re-apply Live2D background color after resize
        QTimer.singleShot(50, self._apply_live2d_background_on_resize)

    def _toggle_chat(self):
        """Toggle chat input visibility."""
        self.chat_visible = not self.chat_visible
        if self.chat_input_container:
            self.chat_input_container.setVisible(not self.chat_input_container.isVisible())
            if self.chat_input_container.isVisible():
                self.chat_input_container.set_focus()

    def _toggle_mic(self):
        """Toggle microphone on/off."""
        if self.app_instance:
            self.app_instance.toggle_microphone()

    def _open_settings(self):
        """Open settings dialog."""
        if self.app_instance:
            # Pass self as parent to ensure dialog appears on top of main window
            show_settings_dialog(self.config, self._on_settings_saved, parent=self)

    def _on_settings_saved(self, new_config: Dict[str, Any]):
        """Handle settings save event."""
        # Update config with new values
        self.config.update(new_config)
        # Apply UI settings including transparency
        ui_config = new_config.get("ui", {})
        avatar_config = new_config.get("avatar", {})
        
        # Update Live2D background color and opacity from avatar config
        live2d_bg_color = avatar_config.get("background_color", [0, 0, 0])
        live2d_opacity = avatar_config.get("opacity", 1.0)
        self.live2d_bg_r, self.live2d_bg_g, self.live2d_bg_b = live2d_bg_color[0], live2d_bg_color[1], live2d_bg_color[2]
        self.live2d_opacity = live2d_opacity
        
        # Need to restart the window if transparency changed
        transparent = ui_config.get("transparent", False)
        if transparent != self.transparent:
            # Transparency mode changed - need to recreate window
            logger.info(f"Transparency mode changed: {self.transparent} -> {transparent}")
            self.config["ui"]["transparent"] = transparent
            self.close()
            # Schedule recreation after close
            QTimer.singleShot(100, lambda: self._recreate_window())
        else:
            self.apply_ui_settings(ui_config)
            # Also apply Live2D background color update
            self._apply_live2d_background()
        logger.info("Settings saved and applied")

    def _recreate_window(self):
        """Recreate the main window with new transparency setting."""
        # Create a new instance with updated config
        new_window = QtMainWindow(self.config, self.app_instance)
        new_window.show()
        # Store reference to prevent garbage collection
        self.app_instance.main_window = new_window
        # CRITICAL: Setup callbacks for the new window (render callback, etc.)
        new_window._setup_callbacks()

    def _handle_chat_message(self, text: str):
        """Handle chat message from overlay."""
        if self.on_chat_message:
            self.on_chat_message(text)

    def _handle_chat_message_from_widget(self, text: str):
        """Handle chat message from chat widget."""
        self._handle_chat_message(text)

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
        """Apply UI settings from config (background color, text color, font, transparency)."""
        bg_color = ui_config.get("background_color", [0, 0, 0])
        text_color = ui_config.get("text_color", [255, 255, 255])
        font_family = ui_config.get("font_family", "Arial")
        font_size = ui_config.get("font_size", 14)
        transparent = ui_config.get("transparent", False)

        # Update stored values
        self.bg_r, self.bg_g, self.bg_b = bg_color[0], bg_color[1], bg_color[2]
        self.text_r, self.text_g, self.text_b = text_color[0], text_color[1], text_color[2]
        self.font_family = font_family
        self.font_size = font_size

        # Check if transparency mode changed
        transparency_changed = (self.transparent != transparent)
        self.transparent = transparent

        # Apply new styles based on transparency mode
        if self.transparent:
            # Must hide window before changing window flags
            if transparency_changed:
                self.hide()
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

            # Update central widget
            central_widget = self.centralWidget()
            if central_widget:
                central_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                central_widget.setStyleSheet("background: transparent;")

            # Update GL widget for transparency
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.gl_widget.update_clear_color(0.0, 0.0, 0.0, 0.0)
            self.gl_widget.setStyleSheet("QOpenGLWidget { background: transparent; border-radius: 0px; }")
        else:
            bg_hex = f"#{self.bg_r:02x}{self.bg_g:02x}{self.bg_b:02x}"
            text_hex = f"#{self.text_r:02x}{self.text_g:02x}{self.text_b:02x}"
            # Must hide window before changing window flags
            if transparency_changed:
                self.hide()
                self.setWindowFlags(Qt.Window)
            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {bg_hex};
                    color: {text_hex};
                    font-family: "{self.font_family}";
                    font-size: {self.font_size}px;
                }}
            """)

            # Update GL widget for opaque mode - use Live2D background color and opacity from config
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            live2d_bg_hex = f"#{self.live2d_bg_r:02x}{self.live2d_bg_g:02x}{self.live2d_bg_b:02x}"
            self.gl_widget.update_clear_color(
                self.live2d_bg_r / 255.0,
                self.live2d_bg_g / 255.0,
                self.live2d_bg_b / 255.0,
                self.live2d_opacity
            )
            self.gl_widget.setStyleSheet(f"""
                QOpenGLWidget {{
                    background-color: {live2d_bg_hex};
                    border-radius: 0px;
                }}
            """)

        # Show window again if transparency changed (flags were updated)
        if transparency_changed:
            self.show()

        logger.info(f"UI settings applied: transparent={transparent}, bg={bg_color}, text={text_color}, font={font_family} {font_size}px")

    def _apply_live2d_background(self):
        """Apply Live2D background color and opacity to the GL widget."""
        if self.transparent:
            # In transparent mode, use transparent clear color
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.gl_widget.update_clear_color(0.0, 0.0, 0.0, 0.0)
            self.gl_widget.setStyleSheet("QOpenGLWidget { background: transparent; border-radius: 0px; }")
        else:
            # In opaque mode, use configured Live2D background color and opacity
            self.gl_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            live2d_bg_hex = f"#{self.live2d_bg_r:02x}{self.live2d_bg_g:02x}{self.live2d_bg_b:02x}"
            self.gl_widget.update_clear_color(
                self.live2d_bg_r / 255.0,
                self.live2d_bg_g / 255.0,
                self.live2d_bg_b / 255.0,
                self.live2d_opacity
            )
            self.gl_widget.setStyleSheet(f"""
                QOpenGLWidget {{
                    background-color: {live2d_bg_hex};
                    border-radius: 0px;
                }}
            """)
        logger.info(f"Live2D background applied: R={self.live2d_bg_r}, G={self.live2d_bg_g}, B={self.live2d_bg_b}")

    def _apply_live2d_background_on_resize(self):
        """Re-apply Live2D background color after resize (for non-transparent mode)."""
        if not self.transparent:
            self._apply_live2d_background()

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
            if self.chat_input_container.isVisible() and self.chat_input_container.chat_input_field.hasFocus():
                # Let Qt handle it normally
                super().keyPressEvent(event)
