"""Shared pytest/unittest configuration for the AI VTuber test suite.

The repository contains Windows-only modules (the Win32 foreground-window
identifier and its CLI debugging tool) that must remain importable and
testable on non-Windows CI hosts. ``ctypes.WinDLL`` and the ``wintypes``
module only exist on Windows, so we install minimal stand-ins *before*
those modules are imported. The real detection logic is never stubbed:
tests inject fake bindings instead, and on an actual Windows machine this
shim does nothing at all.
"""

import ctypes
import sys
import types

if sys.platform != "win32":
    if "wintypes" not in sys.modules:
        _wt = types.ModuleType("wintypes")

        class _DWORD(ctypes.c_uint32):
            pass

        _wt.DWORD = _DWORD
        _wt.BOOL = ctypes.c_int
        _wt.HANDLE = ctypes.c_void_p
        _wt.HWND = ctypes.c_void_p
        _wt.HMODULE = ctypes.c_void_p
        _wt.LPWSTR = ctypes.c_wchar_p
        sys.modules["wintypes"] = _wt

    if not hasattr(ctypes, "WinDLL"):
        def _fake_windll(*args, **kwargs):
            raise OSError("WinDLL is only available on Windows")

        ctypes.WinDLL = _fake_windll

    if not hasattr(ctypes, "get_last_error"):
        ctypes.get_last_error = lambda: 0
