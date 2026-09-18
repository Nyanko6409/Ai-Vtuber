"""AI VTuber - LLM (Language Model) Settings Tab

Provides language model path and generation parameters configuration.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QGroupBox, QSlider, QCheckBox
from PySide6.QtCore import Qt


class LLMSettingsTab(QWidget):
    """LLM settings tab for language model and generation parameters."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Model path
        model_group = QGroupBox("🤖 Language Model")
        model_layout = QGridLayout(model_group)
        model_layout.setSpacing(10)
        
        model_label = QLabel("Model Path / URL:")
        model_layout.addWidget(model_label, 0, 0)
        
        self.llm_model_edit = QLineEdit()
        self.llm_model_edit.setPlaceholderText("e.g., http://localhost:1234/v1")
        model_layout.addWidget(self.llm_model_edit, 0, 1)
        
        layout.addWidget(model_group)
        
        # Generation parameters
        params_group = QGroupBox("⚙️ Generation Parameters")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(15)
        
        # Temperature slider
        temp_label = QLabel("Temperature:")
        params_layout.addWidget(temp_label)
        
        self.llm_temp_slider = QSlider(Qt.Horizontal)
        self.llm_temp_slider.setMinimum(1)
        self.llm_temp_slider.setMaximum(20)
        self.llm_temp_slider.setValue(7)
        self.llm_temp_slider.setTickPosition(QSlider.TicksBelow)
        self.llm_temp_slider.setTickInterval(1)
        params_layout.addWidget(self.llm_temp_slider)
        
        self.llm_temp_value_label = QLabel("0.7")
        self.llm_temp_value_label.setAlignment(Qt.AlignCenter)
        self.llm_temp_value_label.setStyleSheet("color: #a0b0ff; font-weight: bold;")
        params_layout.addWidget(self.llm_temp_value_label)
        
        self.llm_temp_slider.valueChanged.connect(
            lambda v: self.llm_temp_value_label.setText(f"{v/10:.1f}")
        )
        
        # Streaming checkbox
        self.llm_stream_check = QCheckBox("Enable Streaming Responses")
        self.llm_stream_check.setStyleSheet("font-size: 13px; padding: 5px;")
        params_layout.addWidget(self.llm_stream_check)
        
        layout.addWidget(params_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        llm_config = self.config.get("llm", {})
        self.llm_model_edit.setText(llm_config.get("base_url", ""))
        llm_temp = llm_config.get("temperature", 0.7)
        self.llm_temp_slider.setValue(int(llm_temp * 10))
        self.llm_temp_value_label.setText(f"{llm_temp:.1f}")
        self.llm_stream_check.setChecked(llm_config.get("stream_enabled", True))
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "llm": {
                "base_url": self.llm_model_edit.text(),
                "temperature": self.llm_temp_slider.value() / 10.0,
                "stream_enabled": self.llm_stream_check.isChecked(),
            }
        }
