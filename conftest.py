"""Ensure Windows-only vision modules are importable on non-Windows hosts.

See tests/conftest.py for the full rationale: this root-level conftest only
installs minimal ``ctypes``/``wintypes`` stand-ins on non-Windows platforms so
that ``ai_vtuber.vision.windows_app_identifier`` (and its CLI) can be imported
and unit-tested with injected fake bindings. On a real Windows 11 machine this
file changes nothing.
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

    if not hasattr(ctypes, "WINFUNCTYPE"):
        # Windows-only calling convention; CFUNCTYPE is equivalent for the
        # purposes of tests that never call real Win32 APIs.
        ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE

    _wt = sys.modules["wintypes"]
    for _attr in ("LPARAM", "WPARAM"):
        if not hasattr(_wt, _attr):
            setattr(_wt, _attr, ctypes.c_ssize_t)
    if not hasattr(_wt, "UINT"):
        _wt.UINT = ctypes.c_uint
