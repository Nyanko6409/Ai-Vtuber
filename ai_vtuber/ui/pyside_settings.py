"""AI VTuber - Settings (Compatibility Wrapper)

This module provides backward compatibility for imports from pyside_settings.
The actual implementation has been moved to settings/dialog.py.
"""

from .settings.dialog import SettingsDialog, show_settings_dialog

__all__ = ["SettingsDialog", "show_settings_dialog"]
