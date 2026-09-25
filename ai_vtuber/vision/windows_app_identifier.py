"""AI VTuber - Windows 11 Foreground Application Identifier

Windows-11-only component that resolves the application currently in the
foreground on the desktop *before* vision analysis runs. It uses native
Win32 user32/kernel32 APIs (via ctypes) and the Windows Toolhelp snapshot
API to derive:

    - application name   (friendly display name, resolved from the actual
                          process executable - never from the vision model)
    - process name       (e.g. "chrome.exe")
    - window title       (e.g. "GitHub - Google Chrome")
    - process ID         (PID owning the foreground window)
    - window handle      (HWND as a plain integer)

Public API:
    get_active_application() -> Optional[Dict[str, Any]]

Design notes:
    * No pywin32 dependency: everything is done with stdlib ``ctypes`` so
      the module works on any Python install on Windows 11.
    * The Win32 bindings are created lazily (and can be injected for tests),
      so importing this module on a non-Windows machine never raises.
    * All failure modes (no foreground window, inaccessible process,
      permission errors, unknown executable) return a best-effort dict or
      ``None`` - they never raise into the vision pipeline.
    * This module intentionally has NO cross-platform abstraction: it is
      Windows 11 specific, per project scope.
"""

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Windows error codes we care about when opening processes.
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87
_ERROR_OPEN_FAILED = 24  # ERROR_TOO_MANY_OPEN_FILES / generic open failure

# Process access right needed only to read the image file name.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Toolhelp snapshot flags.
_TH32CS_SNAPPROCESS = 0x00000002

_MAX_PATH_LOCAL = 260


class _MODULEENTRY32W(ctypes.Structure):
    """Corresponds to Win32 MODULEENTRY32W (unicode) from tlhelp32.h."""
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32Module", wintypes.HMODULE),
        ("th32ProcessID", wintypes.DWORD),
        ("GlcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * _MAX_PATH_LOCAL),
    ]


class _PROCESSENTRY32W(ctypes.Structure):
    """Corresponds to Win32 PROCESSENTRY32W (unicode) from tlhelp32.h."""
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("th32Threads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class Win32Bindings:
    """Lazily-created container for the user32/kernel32 functions used here.

    Kept as an injectable class so unit tests can supply a mock without
    touching real Windows APIs.
    """

    def __init__(self):
        self._loaded = False
        self._load_lock = threading.Lock()
        self.GetForegroundWindow = None
        self.GetWindowTextW = None
        self.GetWindowTextLengthW = None
        self.GetWindowThreadProcessId = None
        self.IsWindow = None
        self.OpenProcess = None
        self.CloseHandle = None
        self.QueryFullProcessImageNameW = None
        self.CreateToolhelp32Snapshot = None
        self.Module32FirstW = None
        self.Module32NextW = None
        self.Process32FirstW = None
        self.Process32NextW = None
        self.GetLastError = None

    def load(self) -> bool:
        """Load the Win32 libraries and bind function prototypes.

        Returns True on success, False if not running on Windows or the
        bindings could not be created. Never raises.
        """
        if self._loaded:
            return True
        with self._load_lock:
            if self._loaded:
                return True
            if sys.platform != "win32":
                return False
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

                user32.GetForegroundWindow.restype = wintypes.HWND
                user32.GetForegroundWindow.argtypes = []

                user32.GetWindowTextW.restype = ctypes.c_int
                user32.GetWindowTextW.argtypes = [
                    wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
                ]

                user32.GetWindowTextLengthW.restype = ctypes.c_int
                user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]

                user32.GetWindowThreadProcessId.restype = wintypes.DWORD
                user32.GetWindowThreadProcessId.argtypes = [
                    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
                ]

                user32.IsWindow.restype = wintypes.BOOL
                user32.IsWindow.argtypes = [wintypes.HWND]

                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.OpenProcess.argtypes = [
                    wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
                ]

                kernel32.CloseHandle.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

                kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
                kernel32.QueryFullProcessImageNameW.argtypes = [
                    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                    ctypes.POINTER(wintypes.DWORD),
                ]

                kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
                kernel32.CreateToolhelp32Snapshot.argtypes = [
                    wintypes.DWORD, wintypes.DWORD
                ]

                kernel32.Module32FirstW.restype = wintypes.BOOL
                kernel32.Module32FirstW.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W)
                ]

                kernel32.Module32NextW.restype = wintypes.BOOL
                kernel32.Module32NextW.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W)
                ]

                kernel32.Process32FirstW.restype = wintypes.BOOL
                kernel32.Process32FirstW.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)
                ]

                kernel32.Process32NextW.restype = wintypes.BOOL
                kernel32.Process32NextW.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)
                ]

                self.GetForegroundWindow = user32.GetForegroundWindow
                self.GetWindowTextW = user32.GetWindowTextW
                self.GetWindowTextLengthW = user32.GetWindowTextLengthW
                self.GetWindowThreadProcessId = user32.GetWindowThreadProcessId
                self.IsWindow = user32.IsWindow
                self.OpenProcess = kernel32.OpenProcess
                self.CloseHandle = kernel32.CloseHandle
                self.QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
                self.CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
                self.Module32FirstW = kernel32.Module32FirstW
                self.Module32NextW = kernel32.Module32NextW
                self.Process32FirstW = kernel32.Process32FirstW
                self.Process32NextW = kernel32.Process32NextW
                self.GetLastError = kernel32.GetLastError

                self._loaded = True
                return True
            except Exception as e:  # pragma: no cover - Windows-only path
                logger.warning(f"Failed to load Win32 bindings: {e}")
                return False


