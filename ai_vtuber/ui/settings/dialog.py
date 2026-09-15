"""AI VTuber - Settings Dialog

Main settings dialog that coordinates all configuration tabs.
"""

import logging
from typing import Optional, Callable
from pathlib import Path

try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    HAS_RUAMEL = False
    import yaml

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QWidget, QScrollArea, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

from ..theme import get_settings_base_stylesheet
from .audio_tab import AudioSettingsTab
from .stt_tab import STTSettingsTab
from .tts_tab import TTSSettingsTab
from .llm_tab import LLMSettingsTab
from .avatar_tab import AvatarSettingsTab
from .fillers_tab import FillersSettingsTab
from .ui_tab import UISettingsTab

logger = logging.getLogger("ai_vtuber")


class SettingsDialog(QDialog):
    """Modern Qt-based settings dialog for VTuber configuration."""
    
    # Signal emitted when settings are saved
    settings_saved = Signal(dict)
    
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        
        self.setWindowTitle("AI VTuber Settings")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)
        
        # Set modern dark theme
        self.setStyleSheet(get_settings_base_stylesheet())
        
        self._setup_ui()
        self._load_config_to_ui()
    
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
        self._create_tabs()
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Save button
        self.save_button = QPushButton("💾 Save Settings")
        self.save_button.setObjectName("saveButton")
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
    
    def _create_tabs(self) -> None:
        """Create all settings tabs."""
        # Create tab instances
        self.audio_tab = AudioSettingsTab(self.config)
        self.stt_tab = STTSettingsTab(self.config)
        self.tts_tab = TTSSettingsTab(self.config)
        self.llm_tab = LLMSettingsTab(self.config)
        self.avatar_tab = AvatarSettingsTab(self.config)
        self.fillers_tab = FillersSettingsTab(self.config)
        self.ui_tab = UISettingsTab(self.config)
        
        # Load config into each tab
        self.audio_tab.load_config()
        self.stt_tab.load_config()
        self.tts_tab.load_config()
        self.llm_tab.load_config()
        self.avatar_tab.load_config()
        self.fillers_tab.load_config()
        self.ui_tab.load_config()
        
        # Add tabs to widget with scroll areas
        self.tab_widget.addTab(self._create_scroll_area(self.audio_tab), "🎤 Audio")
        self.tab_widget.addTab(self._create_scroll_area(self.stt_tab), "🗣️ STT")
        self.tab_widget.addTab(self._create_scroll_area(self.tts_tab), "🔊 TTS")
        self.tab_widget.addTab(self._create_scroll_area(self.llm_tab), "🤖 LLM")
        self.tab_widget.addTab(self._create_scroll_area(self.avatar_tab), "🎭 Avatar")
        self.tab_widget.addTab(self._create_scroll_area(self.fillers_tab), "🎬 Fillers")
        self.tab_widget.addTab(self._create_scroll_area(self.ui_tab), "🎨 UI")
    
    def _create_scroll_area(self, widget: QWidget) -> QScrollArea:
        """Create a scrollable area for a widget."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll
    
    def _load_config_to_ui(self) -> None:
        """Load current config into UI widgets (already done in tab creation)."""
        # Config is loaded during tab creation
        pass
    
    def _get_current_config(self) -> dict:
        """Get current configuration from all tabs."""
        config = {}
        config.update(self.audio_tab.get_config())
        config.update(self.stt_tab.get_config())
        config.update(self.tts_tab.get_config())
        config.update(self.llm_tab.get_config())
        config.update(self.avatar_tab.get_config())
        config.update(self.fillers_tab.get_config())
        config.update(self.ui_tab.get_config())
        return config
    
    @Slot()
    def _on_save(self) -> None:
        """Handle save button click."""
        new_config = self._get_current_config()
        
        # Save to file - config.yaml is in project root (parent of ai_vtuber)
        try:
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
            
            if HAS_RUAMEL:
                # Use ruamel.yaml to preserve comments and formatting
                yaml_rt = YAML()
                yaml_rt.preserve_quotes = True
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml_rt.load(f) or {}
                
                if not isinstance(existing_config, dict):
                    raise ValueError("config.yaml must contain a YAML mapping/object")
                
                # Update sections (including "ui")
                for section in ["audio", "stt", "tts", "llm", "avatar", "fillers", "ui"]:
                    if section in new_config:
                        if section not in existing_config:
                            existing_config[section] = {}
                        existing_config[section].update(new_config[section])
                
                # Write back atomically with backup
                backup_path = config_path.with_suffix(".yaml.bak")
                temp_path = config_path.with_suffix(".yaml.tmp")
                
                # Create backup
                if config_path.exists():
                    import shutil
                    shutil.copy2(config_path, backup_path)
                
                # Write to temp file first
                with open(temp_path, 'w', encoding='utf-8') as f:
                    yaml_rt.dump(existing_config, f)
                
                # Atomically replace original
                temp_path.replace(config_path)
            else:
                # Fallback to PyYAML (loses comments but still works)
                # Load existing config to preserve structure
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}
                
                if not isinstance(existing_config, dict):
                    raise ValueError("config.yaml must contain a YAML mapping/object")
                
                # Update sections (including "ui")
                for section in ["audio", "stt", "tts", "llm", "avatar", "fillers", "ui"]:
                    if section in new_config:
                        if section not in existing_config:
                            existing_config[section] = {}
                        existing_config[section].update(new_config[section])
                
                # Write back atomically with backup
                backup_path = config_path.with_suffix(".yaml.bak")
                temp_path = config_path.with_suffix(".yaml.tmp")
                
                # Create backup
                if config_path.exists():
                    import shutil
                    shutil.copy2(config_path, backup_path)
                
                # Write to temp file first
                with open(temp_path, 'w', encoding='utf-8') as f:
                    yaml.dump(existing_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                
                # Atomically replace original
                temp_path.replace(config_path)
            
            logger.info("Configuration saved successfully")
            
            # Emit signal with new config
            self.settings_saved.emit(existing_config)
            self.accept()
            
        except Exception as e:
            logger.exception("Failed to save config")
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save configuration:\n\n{e}"
            )


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
