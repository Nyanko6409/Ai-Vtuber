"""AI VTuber - UI Settings Tab

Provides window transparency, background color, text color, and font configuration.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox, QCheckBox, QSpinBox, QComboBox


class UISettingsTab(QWidget):
    """UI settings tab for window appearance configuration."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Transparency setting
        transparent_group = QGroupBox("🪟 Window Transparency")
        transparent_layout = QVBoxLayout(transparent_group)
        transparent_layout.setSpacing(10)
        
        self.transparent_check = QCheckBox("Enable Transparent Background (Click-Through)")
        self.transparent_check.setChecked(self.config.get("ui", {}).get("transparent", False))
        self.transparent_check.setToolTip(
            "Makes the window background transparent and click-through, showing only the avatar.\n"
            "Mouse clicks will pass through to windows behind the avatar.\n"
            "Requires a compositing window manager (GNOME/KDE default, or picom on tiling WMs).\n"
            "In OBS: Use 'Window Capture (Xcomposite)' and check 'Allow Transparency'."
        )
        transparent_layout.addWidget(self.transparent_check)
        
        transparent_info = QLabel(
            "ℹ️ Note: When enabled, the window becomes frameless and clicks pass through to windows behind.\n"
            "   Press ESC to quit the application. Background color is ignored in this mode."
        )
        transparent_info.setWordWrap(True)
        transparent_info.setStyleSheet("color: #a0b0ff; font-size: 12px;")
        transparent_layout.addWidget(transparent_info)
        
        layout.addWidget(transparent_group)
        
        # Background color settings
        bg_group = QGroupBox("🎨 Background Color")
        bg_layout = QGridLayout(bg_group)
        bg_layout.setSpacing(10)
        
        bg_label = QLabel("Background Color (RGB):")
        bg_layout.addWidget(bg_label, 0, 0)
        
        bg_colors = self.config.get("ui", {}).get("background_color", [0, 0, 0])
        
        self.bg_r_spin = QSpinBox()
        self.bg_r_spin.setMinimum(0)
        self.bg_r_spin.setMaximum(255)
        self.bg_r_spin.setValue(bg_colors[0] if len(bg_colors) > 0 else 0)
        self.bg_r_spin.setPrefix("R: ")
        bg_layout.addWidget(self.bg_r_spin, 0, 1)
        
        self.bg_g_spin = QSpinBox()
        self.bg_g_spin.setMinimum(0)
        self.bg_g_spin.setMaximum(255)
        self.bg_g_spin.setValue(bg_colors[1] if len(bg_colors) > 1 else 0)
        self.bg_g_spin.setPrefix("G: ")
        bg_layout.addWidget(self.bg_g_spin, 0, 2)
        
        self.bg_b_spin = QSpinBox()
        self.bg_b_spin.setMinimum(0)
        self.bg_b_spin.setMaximum(255)
        self.bg_b_spin.setValue(bg_colors[2] if len(bg_colors) > 2 else 0)
        self.bg_b_spin.setPrefix("B: ")
        bg_layout.addWidget(self.bg_b_spin, 0, 3)
        
        layout.addWidget(bg_group)
        
        # Text color settings
        text_group = QGroupBox("📝 Text Color")
        text_layout = QGridLayout(text_group)
        text_layout.setSpacing(10)
        
        text_label = QLabel("Text Color (RGB):")
        text_layout.addWidget(text_label, 0, 0)
        
        text_colors = self.config.get("ui", {}).get("text_color", [255, 255, 255])
        
        self.text_r_spin = QSpinBox()
        self.text_r_spin.setMinimum(0)
        self.text_r_spin.setMaximum(255)
        self.text_r_spin.setValue(text_colors[0] if len(text_colors) > 0 else 255)
        self.text_r_spin.setPrefix("R: ")
        text_layout.addWidget(self.text_r_spin, 0, 1)
        
        self.text_g_spin = QSpinBox()
        self.text_g_spin.setMinimum(0)
        self.text_g_spin.setMaximum(255)
        self.text_g_spin.setValue(text_colors[1] if len(text_colors) > 1 else 255)
        self.text_g_spin.setPrefix("G: ")
        text_layout.addWidget(self.text_g_spin, 0, 2)
        
        self.text_b_spin = QSpinBox()
        self.text_b_spin.setMinimum(0)
        self.text_b_spin.setMaximum(255)
        self.text_b_spin.setValue(text_colors[2] if len(text_colors) > 2 else 255)
        self.text_b_spin.setPrefix("B: ")
        text_layout.addWidget(self.text_b_spin, 0, 3)
        
        layout.addWidget(text_group)
        
        # Font settings
        font_group = QGroupBox("🔤 Font Settings")
        font_layout = QVBoxLayout(font_group)
        font_layout.setSpacing(15)
        
        # Font family
        font_family_label = QLabel("Font Family:")
        font_layout.addWidget(font_family_label)
        
        self.font_family_combo = QComboBox()
        self.font_family_combo.setEditable(True)
        common_fonts = [
            "Arial", "Times New Roman", "Segoe UI", "Calibri", "Verdana",
            "Georgia", "Tahoma", "Trebuchet MS", "Impact", "Comic Sans MS"
        ]
        self.font_family_combo.addItems(common_fonts)
        
        current_font = self.config.get("ui", {}).get("font_family", "Arial")
        index = self.font_family_combo.findText(current_font)
        if index >= 0:
            self.font_family_combo.setCurrentIndex(index)
        else:
            self.font_family_combo.setCurrentText(current_font)
        
        font_layout.addWidget(self.font_family_combo)
        
        # Font size
        font_size_label = QLabel("Font Size:")
        font_layout.addWidget(font_size_label)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimum(8)
        self.font_size_spin.setMaximum(72)
        self.font_size_spin.setValue(self.config.get("ui", {}).get("font_size", 14))
        self.font_size_spin.setSuffix(" px")
        font_layout.addWidget(self.font_size_spin)
        
        layout.addWidget(font_group)
        layout.addStretch()
    
    def load_config(self):
        """Load configuration into UI widgets."""
        ui_config = self.config.get("ui", {})
        self.transparent_check.setChecked(ui_config.get("transparent", False))
        bg_colors = ui_config.get("background_color", [0, 0, 0])
        self.bg_r_spin.setValue(bg_colors[0] if len(bg_colors) > 0 else 0)
        self.bg_g_spin.setValue(bg_colors[1] if len(bg_colors) > 1 else 0)
        self.bg_b_spin.setValue(bg_colors[2] if len(bg_colors) > 2 else 0)
        
        text_colors = ui_config.get("text_color", [255, 255, 255])
        self.text_r_spin.setValue(text_colors[0] if len(text_colors) > 0 else 255)
        self.text_g_spin.setValue(text_colors[1] if len(text_colors) > 1 else 255)
        self.text_b_spin.setValue(text_colors[2] if len(text_colors) > 2 else 255)
        
        current_font = ui_config.get("font_family", "Arial")
        index = self.font_family_combo.findText(current_font)
        if index >= 0:
            self.font_family_combo.setCurrentIndex(index)
        else:
            self.font_family_combo.setCurrentText(current_font)
        self.font_size_spin.setValue(ui_config.get("font_size", 14))
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
        return {
            "ui": {
                "transparent": self.transparent_check.isChecked(),
                "background_color": [
                    self.bg_r_spin.value(),
                    self.bg_g_spin.value(),
                    self.bg_b_spin.value(),
                ],
                "text_color": [
                    self.text_r_spin.value(),
                    self.text_g_spin.value(),
                    self.text_b_spin.value(),
                ],
                "font_family": self.font_family_combo.currentText(),
                "font_size": self.font_size_spin.value(),
            }
        }