# Module-level default bindings (lazily loaded). Tests may either patch
# ``get_active_application(bindings=...)`` directly or monkeypatch this
# object's attributes.
_bindings = Win32Bindings()

# Small cache of friendly application names keyed by lowercase exe name,
# populated from the main module's base name (e.g. "chrome.exe" -> "Chrome").
_app_name_cache: Dict[str, str] = {}


def _normalize_hwnd(hwnd: Any) -> int:
    """Coerce whatever ctypes returns for HWND into a plain int (or 0)."""
    if hwnd is None:
        return 0
    if isinstance(hwnd, int):
        return hwnd
    try:
        return int(ctypes.cast(hwnd, ctypes.c_void_p).value or 0)
    except Exception:
        try:
            return int(hwnd)
        except Exception:
            return 0


def _get_window_title(b: Win32Bindings, hwnd: int) -> str:
    """Return the foreground window title via GetWindowTextW (empty on failure)."""
    try:
        length = b.GetWindowTextLengthW(wintypes.HWND(hwnd))
        if not length or length < 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        written = b.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
        if written <= 0:
            return ""
        return buf.value or ""
    except Exception as e:
        logger.debug(f"GetWindowText failed for HWND {hwnd}: {e}")
        return ""


def _get_pid(b: Win32Bindings, hwnd: int) -> Optional[int]:
    """Return the PID owning the window via GetWindowThreadProcessId."""
    try:
        pid = wintypes.DWORD(0)
        b.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        value = int(pid.value)
        return value if value > 0 else None
    except Exception as e:
        logger.debug(f"GetWindowThreadProcessId failed for HWND {hwnd}: {e}")
        return None


def _query_image_path(b: Win32Bindings, pid: int) -> Optional[str]:
    """QueryFullProcessImageNameW with limited rights; None on any failure."""
    handle = None
    try:
        handle = b.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0
            logger.debug(
                f"OpenProcess failed for PID {pid} (error={err}); "
                "process inaccessible or exited"
            )
            return None
        buf = ctypes.create_unicode_buffer(_MAX_PATH_LOCAL * 2)
        size = wintypes.DWORD(buf._length_)
        ok = b.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        if not ok:
            logger.debug(f"QueryFullProcessImageNameW failed for PID {pid}")
            return None
        return buf.value or None
    except Exception as e:
        logger.debug(f"Process image lookup error for PID {pid}: {e}")
        return None
    finally:
        if handle:
            try:
                b.CloseHandle(handle)
            except Exception:
                pass


