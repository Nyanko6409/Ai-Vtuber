"""AI VTuber - STT (Speech-to-Text) Settings Tab

Provides speech recognition model and VAD configuration.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QGroupBox, QSlider
from PySide6.QtCore import Qt


class STTSettingsTab(QWidget):
    """STT settings tab for speech-to-text model and VAD configuration."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Model selection
        model_group = QGroupBox("🗣️ Speech-to-Text Model")
        model_layout = QGridLayout(model_group)
        model_layout.setSpacing(10)
        
        model_label = QLabel("Model Size:")
        model_layout.addWidget(model_label, 0, 0)
        
        self.stt_model_combo = QComboBox()
        self.stt_model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        model_layout.addWidget(self.stt_model_combo, 0, 1)
        
        device_label = QLabel("Device:")
        model_layout.addWidget(device_label, 1, 0)
        
        self.stt_device_combo = QComboBox()
        self.stt_device_combo.addItems(["auto", "cuda", "cpu"])
        model_layout.addWidget(self.stt_device_combo, 1, 1)
        
        layout.addWidget(model_group)
        
        # VAD settings
        vad_group = QGroupBox("📊 Voice Activity Detection")
        vad_layout = QVBoxLayout(vad_group)
        vad_layout.setSpacing(10)
        
        vad_label = QLabel("Sensitivity Threshold:")
        vad_layout.addWidget(vad_label)
        
        self.vad_slider = QSlider(Qt.Horizontal)
        self.vad_slider.setMinimum(1)
        self.vad_slider.setMaximum(9)
        self.vad_slider.setValue(5)
        self.vad_slider.setTickPosition(QSlider.TicksBelow)
        self.vad_slider.setTickInterval(1)
        vad_layout.addWidget(self.vad_slider)
        
        self.vad_value_label = QLabel("0.5")
        self.vad_value_label.setAlignment(Qt.AlignCenter)
        self.vad_value_label.setStyleSheet("color: #a0b0ff; font-weight: bold;")
        vad_layout.addWidget(self.vad_value_label)
        
        self.vad_slider.valueChanged.connect(
            lambda v: self.vad_value_label.setText(f"{v/10:.1f}")
        )
        
        layout.addWidget(vad_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        stt_config = self.config.get("stt", {})
        self.stt_model_combo.setCurrentText(stt_config.get("model_size", "base"))
        self.stt_device_combo.setCurrentText(stt_config.get("device", "auto"))
        vad_value = stt_config.get("vad_threshold", 0.5)
        self.vad_slider.setValue(int(vad_value * 10))
        self.vad_value_label.setText(f"{vad_value:.1f}")
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "stt": {
                "model_size": self.stt_model_combo.currentText(),
                "device": self.stt_device_combo.currentText(),
                "vad_threshold": self.vad_slider.value() / 10.0,
            }
        }
