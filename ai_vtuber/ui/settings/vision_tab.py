"""AI VTuber - Vision Settings Tab

Provides screen vision configuration for AI assistant's desktop/game watching.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, 
    QGroupBox, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt


class VisionSettingsTab(QWidget):
    """Vision settings tab for on-demand screen capture and analysis."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Enable/Disable vision
        enable_group = QGroupBox("👁️ Screen Vision")
        enable_layout = QVBoxLayout(enable_group)
        enable_layout.setSpacing(10)
        
        self.vision_enabled_check = QCheckBox("Enable Screen Vision")
        self.vision_enabled_check.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        enable_layout.addWidget(self.vision_enabled_check)
        
        enable_desc = QLabel(
            "When enabled, you can ask Airi to look at your screen. "
            "She will take a screenshot and analyze it to understand "
            "what you're doing (playing games, browsing, etc.). This uses LM Studio "
            "with a vision-capable model."
        )
        enable_desc.setWordWrap(True)
        enable_desc.setStyleSheet("color: #888; font-size: 12px; padding: 5px;")
        enable_layout.addWidget(enable_desc)
        
        layout.addWidget(enable_group)
        
        # Capture settings
        capture_group = QGroupBox("📸 Capture Settings")
        capture_layout = QGridLayout(capture_group)
        capture_layout.setSpacing(10)
        
        # Monitor index
        monitor_label = QLabel("Monitor Index:")
        capture_layout.addWidget(monitor_label, 0, 0)
        
        self.vision_monitor_spin = QSpinBox()
        self.vision_monitor_spin.setMinimum(0)
        self.vision_monitor_spin.setMaximum(3)
        self.vision_monitor_spin.setValue(0)
        self.vision_monitor_spin.setToolTip("0 = primary monitor")
        capture_layout.addWidget(self.vision_monitor_spin, 0, 1)
        
        capture_desc = QLabel(
            "Airi uses on-demand screenshots only.\n"
            "No continuous background capture or frame analysis.\n"
            "Just ask her to look at your screen when needed!"
        )
        capture_desc.setWordWrap(True)
        capture_desc.setStyleSheet("color: #888; font-size: 12px; padding: 5px;")
        capture_layout.addWidget(capture_desc, 1, 0, 1, 2)
        
        layout.addWidget(capture_group)
        
        # Advanced settings
        advanced_group = QGroupBox("⚙️ Advanced")
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setSpacing(10)
        
        # Resolution limits - set to 1920x1080 for Full HD screenshots
        resolution_layout = QGridLayout()
        resolution_layout.setSpacing(10)
        
        max_width_label = QLabel("Max Width:")
        resolution_layout.addWidget(max_width_label, 0, 0)
        
        self.vision_max_width_spin = QSpinBox()
        self.vision_max_width_spin.setMinimum(320)
        self.vision_max_width_spin.setMaximum(1920)
        self.vision_max_width_spin.setSingleStep(64)
        self.vision_max_width_spin.setValue(1920)
        self.vision_max_width_spin.setToolTip("Screenshot width (default: 1920 for Full HD)")
        resolution_layout.addWidget(self.vision_max_width_spin, 0, 1)
        
        max_height_label = QLabel("Max Height:")
        resolution_layout.addWidget(max_height_label, 1, 0)
        
        self.vision_max_height_spin = QSpinBox()
        self.vision_max_height_spin.setMinimum(240)
        self.vision_max_height_spin.setMaximum(1080)
        self.vision_max_height_spin.setSingleStep(64)
        self.vision_max_height_spin.setValue(1080)
        self.vision_max_height_spin.setToolTip("Screenshot height (default: 1080 for Full HD)")
        resolution_layout.addWidget(self.vision_max_height_spin, 1, 1)
        
        debug_info = QLabel(
            "Debug logs will show when screenshots are captured and sent to LLM.\n"
            "Check your console for [VISION DEBUG] messages."
        )
        debug_info.setWordWrap(True)
        debug_info.setStyleSheet("color: #0a8; font-size: 11px; padding: 5px; margin-top: 10px;")
        advanced_layout.addLayout(resolution_layout)
        advanced_layout.addWidget(debug_info)
        
        layout.addWidget(advanced_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        vision_config = self.config.get("vision", {})
        
        self.vision_enabled_check.setChecked(vision_config.get("enabled", False))
        self.vision_monitor_spin.setValue(vision_config.get("monitor_index", 0))
        self.vision_max_width_spin.setValue(vision_config.get("max_width", 1920))
        self.vision_max_height_spin.setValue(vision_config.get("max_height", 1080))
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "vision": {
                "enabled": self.vision_enabled_check.isChecked(),
                "monitor_index": self.vision_monitor_spin.value(),
                "max_width": self.vision_max_width_spin.value(),
                "max_height": self.vision_max_height_spin.value(),
            }
        }