def _toolhelp_primary_module_path(b: Win32Bindings, pid: int) -> Optional[str]:
    """Fallback: enumerate modules of ``pid`` via Toolhelp snapshot.

    Used when QueryFullProcessImageNameW fails (older drivers, some
    protected processes). Requires SeDebugPrivilege for other users'
    processes; failures are handled silently.
    """
    snap = None
    try:
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        TH32CS_SNAPMODULE = 0x00000008
        TH32CS_SNAPMODULE32 = 0x00000010
        snap = b.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
        if not snap or ctypes.cast(snap, ctypes.c_void_p).value == INVALID_HANDLE_VALUE:
            return None

        entry = _MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(_MODULEENTRY32W)
        found = b.Module32FirstW(snap, ctypes.byref(entry))
        while found:
            if int(entry.th32ProcessID) == pid:
                path = entry.szExePath or ""
                if path:
                    return path
            found = b.Module32NextW(snap, ctypes.byref(entry))
        return None
    except Exception as e:
        logger.debug(f"Toolhelp module lookup failed for PID {pid}: {e}")
        return None
    finally:
        if snap:
            try:
                b.CloseHandle(snap)
            except Exception:
                pass


def _toolhelp_process_name(b: Win32Bindings, pid: int) -> Optional[str]:
    """Last-resort fallback: szExeFile from a process snapshot."""
    snap = None
    try:
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        snap = b.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snap or ctypes.cast(snap, ctypes.c_void_p).value == INVALID_HANDLE_VALUE:
            return None
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not b.Process32FirstW or not b.Process32NextW:
            return None
        found = b.Process32FirstW(snap, ctypes.byref(entry))
        while found:
            if int(entry.th32ProcessID) == pid:
                return entry.szExeFile or None
            found = b.Process32NextW(snap, ctypes.byref(entry))
        return None
    except Exception as e:
        logger.debug(f"Toolhelp process-name lookup failed for PID {pid}: {e}")
        return None
    finally:
        if snap:
            try:
                b.CloseHandle(snap)
            except Exception:
                pass


def _basename(path: str) -> str:
    """Windows-style basename that also accepts backslashes (works anywhere)."""
    trimmed = path.rstrip("\\/")
    idx = max(trimmed.rfind("\\"), trimmed.rfind("/"))
    return trimmed[idx + 1:] if idx >= 0 else trimmed


def _resolve_display_name(exe_path: Optional[str], exe_name: Optional[str]) -> str:
    """Resolve a friendly application name from the actual executable.

    Uses the main module's base name minus extension (e.g.
    ``C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`` ->
    ``Chrome``). This never asks the vision model or LLM - it comes from
    the real Windows process image. Unknown executables simply yield
    their own base name.
    """
    name = None
    if exe_path:
        name = _basename(exe_path)
    if not name and exe_name:
        name = exe_name
    if not name:
        return "Unknown Application"

    key = name.lower()
    cached = _app_name_cache.get(key)
    if cached:
        return cached

    stem = name[:-4] if key.endswith(".exe") else name
    display = stem.replace("_", " ").strip() or "Unknown Application"
    # Title-case simple names ("chrome" -> "Chrome"), leave acronyms intact.
    if display.islower():
        display = display.capitalize()
    _app_name_cache[key] = display
    return display


