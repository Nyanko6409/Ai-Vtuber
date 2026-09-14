"""AI VTuber - PySide6 Settings Window

Provides a modern Qt-based settings dialog for configuring all VTuber parameters.
Integrates with Live2D rendering by running in a separate window or overlay.

COLOR REFERENCE (Dark Theme):
================================================================================
BACKGROUND COLORS:
- #1e1e2e (Dark Blue-Gray): Main dialog background, tab widget
- #2a2a3a (Medium Dark Gray): Tab buttons, group boxes
- #4a4a6a (Lighter Gray): Selected tab
- #3a3a5a (Hover Gray): Hovered tab
- #252535 (Input Background): Text input fields
- #3b3b4f (Border Color): Borders, separators

BUTTON COLORS:
- #6a80ff (Blue): Primary action button (Save)
- #8a90ff (Lighter Blue): Save button hover
- #4a60c0 (Darker Blue): Cancel button
- #5a70d0 (Medium Blue): Cancel button hover
- #4a4a5a (Disabled Gray): Disabled buttons
- #5a5a6a (Disabled Hover): Disabled button hover

TEXT COLORS:
- #ffffff (White): Primary text, labels
- #a0b0ff (Light Blue): Value labels, titles
- #cccccc (Light Gray): Placeholder text

ACCENT COLORS:
- #3b3b4f (Dark Border): Tab borders, input borders
- #6a80ff (Blue): Focus borders, active elements
================================================================================
"""

