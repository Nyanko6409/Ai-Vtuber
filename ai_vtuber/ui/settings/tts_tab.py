"""AI VTuber - TTS (Text-to-Speech) Settings Tab

Provides TTS model, voice, and speech parameters configuration.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QGroupBox, QSlider
from PySide6.QtCore import Qt


class TTSSettingsTab(QWidget):
    """TTS settings tab for text-to-speech model and parameters."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Model selection
        model_group = QGroupBox("🔊 TTS Model")
        model_layout = QGridLayout(model_group)
        model_layout.setSpacing(10)
        
        model_label = QLabel("Model:")
        model_layout.addWidget(model_label, 0, 0)
        
        self.tts_model_combo = QComboBox()
        self.tts_model_combo.addItems([
            "KittenML/kitten-tts-nano-0.8-int8",
            "KittenML/kitten-tts-nano-0.8",
            "KittenML/kitten-tts-micro-0.8",
            "KittenML/kitten-tts-mini-0.8"
        ])
        model_layout.addWidget(self.tts_model_combo, 0, 1)
        
        voice_label = QLabel("Voice:")
        model_layout.addWidget(voice_label, 1, 0)
        
        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.addItems([
            "Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"
        ])
        model_layout.addWidget(self.tts_voice_combo, 1, 1)
        
        layout.addWidget(model_group)
        
        # Speed and backend
        params_group = QGroupBox("⚙️ Parameters")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(15)
        
        # Speed slider
        speed_label = QLabel("Speech Speed:")
        params_layout.addWidget(speed_label)
        
        self.tts_speed_slider = QSlider(Qt.Horizontal)
        self.tts_speed_slider.setMinimum(50)
        self.tts_speed_slider.setMaximum(200)
        self.tts_speed_slider.setValue(125)
        self.tts_speed_slider.setTickPosition(QSlider.TicksBelow)
        self.tts_speed_slider.setTickInterval(25)
        params_layout.addWidget(self.tts_speed_slider)
        
        self.tts_speed_value_label = QLabel("1.25x")
        self.tts_speed_value_label.setAlignment(Qt.AlignCenter)
        self.tts_speed_value_label.setStyleSheet("color: #a0b0ff; font-weight: bold;")
        params_layout.addWidget(self.tts_speed_value_label)
        
        self.tts_speed_slider.valueChanged.connect(
            lambda v: self.tts_speed_value_label.setText(f"{v/100:.2f}x")
        )
        
        # Backend selection
        backend_label = QLabel("Backend:")
        params_layout.addWidget(backend_label)
        
        self.tts_backend_combo = QComboBox()
        self.tts_backend_combo.addItems(["cuda", "cpu"])
        params_layout.addWidget(self.tts_backend_combo)
        
        layout.addWidget(params_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        tts_config = self.config.get("tts", {})
        self.tts_model_combo.setCurrentText(tts_config.get("model", "KittenML/kitten-tts-nano-0.8-int8"))
        self.tts_voice_combo.setCurrentText(tts_config.get("voice", "Bella"))
        tts_speed = tts_config.get("speed", 1.25)
        self.tts_speed_slider.setValue(int(tts_speed * 100))
        self.tts_speed_value_label.setText(f"{tts_speed:.2f}x")
        self.tts_backend_combo.setCurrentText(tts_config.get("backend", "cuda"))
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "tts": {
                "model": self.tts_model_combo.currentText(),
                "voice": self.tts_voice_combo.currentText(),
                "speed": self.tts_speed_slider.value() / 100.0,
                "backend": self.tts_backend_combo.currentText(),
            }
        }
