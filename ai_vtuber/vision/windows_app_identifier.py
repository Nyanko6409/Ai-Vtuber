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
    find_window_by_name(query) -> Optional[Dict[str, Any]]
    get_window_rect(hwnd) -> Optional[Tuple[int, int, int, int]]

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
    * Window lookup (``find_window_by_name``) only FINDS windows - it never
      moves, resizes, focuses, or activates anything (no SetWindowPos).
"""

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Any, Callable, Dict, Optional, Tuple

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

# Window styles / extended styles used when enumerating candidate windows.
_GWL_STYLE = -16
_GWL_EXSTYLE = -20
_WS_VISIBLE = 0x10000000
_WS_CHILD = 0x40000000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000

# GetAncestor flags (GA_ROOT) - used to skip owned helper windows: only the
# top-level owner of a window chain is a real taskbar-style candidate.
_GA_ROOT = 2

# Common user-friendly names -> actual executable names (all lowercase).
# Used by find_window_by_name() so "/look VS Code" finds Code.exe etc.
# Matching is always case-insensitive on both sides.
APP_ALIASES: Dict[str, str] = {
    "discord": "discord.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "msedge": "msedge.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "vs code": "code.exe",
    "visual studio code": "code.exe",
    "code": "code.exe",
    "genshin impact": "genshinimpact.exe",
    "genshinimpact": "genshinimpact.exe",
    "genshin": "genshinimpact.exe",
    "notepad": "notepad.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "windows terminal": "windowsterminal.exe",
    "terminal": "windowsterminal.exe",
    "powershell": "powershell.exe",
}


def _normalize_query(query: str) -> str:
    """Lowercase + collapse whitespace for alias lookups."""
    return " ".join((query or "").split()).lower()


def _candidate_keys(query: str) -> Tuple[set, str]:
    """Derive (process-name candidates, normalized query) from a user query.

    ``Discord`` -> ({"discord.exe"}, "discord")
    ``VS Code`` -> ({"code.exe"}, "vs code")
    ``Code.exe`` -> ({"code.exe"}, "code.exe")   # already an exe name
    """
    norm = _normalize_query(query)
    procs = set()
    if not norm:
        return procs, norm
    aliased = APP_ALIASES.get(norm)
    if aliased:
        procs.add(aliased)
    else:
        compact = norm.replace(" ", "")
        if compact.endswith(".exe"):
            procs.add(compact)
        else:
            procs.add(compact + ".exe")
    return procs, norm


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


class _RECT(ctypes.Structure):
    """Corresponds to Win32 RECT from windef.h (used by GetWindowRect)."""
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
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
        self.IsWindowVisible = None
        self.GetWindowRect = None
        self.GetAncestor = None
        self.GetWindowLongPtrW = None
        self.EnumWindows = None
        self.OpenProcess = None
        self.CloseHandle = None
        self.QueryFullProcessImageNameW = None
        self.CreateToolhelp32Snapshot = None
        self.Module32FirstW = None
        self.Module32NextW = None
        self.Process32FirstW = None
        self.Process32NextW = None
        self.GetLastError = None

    # ``c_ssize_t`` is the portable spelling of Windows' LONG_PTR.
    _LONG_PTR = ctypes.c_ssize_t

    @property
    def WNDENUMPROC(self):
        """EnumWindows callback prototype (created lazily).

        Built on first use instead of at class-definition time so this
        module stays importable on non-Windows hosts where
        ``ctypes.WINFUNCTYPE`` does not exist (mirrors the lazy
        ``load()`` strategy used for every other Win32 binding).
        """
        return ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

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

                user32.IsWindowVisible.restype = wintypes.BOOL
                user32.IsWindowVisible.argtypes = [wintypes.HWND]

                user32.GetWindowRect.restype = wintypes.BOOL
                user32.GetWindowRect.argtypes = [
                    wintypes.HWND, ctypes.POINTER(_RECT)
                ]

                # BOOL EnumWindows(WNDENUMPROC, LPARAM)
                user32.EnumWindows.restype = wintypes.BOOL
                user32.EnumWindows.argtypes = [self.WNDENUMPROC, wintypes.LPARAM]

                # HWND GetAncestor(HWND, UINT)
                user32.GetAncestor.restype = wintypes.HWND
                user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]

                # LONG_PTR GetWindowLongPtrW(HWND, int)  (64-bit correct;
                # falls back to the 32-bit GetWindowLongW on WoW64 Python)
                if hasattr(user32, "GetWindowLongPtrW"):
                    getter = user32.GetWindowLongPtrW
                else:  # pragma: no cover - 32-bit Python only
                    getter = user32.GetWindowLongW
                getter.restype = self._LONG_PTR
                getter.argtypes = [wintypes.HWND, ctypes.c_int]

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
                self.IsWindowVisible = user32.IsWindowVisible
                self.GetWindowRect = user32.GetWindowRect
                self.GetAncestor = user32.GetAncestor
                self.GetWindowLongPtrW = getter
                self.EnumWindows = user32.EnumWindows
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


def _resolve_process_info(
    b: Win32Bindings, pid: Optional[int], window_title: str, hwnd: int
) -> Dict[str, Any]:
    """Resolve app name / process name / exe path for a window's PID.

    Shared by the foreground identifier and the ``/look`` window lookup so
    there is exactly ONE process-resolution path (QueryFullProcessImageNameW
    primary, Toolhelp module snapshot second, Toolhelp process-name last).
    Handles inaccessible processes and permission errors gracefully -
    never raises.
    """
    if pid is None:
        return {
            "application": "Unknown Application",
            "process_name": None,
            "window_title": window_title,
            "pid": None,
            "hwnd": hwnd,
        }

    # Executable path from the actual process (primary then fallbacks).
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


def _is_acceptable_candidate(b: Win32Bindings, hwnd_int: int) -> bool:
    """Cheap visibility/style filter used while enumerating windows.

    Skips invisible windows, child windows, tool windows and zero-size
    windows (minimized windows report a (-32000, -32000) rect). Read-only:
    never modifies any window.
    """
    try:
        if not b.IsWindowVisible(wintypes.HWND(hwnd_int)):
            return False
    except Exception:
        return False

    try:
        style = int(b.GetWindowLongPtrW(wintypes.HWND(hwnd_int), _GWL_STYLE)) & 0xFFFFFFFF
        exstyle = int(b.GetWindowLongPtrW(wintypes.HWND(hwnd_int), _GWL_EXSTYLE)) & 0xFFFFFFFF
    except Exception:
        style, exstyle = 0, 0
    if style & _WS_CHILD:
        return False
    if (exstyle & _WS_EX_TOOLWINDOW) and not (exstyle & _WS_EX_APPWINDOW):
        return False

    # Only consider the top-level owner of a window chain.
    try:
        root = b.GetAncestor(wintypes.HWND(hwnd_int), _GA_ROOT)
        if _normalize_hwnd(root) != hwnd_int:
            return False
    except Exception:
        pass

    rect = get_window_rect(hwnd_int, bindings=b)
    if not rect:
        return False
    left, top, right, bottom = rect
    if right - left <= 0 or bottom - top <= 0:
        return False
    return True


def find_window_by_name(
    query: str,
    bindings: Optional[Win32Bindings] = None,
) -> Optional[Dict[str, Any]]:
    """Find a visible top-level window whose process/title matches ``query``.

    Used by the ``/look`` command ("Discord", "Chrome", "VS Code",
    "Genshin Impact", ...). Matching is case-insensitive on both sides and
    resolves through :data:`APP_ALIASES` plus the existing process-
    resolution logic (QueryFullProcessImageNameW primary, Toolhelp
    fallbacks) shared with :func:`get_active_application`.

    IMPORTANT: this function only FINDS windows. It never moves, resizes,
    focuses, activates or otherwise modifies anything (no SetWindowPos).

    Returns a dict with::

        {
            "hwnd":          int window handle,
            "pid":           int process id,
            "window_title":  e.g. "Discord",
            "process_name":  e.g. "Discord.exe",
            "application":   friendly name, e.g. "Discord",
            "exe_path":      full path when available,
            "rect":          (left, top, right, bottom) screen rectangle,
        }

    Returns ``None`` when no matching window exists or the platform/APIs
    are unavailable (never raises).
    """
    b = bindings or _bindings
    if not b.load():
        logger.debug("Win32 bindings unavailable; window lookup skipped")
        return None

    candidates, norm = _candidate_keys(query)
    if not norm:
        return None

    def _title_matches(title: str) -> bool:
        t = title.lower()
        if norm in t:
            return True
        compact = norm.replace(" ", "")
        return compact and compact in t.replace(" ", "")

    found: Dict[int, Dict[str, Any]] = {}

    def _callback(raw_hwnd, _lparam):
        try:
            hwnd_int = _normalize_hwnd(raw_hwnd)
            if not hwnd_int or hwnd_int in found:
                return True
            if not _is_acceptable_candidate(b, hwnd_int):
                return True
            pid = _get_pid(b, hwnd_int)
            proc_name = None
            if pid:
                exe_path = _query_image_path(b, pid)
                if exe_path:
                    proc_name = _basename(exe_path).lower()
            title = _get_window_title(b, hwnd_int)
            proc_hit = bool(proc_name and proc_name in candidates)
            title_hit = bool(title and _title_matches(title))
            if proc_hit or title_hit:
                found[hwnd_int] = {
                    "pid": pid,
                    "title": title,
                    "rank": 0 if proc_hit else 1,
                }
                order.append(hwnd_int)
        except Exception as e:  # defensive: one bad window must not abort
            logger.debug(f"EnumWindows callback error: {e}")
        return True

    try:
        b.EnumWindows(b.WNDENUMPROC(_callback), 0)
    except Exception as e:
        logger.debug(f"EnumWindows failed: {e}")
        return None

    if not found:
        logger.debug(f"No window found for query {query!r}")
        return None

    # Prefer process-name matches; among equals prefer the largest window
    # (main app window over small helper dialogs with the same exe).
    def _area(hwnd_int: int) -> int:
        rect = get_window_rect(hwnd_int, bindings=b)
        if not rect:
            return 0
        l, t, r, bo = rect
        return max(0, r - l) * max(0, bo - t)

    best_hwnd = min(found.keys(), key=lambda h: (found[h]["rank"], -_area(h)))
    entry = found[best_hwnd]

    info = _resolve_process_info(b, entry["pid"], entry["title"], best_hwnd)
    info["rect"] = get_window_rect(best_hwnd, bindings=b)
    return info


def get_window_rect(
    hwnd: Any,
    bindings: Optional[Win32Bindings] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """Return a window's screen rectangle as ``(left, top, right, bottom)``.

    Read-only GetWindowRect wrapper. Returns ``None`` for invalid/closed
    handles, non-Windows hosts, or degenerate rectangles (zero/negative
    size, e.g. minimized windows). Never raises.
    """
    b = bindings or _bindings
    if not b.load():
        return None
    hwnd_int = _normalize_hwnd(hwnd)
    if not hwnd_int:
        return None
    try:
        if not b.IsWindow(wintypes.HWND(hwnd_int)):
            return None
        rect = _RECT()
        if not b.GetWindowRect(wintypes.HWND(hwnd_int), ctypes.byref(rect)):
            return None
        box = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception as e:
        logger.debug(f"GetWindowRect failed for HWND {hwnd}: {e}")
        return None
    left, top, right, bottom = box
    if right - left <= 0 or bottom - top <= 0:
        # Invalid / minimized / off-screen garbage rectangle.
        return None
    return box


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

    # 3. Owning process id + 4. executable resolution (shared helper).
    pid = _get_pid(b, hwnd)
    return _resolve_process_info(b, pid, window_title, hwnd)


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


def diagnose_failure(info, bindings=None) -> str:
    """Derive a human-readable failure reason from an identifier result.

    Returns an empty string when detection succeeded fully; otherwise a
    short reason ("No foreground window", "Process lookup failed",
    "Unknown executable", ...). This only inspects the dict produced by
    ``get_active_application()`` - it never touches the Win32 APIs itself.
    ``bindings`` lets tooling (e.g. the --debug watcher running against
    injected/mock bindings on a test host) state which API set was actually
    consulted; it defaults to the module-level real bindings.
    """
    if info is None:
        b = bindings if bindings is not None else _bindings
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


def render_active_window_debug_line(
    info: Optional[Dict[str, Any]],
    reason_override: str = "",
    error: Optional[BaseException] = None,
) -> str:
    """Render ONE compact ``[DEBUG] Active Windows Application`` block.

    Pure presentation on top of a ``get_active_application()`` result - it
    contains no Win32 detection logic of its own. Used by the in-app
    foreground-change watcher enabled with ``python main.py --debug``.

    Success::

        [DEBUG] Active Windows Application
          Application:    Google Chrome
          Process Name:   chrome.exe
          PID:            12345
          HWND:           123456
          Window Title:   GitHub - Google Chrome
          Executable:     C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe

    Failure::

        [DEBUG] Active Windows Application: UNKNOWN
          Reason: No foreground window / process lookup failed

    ``Process Name`` / ``Executable`` always describe the actual owning
    process and ``Window Title`` the actual foreground window title - both
    exactly as Windows reports them (they may legitimately differ, e.g.
    WindowsTerminal.exe showing a PowerShell path as its tab title).
    """
    if error is not None:
        reason = f"detection error ({error})"
        info = None
    else:
        reason = reason_override or diagnose_failure(info)

    data = info or {}

    def _val(v, unknown="UNKNOWN"):
        return v if (v is not None and str(v) != "") else unknown

    if reason:
        return "\n".join([
            "[DEBUG] Active Windows Application: UNKNOWN",
            f"  Reason: {reason}",
        ])

    exe_path = data.get("exe_path") or data.get("process_name") or "(unavailable)"
    return "\n".join([
        "[DEBUG] Active Windows Application",
        f"  Application:    {_val(data.get('application'))}",
        f"  Process Name:   {_val(data.get('process_name'))}",
        f"  PID:            {data.get('pid') if data.get('pid') is not None else 'N/A'}",
        f"  HWND:           {data.get('hwnd') if data.get('hwnd') is not None else 'N/A'}",
        f"  Window Title:   {_val(data.get('window_title'), '(none)')}",
        f"  Executable:     {exe_path}",
    ])


class ActiveWindowDebugWatcher:
    """Periodically poll the foreground window while the app runs (--debug).

    Windows-11-only diagnostic helper. It reuses the existing
    ``get_active_application()`` implementation for *all* detection - no
    Win32 logic lives here - and prints a debug block ONLY when the active
    window actually changes, so the console is never spammed per frame.

    The watcher runs on a daemon thread and stops cleanly via ``stop()``,
    which the application calls during shutdown. Detection failures are
    reported once (with a reason) instead of raising into the app.
    """

    #: identity key: change of any of these fields triggers a new print
    _IDENTITY_FIELDS = ("hwnd", "pid", "process_name", "window_title")

    def __init__(self, interval: float = 1.0, provider=None, printer=None,
                 bindings=None):
        self.interval = max(0.2, float(interval))
        # Same entry point VisionManager uses before every capture.
        self._get_info = provider if provider is not None else get_active_application
        self._print = printer if printer is not None else print
        # Optional: which Win32 binding set the provider consults (used only
        # to phrase failure reasons; detection logic is never touched here).
        self._bindings = bindings
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_key: Optional[tuple] = None
        self._last_reason: Optional[str] = None

    @classmethod
    def _identity(cls, info: Dict[str, Any]) -> tuple:
        return tuple(info.get(f) for f in cls._IDENTITY_FIELDS)

    def check_once(self) -> Optional[str]:
        """Poll the foreground window once; return printed text (or None).

        Prints only when the active window changed since the last call (or
        when the failure state changed after a previous failure). Never
        raises: any provider exception is reported as a FAILED block once.
        """
        try:
            info = self._get_info()
        except Exception as e:  # defensive: debug must never crash the app
            reason = f"detection error ({e})"
            if reason != self._last_reason:
                self._last_reason = reason
                self._last_key = None
                text = render_active_window_debug_line(None, error=e)
                self._print(text)
                return text
            return None

        if not info:
            reason = diagnose_failure(None, bindings=self._bindings)
            if reason != self._last_reason:
                self._last_reason = reason
                self._last_key = None
                text = render_active_window_debug_line(None, reason_override=reason)
                self._print(text)
                return text
            return None

        self._last_reason = None
        key = self._identity(info)
        if key == self._last_key:
            return None  # unchanged: stay silent
        self._last_key = key
        text = render_active_window_debug_line(info)
        self._print(text)
        return text

    def start(self) -> None:
        """Start the polling daemon thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="ActiveWindowDebugWatcher", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            try:
                self.check_once()
            except Exception as e:  # pragma: no cover - belt & braces
                logger.debug(f"Active-window debug watcher error: {e}")

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the watcher to stop and join its thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None


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
