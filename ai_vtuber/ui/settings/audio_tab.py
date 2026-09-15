"""AI VTuber - Audio Settings Tab

Provides microphone selection and audio input configuration.
"""

import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QGroupBox, QScrollArea

logger = logging.getLogger("ai_vtuber")


class AudioSettingsTab(QWidget):
    """Audio settings tab for microphone and input device configuration."""
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        layout = QVBoxLayout(self)
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
        
        # Wrap in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    
    def _get_microphone_list(self) -> list[str]:
        """Get list of available microphones."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            mics = [
                f"{i}: {dev['name']}"
                for i, dev in enumerate(devices)
                if dev["max_input_channels"] > 0
            ]
            return ["-1: Default Microphone", *mics]
        except Exception as e:
            logger.warning(f"Could not query microphones: {e}")
            return ["-1: Default Microphone"]
    
    def load_config(self):
        """Load configuration into UI widgets."""
        mic_index = self.config.get("audio", {}).get("microphone_index", -1)
        mic_list = self._get_microphone_list()
        for i, mic in enumerate(mic_list):
            if mic.startswith(f"{mic_index}:"):
                self.mic_combo.setCurrentIndex(i)
                break
    
    def get_config(self) -> dict:
        """Get current configuration from UI widgets."""
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
            }
        }
