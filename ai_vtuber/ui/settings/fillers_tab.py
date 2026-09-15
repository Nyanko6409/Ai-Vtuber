"""AI VTuber - Fillers Settings Tab

Provides filler words timing and configuration.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QCheckBox, QSpinBox, QLabel


class FillersSettingsTab(QWidget):
    """Fillers settings tab for filler words configuration."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Enable fillers
        enable_group = QGroupBox("🎬 Filler Words")
        enable_layout = QVBoxLayout(enable_group)
        enable_layout.setSpacing(10)
        
        self.fillers_enable_check = QCheckBox("Enable Filler Words")
        self.fillers_enable_check.setStyleSheet("font-size: 14px; padding: 8px;")
        enable_layout.addWidget(self.fillers_enable_check)
        
        layout.addWidget(enable_group)
        
        # Timing parameters
        timing_group = QGroupBox("⏱️ Timing")
        timing_layout = QVBoxLayout(timing_group)
        timing_layout.setSpacing(15)
        
        # Start delay
        start_delay_label = QLabel("Start Delay (ms):")
        timing_layout.addWidget(start_delay_label)
        
        self.filler_start_spin = QSpinBox()
        self.filler_start_spin.setMinimum(100)
        self.filler_start_spin.setMaximum(2000)
        self.filler_start_spin.setValue(500)
        self.filler_start_spin.setSingleStep(100)
        self.filler_start_spin.setSuffix(" ms")
        timing_layout.addWidget(self.filler_start_spin)
        
        # Stall threshold
        stall_label = QLabel("Stall Threshold (ms):")
        timing_layout.addWidget(stall_label)
        
        self.filler_stall_spin = QSpinBox()
        self.filler_stall_spin.setMinimum(100)
        self.filler_stall_spin.setMaximum(2000)
        self.filler_stall_spin.setValue(400)
        self.filler_stall_spin.setSingleStep(100)
        self.filler_stall_spin.setSuffix(" ms")
        timing_layout.addWidget(self.filler_stall_spin)
        
        layout.addWidget(timing_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        filler_config = self.config.get("fillers", {})
        self.fillers_enable_check.setChecked(filler_config.get("enabled", True))
        self.filler_start_spin.setValue(filler_config.get("start_delay_ms", 500))
        self.filler_stall_spin.setValue(filler_config.get("stall_threshold_ms", 400))
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "fillers": {
                "enabled": self.fillers_enable_check.isChecked(),
                "start_delay_ms": self.filler_start_spin.value(),
                "stall_threshold_ms": self.filler_stall_spin.value(),
            }
        }
