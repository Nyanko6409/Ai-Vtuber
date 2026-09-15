"""AI VTuber - Avatar Settings Tab

Provides Live2D model path and appearance configuration.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QGroupBox, QSlider
from PySide6.QtCore import Qt


class AvatarSettingsTab(QWidget):
    """Avatar settings tab for Live2D model and appearance."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Model path
        model_group = QGroupBox("🎭 Avatar Model")
        model_layout = QGridLayout(model_group)
        model_layout.setSpacing(10)
        
        model_label = QLabel("Model Path:")
        model_layout.addWidget(model_label, 0, 0)
        
        self.avatar_model_edit = QLineEdit()
        self.avatar_model_edit.setPlaceholderText("Path to .model3.json file")
        model_layout.addWidget(self.avatar_model_edit, 0, 1)
        
        layout.addWidget(model_group)
        
        # Appearance
        appearance_group = QGroupBox("🎨 Appearance")
        appearance_layout = QVBoxLayout(appearance_group)
        appearance_layout.setSpacing(15)
        
        # Scale slider
        scale_label = QLabel("Scale:")
        appearance_layout.addWidget(scale_label)
        
        self.avatar_scale_slider = QSlider(Qt.Horizontal)
        self.avatar_scale_slider.setMinimum(5)
        self.avatar_scale_slider.setMaximum(50)
        self.avatar_scale_slider.setValue(20)
        self.avatar_scale_slider.setTickPosition(QSlider.TicksBelow)
        self.avatar_scale_slider.setTickInterval(5)
        appearance_layout.addWidget(self.avatar_scale_slider)
        
        self.avatar_scale_value_label = QLabel("2.0x")
        self.avatar_scale_value_label.setAlignment(Qt.AlignCenter)
        self.avatar_scale_value_label.setStyleSheet("color: #a0b0ff; font-weight: bold;")
        appearance_layout.addWidget(self.avatar_scale_value_label)
        
        self.avatar_scale_slider.valueChanged.connect(
            lambda v: self.avatar_scale_value_label.setText(f"{v/10:.1f}x")
        )
        
        layout.addWidget(appearance_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        avatar_config = self.config.get("avatar", {})
        self.avatar_model_edit.setText(avatar_config.get("model_path", ""))
        avatar_scale = avatar_config.get("scale", 2.0)
        self.avatar_scale_slider.setValue(int(avatar_scale * 10))
        self.avatar_scale_value_label.setText(f"{avatar_scale:.1f}x")
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "avatar": {
                "model_path": self.avatar_model_edit.text(),
                "scale": self.avatar_scale_slider.value() / 10.0,
            }
        }
