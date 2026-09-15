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
        
        # Live2D Background Color settings
        live2d_bg_group = QGroupBox("🎨 Live2D Background Color")
        live2d_bg_layout = QGridLayout(live2d_bg_group)
        live2d_bg_layout.setSpacing(10)
        
        live2d_bg_label = QLabel("Live2D Background Color (RGB):")
        live2d_bg_layout.addWidget(live2d_bg_label, 0, 0)
        
        bg_colors = self.config.get("avatar", {}).get("background_color", [0, 0, 0])
        
        self.live2d_bg_r_spin = QSpinBox()
        self.live2d_bg_r_spin.setMinimum(0)
        self.live2d_bg_r_spin.setMaximum(255)
        self.live2d_bg_r_spin.setValue(bg_colors[0] if len(bg_colors) > 0 else 0)
        self.live2d_bg_r_spin.setPrefix("R: ")
        live2d_bg_layout.addWidget(self.live2d_bg_r_spin, 0, 1)
        
        self.live2d_bg_g_spin = QSpinBox()
        self.live2d_bg_g_spin.setMinimum(0)
        self.live2d_bg_g_spin.setMaximum(255)
        self.live2d_bg_g_spin.setValue(bg_colors[1] if len(bg_colors) > 1 else 0)
        self.live2d_bg_g_spin.setPrefix("G: ")
        live2d_bg_layout.addWidget(self.live2d_bg_g_spin, 0, 2)
        
        self.live2d_bg_b_spin = QSpinBox()
        self.live2d_bg_b_spin.setMinimum(0)
        self.live2d_bg_b_spin.setMaximum(255)
        self.live2d_bg_b_spin.setValue(bg_colors[2] if len(bg_colors) > 2 else 0)
        self.live2d_bg_b_spin.setPrefix("B: ")
        live2d_bg_layout.addWidget(self.live2d_bg_b_spin, 0, 3)
        
        layout.addWidget(live2d_bg_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        avatar_config = self.config.get("avatar", {})
        self.avatar_model_edit.setText(avatar_config.get("model_path", ""))
        avatar_scale = avatar_config.get("scale", 2.0)
        self.avatar_scale_slider.setValue(int(avatar_scale * 10))
        self.avatar_scale_value_label.setText(f"{avatar_scale:.1f}x")
        
        # Load Live2D background color
        bg_colors = avatar_config.get("background_color", [0, 0, 0])
        self.live2d_bg_r_spin.setValue(bg_colors[0] if len(bg_colors) > 0 else 0)
        self.live2d_bg_g_spin.setValue(bg_colors[1] if len(bg_colors) > 1 else 0)
        self.live2d_bg_b_spin.setValue(bg_colors[2] if len(bg_colors) > 2 else 0)
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "avatar": {
                "model_path": self.avatar_model_edit.text(),
                "scale": self.avatar_scale_slider.value() / 10.0,
                "background_color": [
                    self.live2d_bg_r_spin.value(),
                    self.live2d_bg_g_spin.value(),
                    self.live2d_bg_b_spin.value(),
                ],
            }
        }
