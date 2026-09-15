"""AI VTuber - Qt Main Window (Compatibility Wrapper)

This module provides backward compatibility for imports from qt_main_window.
The actual implementation has been moved to main_window.py.
"""

from .main_window import QtMainWindow

__all__ = ["QtMainWindow"]