def get_active_application(
    bindings: Optional[Win32Bindings] = None
) -> Optional[Dict[str, Any]]:
    """Identify the current Windows 11 foreground application.

    Returns a dict with:
        {
            "application":  friendly name resolved from the process exe,
            "process_name": e.g. "chrome.exe",
            "window_title": e.g. "GitHub - Google Chrome",
            "pid":          int process id,
            "hwnd":         int window handle,
        }

    Returns ``None`` only when there is no foreground window at all or the
    OS bindings cannot be used (non-Windows host). Partial results are
    returned on process-lookup failure / inaccessible process / permission
    errors, with best-effort values (never raises).
    """
    b = bindings or _bindings
    if not b.load():
        logger.debug("Win32 bindings unavailable; active-app detection skipped")
        return None

    # 1. Foreground window handle.
    try:
        raw_hwnd = b.GetForegroundWindow()
    except Exception as e:
        logger.debug(f"GetForegroundWindow failed: {e}")
        return None

    hwnd = _normalize_hwnd(raw_hwnd)
    if not hwnd:
        # No foreground window (e.g. full-screen exclusive app, secure desktop).
        logger.debug("No foreground window detected")
        return None

    # 2. Window title.
    window_title = _get_window_title(b, hwnd)

    # 3. Owning process id.
    pid = _get_pid(b, hwnd)
    if pid is None:
        return {
            "application": "Unknown Application",
            "process_name": None,
            "window_title": window_title,
            "pid": None,
            "hwnd": hwnd,
        }

    # 4. Executable path from the actual process (primary then fallbacks).
    exe_path = _query_image_path(b, pid)
    if not exe_path:
        exe_path = _toolhelp_primary_module_path(b, pid)
    if not exe_path:
        fallback_name = _toolhelp_process_name(b, pid)
        if fallback_name:
            exe_path = fallback_name  # name only; still resolves display name

    process_name = _basename(exe_path) if exe_path else None
    application = _resolve_display_name(exe_path, process_name)

    result: Dict[str, Any] = {
        "application": application,
        "process_name": process_name,
        "window_title": window_title,
        "pid": pid,
        "hwnd": hwnd,
    }
    # Extra diagnostic field (full executable path when available). It is
    # additive only - existing consumers read the five documented keys and
    # ignore this one.
    if exe_path:
        result["exe_path"] = exe_path
    return result


def set_bindings(bindings: "Win32Bindings") -> None:
    """Replace the module-level default Win32 bindings.

    Intended for debugging tooling and unit tests so ``get_active_application()``
    can run against injected/mock API bindings without duplicating any of the
    detection logic below. Pass a real ``Win32Bindings()`` instance to restore
    normal behaviour.
    """
    global _bindings
    _bindings = bindings


def get_bindings() -> "Win32Bindings":
    """Return the currently-used module-level Win32 bindings object."""
    return _bindings


# ---------------------------------------------------------------------------
# Debug report (used by ``python main.py --debug``)
#
# Pure presentation on top of ``get_active_application()`` - contains NO
# Win32 detection logic of its own, so it can never diverge from what the
# VisionManager actually sees.
# ---------------------------------------------------------------------------

REASON_NO_BINDINGS = "Win32 bindings unavailable (Windows 11 required)"
REASON_NO_FOREGROUND_WINDOW = "No foreground window"
REASON_PROCESS_LOOKUP_FAILED = "Process lookup failed"
REASON_UNKNOWN_EXECUTABLE = "Unknown executable"


