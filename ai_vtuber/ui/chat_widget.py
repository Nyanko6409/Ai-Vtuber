"""AI VTuber - Chat Input Widget

Provides a chat input field with send button for user messages.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PySide6.QtCore import Qt, Signal


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
