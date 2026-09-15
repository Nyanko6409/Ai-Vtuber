"""AI VTuber - Status Bar Widget

Provides a status bar with FPS counter, microphone status, and action buttons.
"""

from PySide6.QtWidgets import QFrame, QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor


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
        btn.setCursor(QCursor(Qt.PointingHandCursor))
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