def _is_placeholder(value) -> bool:
    """True when a field carries no usable information."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    lowered = text.lower()
    return lowered.startswith("unknown") or lowered in ("none", "?")


def diagnose_failure(info) -> str:
    """Derive a human-readable failure reason from an identifier result.

    Returns an empty string when detection succeeded fully; otherwise a
    short reason ("No foreground window", "Process lookup failed",
    "Unknown executable", ...). This only inspects the dict produced by
    ``get_active_application()`` - it never touches the Win32 APIs itself.
    """
    if info is None:
        b = _bindings
        if not b.load():
            return REASON_NO_BINDINGS
        # Bindings loaded fine but nothing was detected: there is simply no
        # foreground window (secure desktop, full-screen exclusive mode...).
        return REASON_NO_FOREGROUND_WINDOW

    pid = info.get("pid")
    process_name = info.get("process_name")

    if pid is None:
        return REASON_PROCESS_LOOKUP_FAILED
    if _is_placeholder(process_name):
        return REASON_UNKNOWN_EXECUTABLE
    if _is_placeholder(info.get("application")):
        return REASON_UNKNOWN_EXECUTABLE
    return ""


def format_debug_report(
    info,
    reason_override: str = "",
    error: Optional[BaseException] = None,
) -> str:
    """Render the full Windows 11 active-window debug report.

    Success::

        Active Windows Application Debug
        ================================
        Application:    Google Chrome
        Process Name:   chrome.exe
        PID:            12345
        HWND:           123456
        Window Title:   GitHub - Google Chrome
        Executable:     C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe
        Detection:      SUCCESS
        Reason:         -

    Failure::

        Active Windows Application Debug
        ================================
        Application:    UNKNOWN
        ...
        Detection:      FAILED
        Reason:         No foreground window
    """
    lines = [
        "Active Windows Application Debug",
        "=" * 32,
    ]

    if error is not None:
        reason = f"detection error ({error})"
        info = None
    else:
        reason = reason_override or diagnose_failure(info)

    info = info or {}
    success = not reason

    application = info.get("application")
    process_name = info.get("process_name")
    pid = info.get("pid")
    hwnd = info.get("hwnd")
    window_title = info.get("window_title")
    exe_path = info.get("exe_path")

    def _val(v, unknown="UNKNOWN"):
        return v if (v is not None and str(v) != "") else unknown

    lines += [
        f"Application:    {_val(application)}",
        f"Process Name:   {_val(process_name)}",
        f"PID:            {pid if pid is not None else 'N/A'}",
        f"HWND:           {hwnd if hwnd is not None else 'N/A'}",
        f"Window Title:   {_val(window_title, '(none)')}",
        f"Executable:     {_val(exe_path, '(unavailable)')}",
        f"Detection:      {'SUCCESS' if success else 'FAILED'}",
        f"Reason:         {reason if reason else '-'}",
    ]
    return "\n".join(lines)


def _run_debug_report_with(bindings, stream=None):
    """Render one full active-window debug report using ``bindings``.

    Thin wrapper that only forwards the injected bindings to the existing
    ``get_active_application()``; all detection stays in one place. Used by
    unit tests (fake Win32 APIs) and by ``run_debug_report()`` itself.
    """
    return run_debug_report(
        stream=stream,
        provider=lambda: get_active_application(bindings=bindings),
    )


def run_debug_report(stream=None, provider=None) -> int:
    """Print one full active-window debug report and return an exit code.

    ``provider`` defaults to ``get_active_application()`` - the exact same
    entry point VisionManager uses before every capture - so this CLI path
    adds zero duplicated detection logic. Returns 0 on successful detection,
    1 otherwise. Never raises.
    """
    import sys as _sys

    out = stream if stream is not None else _sys.stdout
    get_info = provider if provider is not None else get_active_application
    try:
        info = get_info()
    except Exception as e:  # defensive: the provider must never crash debug
        print(format_debug_report(None, error=e), file=out)
        return 1

    rendered = format_debug_report(info)
    print(rendered, file=out)
    return 0 if diagnose_failure(info) == "" else 1


def describe_active_application(info: Optional[Dict[str, Any]]) -> str:
    """Format identifier output as a short line suitable for LLM context.

    Example:
        'Foreground app: Google Chrome (chrome.exe, PID 12345) - "GitHub - Google Chrome"'
    """
    if not info:
        return ""
    app = info.get("application") or "Unknown Application"
    proc = info.get("process_name")
    title = info.get("window_title") or ""
    pid = info.get("pid")

    parts = [f"Foreground app: {app}"]
    detail = []
    if proc:
        detail.append(proc)
    if pid:
        detail.append(f"PID {pid}")
    if detail:
        parts.append("(" + ", ".join(detail) + ")")
    if title:
        parts.append(f'- "{title[:120]}"')
    return " ".join(parts)
