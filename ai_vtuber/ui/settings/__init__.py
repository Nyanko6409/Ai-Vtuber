"""AI VTuber - Settings Module

Provides configuration dialogs and tabs for all VTuber parameters.
"""

from .dialog import SettingsDialog, show_settings_dialog
from .audio_tab import AudioSettingsTab
from .stt_tab import STTSettingsTab
from .tts_tab import TTSSettingsTab
from .llm_tab import LLMSettingsTab
from .avatar_tab import AvatarSettingsTab
from .fillers_tab import FillersSettingsTab
from .ui_tab import UISettingsTab

__all__ = [
    "SettingsDialog",
    "show_settings_dialog",
    "AudioSettingsTab",
    "STTSettingsTab",
    "TTSSettingsTab",
    "LLMSettingsTab",
    "AvatarSettingsTab",
    "FillersSettingsTab",
    "UISettingsTab",
]