import logging
from typing import Optional, Callable
from pathlib import Path
import yaml

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QSlider, QCheckBox, QPushButton,
    QTabWidget, QWidget, QScrollArea, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Modern Qt-based settings dialog for VTuber configuration."""
    
    # Signal emitted when settings are saved
    settings_saved = Signal(dict)
    
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.temp_config: dict = {}
        
        self.setWindowTitle("AI VTuber Settings")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)
        
        # Set modern dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #3b3b4f;
                background-color: #1e1e2e;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #2a2a3a;
                color: #ffffff;
                padding: 10px 20px;
                margin: 2px;
                border-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #4a4a6a;
            }
            QTabBar::tab:hover {
                background-color: #3a3a5a;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3b3b4f;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: #252535;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #a0b0ff;
            }
            QLabel {
                color: #e0e0e0;
                padding: 4px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #2a2a3a;
                border: 1px solid #3b3b4f;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #6a80ff;
            }
            QSlider::groove:horizontal {
                border: 1px solid #3b3b4f;
                height: 8px;
                background: #2a2a3a;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #6a80ff;
                border: 1px solid #3b3b4f;
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #8a90ff;
            }
            QCheckBox {
                spacing: 8px;
                color: #e0e0e0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #3b3b4f;
                background-color: #2a2a3a;
            }
            QCheckBox::indicator:checked {
                background-color: #6a80ff;
                border: 1px solid #6a80ff;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #6a80ff;
            }
            QPushButton {
                background-color: #4a60c0;
                color: white;
                border: none;
                padding: 10px 24px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a70d0;
            }
            QPushButton:pressed {
                background-color: #3a50b0;
            }
            QPushButton#cancelButton {
                background-color: #4a4a5a;
            }
            QPushButton#cancelButton:hover {
                background-color: #5a5a6a;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #1e1e2e;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #3b3b4f;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4b4b5f;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self._setup_ui()
        self._load_temp_config()
    
    def _setup_ui(self) -> None:
        """Set up the UI layout and widgets."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Title
        title_label = QLabel("⚙️ AI VTuber Configuration")
        title_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #a0b0ff; padding: 10px;")
        main_layout.addWidget(title_label)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("font-size: 14px;")
        main_layout.addWidget(self.tab_widget, 1)
        
        # Create tabs
        self._create_audio_tab()
        self._create_stt_tab()
        self._create_tts_tab()
        self._create_llm_tab()
        self._create_avatar_tab()
        self._create_filler_tab()
        self._create_ui_tab()
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Save button
        self.save_button = QPushButton("💾 Save Settings")
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setMinimumHeight(45)
        self.save_button.setFont(QFont("Segoe UI", 12, QFont.Bold))
        button_layout.addWidget(self.save_button)
        
        # Cancel button
        self.cancel_button = QPushButton("❌ Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setMinimumHeight(45)
        self.cancel_button.setFont(QFont("Segoe UI", 12))
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def _create_scroll_area(self, widget: QWidget) -> QScrollArea:
        """Create a scrollable area for a widget."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll
    
    def _create_audio_tab(self) -> None:
        """Create the Audio settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Microphone selection group
        mic_group = QGroupBox("🎤 Input Device")
        mic_layout = QGridLayout(mic_group)
        mic_layout.setSpacing(10)
        
        mic_label = QLabel("Microphone:")
        mic_layout.addWidget(mic_label, 0, 0)
        
        self.mic_combo = QComboBox()
        self.mic_combo.addItems(self._get_microphone_list())
        mic_layout.addWidget(self.mic_combo, 0, 1)
        
        layout.addWidget(mic_group)
        layout.addStretch()
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🎤 Audio")
    
    def _create_stt_tab(self) -> None:
        """Create the STT settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
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
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🗣️ STT")
    
    def _create_tts_tab(self) -> None:
        """Create the TTS settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
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
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🔊 TTS")
    
    def _create_llm_tab(self) -> None:
        """Create the LLM settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
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
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🤖 LLM")
    
    def _create_avatar_tab(self) -> None:
        """Create the Avatar settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
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
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🎭 Avatar")
    
    def _create_filler_tab(self) -> None:
        """Create the Filler words settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
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
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🎬 Fillers")
    
    def _create_ui_tab(self) -> None:
        """Create the UI settings tab for background color, font, and text color."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
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
        
        scroll = self._create_scroll_area(tab)
        self.tab_widget.addTab(scroll, "🎨 UI")
    
    def _get_microphone_list(self) -> list[str]:
        """Get list of available microphones."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            mics = []
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    mics.append(f"{i}: {dev['name']}")
            if not mics:
                mics = ["-1: Default Microphone"]
            return ["-1: Default Microphone"] + mics
        except Exception as e:
            logger.warning(f"Could not query microphones: {e}")
            return ["-1: Default Microphone"]
    
    def _load_temp_config(self) -> None:
        """Load current config into UI widgets."""
        # Audio
        mic_index = self.config.get("audio", {}).get("microphone_index", -1)
        mic_list = self._get_microphone_list()
        for i, mic in enumerate(mic_list):
            if mic.startswith(f"{mic_index}:"):
                self.mic_combo.setCurrentIndex(i)
                break
        
        # STT
        stt_config = self.config.get("stt", {})
        self.stt_model_combo.setCurrentText(stt_config.get("model_size", "base"))
        self.stt_device_combo.setCurrentText(stt_config.get("device", "auto"))
        vad_value = stt_config.get("vad_threshold", 0.5)
        self.vad_slider.setValue(int(vad_value * 10))
        self.vad_value_label.setText(f"{vad_value:.1f}")
        
        # TTS
        tts_config = self.config.get("tts", {})
        self.tts_model_combo.setCurrentText(tts_config.get("model", "KittenML/kitten-tts-nano-0.8-int8"))
        self.tts_voice_combo.setCurrentText(tts_config.get("voice", "Bella"))
        tts_speed = tts_config.get("speed", 1.25)
        self.tts_speed_slider.setValue(int(tts_speed * 100))
        self.tts_speed_value_label.setText(f"{tts_speed:.2f}x")
        self.tts_backend_combo.setCurrentText(tts_config.get("backend", "cuda"))
        
        # LLM
        llm_config = self.config.get("llm", {})
        self.llm_model_edit.setText(llm_config.get("model", ""))
        llm_temp = llm_config.get("temperature", 0.7)
        self.llm_temp_slider.setValue(int(llm_temp * 10))
        self.llm_temp_value_label.setText(f"{llm_temp:.1f}")
        self.llm_stream_check.setChecked(llm_config.get("stream_enabled", True))
        
        # Avatar
        avatar_config = self.config.get("avatar", {})
        self.avatar_model_edit.setText(avatar_config.get("model_path", ""))
        avatar_scale = avatar_config.get("scale", 2.0)
        self.avatar_scale_slider.setValue(int(avatar_scale * 10))
        self.avatar_scale_value_label.setText(f"{avatar_scale:.1f}x")
        
        # Fillers
        filler_config = self.config.get("fillers", {})
        self.fillers_enable_check.setChecked(filler_config.get("enabled", True))
        self.filler_start_spin.setValue(filler_config.get("start_delay_ms", 500))
        self.filler_stall_spin.setValue(filler_config.get("stall_threshold_ms", 400))
        
        # UI
        ui_config = self.config.get("ui", {})
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
    
    def _get_current_config(self) -> dict:
        """Get current configuration from UI widgets."""
        # Get microphone index
        mic_text = self.mic_combo.currentText()
        mic_index = -1
        if ":" in mic_text:
            try:
                mic_index = int(mic_text.split(":")[0])
            except ValueError:
                mic_index = -1
        
        return {
            "audio": {
                "microphone_index": mic_index,
            },
            "stt": {
                "model_size": self.stt_model_combo.currentText(),
                "device": self.stt_device_combo.currentText(),
                "vad_threshold": self.vad_slider.value() / 10.0,
            },
            "tts": {
                "model": self.tts_model_combo.currentText(),
                "voice": self.tts_voice_combo.currentText(),
                "speed": self.tts_speed_slider.value() / 100.0,
                "backend": self.tts_backend_combo.currentText(),
            },
            "llm": {
                "model": self.llm_model_edit.text(),
                "temperature": self.llm_temp_slider.value() / 10.0,
                "stream_enabled": self.llm_stream_check.isChecked(),
            },
            "avatar": {
                "model_path": self.avatar_model_edit.text(),
                "scale": self.avatar_scale_slider.value() / 10.0,
            },
            "fillers": {
                "enabled": self.fillers_enable_check.isChecked(),
                "start_delay_ms": self.filler_start_spin.value(),
                "stall_threshold_ms": self.filler_stall_spin.value(),
            },
            "ui": {
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
            },
        }
    
    @Slot()
    def _on_save(self) -> None:
        """Handle save button click."""
        new_config = self._get_current_config()
        
        # Save to file
        try:
            config_path = Path(__file__).parent.parent / "config.yaml"
            
            # Load existing config to preserve structure
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f)
            
            # Update sections
            for section in ["audio", "stt", "tts", "llm", "avatar", "fillers"]:
                if section in new_config:
                    if section not in existing_config:
                        existing_config[section] = {}
                    existing_config[section].update(new_config[section])
            
            # Write back
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            logger.info("Configuration saved successfully")
            
            # Emit signal with new config
            self.settings_saved.emit(existing_config)
            self.accept()
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")


def show_settings_dialog(config: dict, on_save: Optional[Callable[[dict], None]] = None, parent=None) -> None:
    """Show the settings dialog."""
    import sys
    
    # Check if QApplication exists
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    dialog = SettingsDialog(config, parent=parent)
    
    if on_save:
        dialog.settings_saved.connect(on_save)
    
    dialog.exec()
