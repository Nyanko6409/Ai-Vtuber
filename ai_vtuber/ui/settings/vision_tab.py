"""AI VTuber - Vision Settings Tab

Provides screen vision configuration for AI assistant's desktop/game watching.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QLineEdit, 
    QGroupBox, QSlider, QCheckBox, QComboBox, QDoubleSpinBox,
    QSpinBox
)
from PySide6.QtCore import Qt


class VisionSettingsTab(QWidget):
    """Vision settings tab for screen capture and analysis configuration."""
    
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
            "When enabled, Airi will periodically analyze your screen to understand "
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
        
        # Source selection
        source_label = QLabel("Capture Source:")
        capture_layout.addWidget(source_label, 0, 0)
        
        self.vision_source_combo = QComboBox()
        self.vision_source_combo.addItems(["screen", "window"])
        self.vision_source_combo.setToolTip("Screen: entire monitor | Window: specific window (future)")
        capture_layout.addWidget(self.vision_source_combo, 0, 1)
        
        # Monitor index
        monitor_label = QLabel("Monitor Index:")
        capture_layout.addWidget(monitor_label, 1, 0)
        
        self.vision_monitor_spin = QSpinBox()
        self.vision_monitor_spin.setMinimum(0)
        self.vision_monitor_spin.setMaximum(3)
        self.vision_monitor_spin.setValue(0)
        self.vision_monitor_spin.setToolTip("0 = primary monitor")
        capture_layout.addWidget(self.vision_monitor_spin, 1, 1)
        
        # Capture interval
        capture_interval_label = QLabel("Capture Interval (seconds):")
        capture_layout.addWidget(capture_interval_label, 2, 0)
        
        self.vision_capture_interval_spin = QDoubleSpinBox()
        self.vision_capture_interval_spin.setMinimum(0.1)
        self.vision_capture_interval_spin.setMaximum(10.0)
        self.vision_capture_interval_spin.setSingleStep(0.1)
        self.vision_capture_interval_spin.setValue(0.5)
        self.vision_capture_interval_spin.setToolTip("How often to capture the screen")
        capture_layout.addWidget(self.vision_capture_interval_spin, 2, 1)
        
        layout.addWidget(capture_group)
        
        # Analysis settings
        analysis_group = QGroupBox("🧠 Analysis Settings")
        analysis_layout = QGridLayout(analysis_group)
        analysis_layout.setSpacing(10)
        
        # Analysis interval
        analysis_interval_label = QLabel("Analysis Interval (seconds):")
        analysis_layout.addWidget(analysis_interval_label, 0, 0)
        
        self.vision_analysis_interval_spin = QDoubleSpinBox()
        self.vision_analysis_interval_spin.setMinimum(1.0)
        self.vision_analysis_interval_spin.setMaximum(60.0)
        self.vision_analysis_interval_spin.setSingleStep(1.0)
        self.vision_analysis_interval_spin.setValue(5.0)
        self.vision_analysis_interval_spin.setToolTip("Minimum time between LLM analyses")
        analysis_layout.addWidget(self.vision_analysis_interval_spin, 0, 1)
        
        # Change detection
        self.vision_change_detection_check = QCheckBox("Enable Change Detection")
        self.vision_change_detection_check.setToolTip("Skip frames with no significant changes")
        analysis_layout.addWidget(self.vision_change_detection_check, 1, 0, 1, 2)
        
        # Change threshold
        threshold_label = QLabel("Change Threshold:")
        analysis_layout.addWidget(threshold_label, 2, 0)
        
        self.vision_threshold_spin = QDoubleSpinBox()
        self.vision_threshold_spin.setMinimum(0.01)
        self.vision_threshold_spin.setMaximum(1.0)
        self.vision_threshold_spin.setSingleStep(0.01)
        self.vision_threshold_spin.setValue(0.15)
        self.vision_threshold_spin.setToolTip("Fraction of pixels that must change (0.0-1.0)")
        analysis_layout.addWidget(self.vision_threshold_spin, 2, 1)
        
        layout.addWidget(analysis_group)
        
        # Advanced settings
        advanced_group = QGroupBox("⚙️ Advanced")
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setSpacing(10)
        
        # On-demand mode (CRITICAL setting)
        self.vision_on_demand_check = QCheckBox("On-Demand Mode Only (Recommended)")
        self.vision_on_demand_check.setToolTip(
            "When enabled: Airi only looks at the screen when you ask something.\n"
            "When disabled: Continuous background capture (can cause performance issues)."
        )
        self.vision_on_demand_check.setChecked(True)  # Default to recommended setting
        advanced_layout.addWidget(self.vision_on_demand_check)
        
        # OCR (reserved)
        self.vision_ocr_check = QCheckBox("Enable OCR (Reserved for future use)")
        self.vision_ocr_check.setEnabled(False)  # Not implemented yet
        advanced_layout.addWidget(self.vision_ocr_check)
        
        # Game cache
        self.vision_game_cache_check = QCheckBox("Enable Game Entity Cache")
        self.vision_game_cache_check.setToolTip("Cache recognized game names, characters, locations")
        advanced_layout.addWidget(self.vision_game_cache_check)
        
        # Inject into conversation
        self.vision_inject_check = QCheckBox("Auto-inject Visual Context into Conversation")
        self.vision_inject_check.setToolTip(
            "Automatically share screen observations in chat.\n"
            "Only works when On-Demand Mode is disabled."
        )
        advanced_layout.addWidget(self.vision_inject_check)
        
        # Resolution limits
        resolution_layout = QGridLayout()
        resolution_layout.setSpacing(10)
        
        max_width_label = QLabel("Max Width:")
        resolution_layout.addWidget(max_width_label, 0, 0)
        
        self.vision_max_width_spin = QSpinBox()
        self.vision_max_width_spin.setMinimum(320)
        self.vision_max_width_spin.setMaximum(1920)
        self.vision_max_width_spin.setSingleStep(64)
        self.vision_max_width_spin.setValue(1280)
        resolution_layout.addWidget(self.vision_max_width_spin, 0, 1)
        
        max_height_label = QLabel("Max Height:")
        resolution_layout.addWidget(max_height_label, 1, 0)
        
        self.vision_max_height_spin = QSpinBox()
        self.vision_max_height_spin.setMinimum(240)
        self.vision_max_height_spin.setMaximum(1080)
        self.vision_max_height_spin.setSingleStep(64)
        self.vision_max_height_spin.setValue(720)
        resolution_layout.addWidget(self.vision_max_height_spin, 1, 1)
        
        advanced_layout.addLayout(resolution_layout)
        
        layout.addWidget(advanced_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        vision_config = self.config.get("vision", {})
        
        self.vision_enabled_check.setChecked(vision_config.get("enabled", False))
        self.vision_source_combo.setCurrentText(vision_config.get("source", "screen"))
        self.vision_monitor_spin.setValue(vision_config.get("monitor_index", 0))
        self.vision_capture_interval_spin.setValue(vision_config.get("capture_interval", 2.0))
        self.vision_analysis_interval_spin.setValue(vision_config.get("analysis_interval", 10.0))
        self.vision_change_detection_check.setChecked(vision_config.get("change_detection", True))
        self.vision_threshold_spin.setValue(vision_config.get("change_threshold", 0.20))
        self.vision_on_demand_check.setChecked(vision_config.get("on_demand_only", True))
        self.vision_ocr_check.setChecked(vision_config.get("ocr_enabled", False))
        self.vision_game_cache_check.setChecked(vision_config.get("game_cache_enabled", True))
        self.vision_inject_check.setChecked(vision_config.get("inject_into_conversation", False))
        self.vision_max_width_spin.setValue(vision_config.get("max_width", 1280))
        self.vision_max_height_spin.setValue(vision_config.get("max_height", 720))
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "vision": {
                "enabled": self.vision_enabled_check.isChecked(),
                "source": self.vision_source_combo.currentText(),
                "monitor_index": self.vision_monitor_spin.value(),
                "capture_interval": self.vision_capture_interval_spin.value(),
                "analysis_interval": self.vision_analysis_interval_spin.value(),
                "change_detection": self.vision_change_detection_check.isChecked(),
                "change_threshold": self.vision_threshold_spin.value(),
                "on_demand_only": self.vision_on_demand_check.isChecked(),
                "ocr_enabled": self.vision_ocr_check.isChecked(),
                "game_cache_enabled": self.vision_game_cache_check.isChecked(),
                "inject_into_conversation": self.vision_inject_check.isChecked(),
                "max_width": self.vision_max_width_spin.value(),
                "max_height": self.vision_max_height_spin.value(),
            }
        }
