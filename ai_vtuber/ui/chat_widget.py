"""AI VTuber - Chat Input Widget

Provides a chat input field with send button for user messages.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QMouseEvent


class ChatInputWidget(QWidget):
    """Chat input widget with text field and send button.
    
    COLOR REFERENCE:
    - transparent: Container background (no surrounding box)
    - rgba(25, 25, 35, 230) (Dark Gray): Input field background
    - rgba(35, 35, 50, 240) (Lighter Dark Gray): Input field focused background
    - rgba(100, 150, 255, 60) (Faint Blue): Input field border default
    - rgba(120, 170, 255, 120) (Brighter Blue): Input field border focused
    - rgba(180, 180, 200, 150) (Light Gray): Placeholder text
    - rgba(50, 100, 200, 200) (Blue): Send button background
    - rgba(70, 130, 230, 220) (Lighter Blue): Send button hover
    - rgba(40, 90, 180, 200) (Darker Blue): Send button pressed
    - white: Input text and button text
    """
    
    # Signal emitted when user submits a message
    message_submitted = Signal(str)
    # Signal emitted when widget is dragged
    position_changed = Signal(int, int)  # new_x, new_y
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chatInputContainer")
        self.setStyleSheet("""
            #chatInputContainer {
                background-color: transparent;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        
        # Input field with subtle dark background
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
        self.chat_input_field.returnPressed.connect(self._send_message)
        layout.addWidget(self.chat_input_field, 1)
        
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
        self.chat_send_button.clicked.connect(self._send_message)
        layout.addWidget(self.chat_send_button)
        
        # Dragging state
        self._dragging = False
        self._drag_start_pos = None
        
        # Enable mouse tracking for smooth dragging
        self.setMouseTracking(True)
    
    def _send_message(self):
        """Send the typed message."""
        text = self.chat_input_field.text().strip()
        if text:
            self.message_submitted.emit(text)
            self.chat_input_field.clear()
    
    def get_text(self) -> str:
        """Get the current text in the input field."""
        return self.chat_input_field.text()
    
    def set_text(self, text: str):
        """Set the text in the input field."""
        self.chat_input_field.setText(text)
    
    def clear(self):
        """Clear the input field."""
        self.chat_input_field.clear()
    
    def set_focus(self):
        """Set focus to the input field."""
        self.chat_input_field.setFocus()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for dragging the widget."""
        if event.button() == Qt.LeftButton:
            # Only start dragging if clicking on empty space (not on input field or button)
            # Check if the click is not on any child widget
            child = self.childAt(event.position().toPoint())
            if child is None:
                self._dragging = True
                self._drag_start_pos = event.position()
                event.accept()
                return
        # Pass event to parent for normal handling
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for dragging the widget."""
        if self._dragging and self._drag_start_pos is not None:
            delta = event.position() - self._drag_start_pos
            new_pos = self.pos() + delta.toPoint()
            self.move(new_pos)
            self._drag_start_pos = event.position()
            # Emit signal with new position relative to parent
            self.position_changed.emit(new_pos.x(), new_pos.y())
            event.accept()
            return
        # Pass event to parent for normal handling
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release after dragging."""
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_start_pos = None
            event.accept()
            return
        # Pass event to parent for normal handling
        super().mouseReleaseEvent(event)
