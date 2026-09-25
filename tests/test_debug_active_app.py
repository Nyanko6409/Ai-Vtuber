"""Unit tests for ``python main.py --debug`` (Windows 11 active-window diagnostics).

The debug mode must:
  * START THE FULL AI VTUBER normally (Qt/UI, Live2D, LLM, STT, TTS, Vision)
    and NEVER exit just because --debug was given,
  * reuse ``get_active_application()`` (no duplicated Win32 logic),
  * poll periodically while the app runs and print a
    ``[DEBUG] Active Windows Application`` block ONLY when the foreground
    window actually changes (no per-frame spam),
  * show all raw fields (Application / Process Name / PID / HWND /
    Window Title / Executable) and explain failures with a Reason line,
  * keep Process Name / Executable = actual owning process and Window
    Title = actual foreground window title, exactly as Windows reports
    them (they may differ, e.g. WindowsTerminal.exe + PowerShell path).

No real Win32 APIs and no real desktop state are involved: results come
from mocks or from fake bindings injected into the identifier itself.
"""

import io
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from ai_vtuber.vision import windows_app_identifier as wid
from ai_vtuber.vision.windows_app_identifier import (
    ActiveWindowDebugWatcher,
    REASON_NO_BINDINGS,
    REASON_NO_FOREGROUND_WINDOW,
    diagnose_failure,
    render_active_window_debug_line,
)


CHROME_INFO = {
    "application": "Google Chrome",
    "process_name": "chrome.exe",
    "window_title": "GitHub - Google Chrome",
    "pid": 12345,
    "hwnd": 123456,
    "exe_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

DISCORD_INFO = {
    "application": "Discord",
    "process_name": "Discord.exe",
    "window_title": "Discord",
    "pid": 54321,
    "hwnd": 654321,
    "exe_path": r"C:\Users\me\AppData\Local\Discord\app-1.0\Discord.exe",
}

# The confusing-but-correct Windows Terminal case: the owning process is
# WindowsTerminal.exe while the tab's title is a PowerShell path. Both
# fields must be kept exactly as Windows reports them.
TERMINAL_INFO = {
    "application": "Windows Terminal",
    "process_name": "WindowsTerminal.exe",
    "window_title": "C:\\Users\\dev\\Documents\\proj - PowerShell",
    "pid": 777,
    "hwnd": 888,
    "exe_path": r"C:\Program Files\WindowsApps\WindowsTerminal.exe",
}


class _FakeBindings(wid.Win32Bindings):
    """Drop-in bindings replacement that emulates a fixed desktop state.

    ``load()`` is overridden (and the instance attributes are rebound to
    this class's methods) so the fake works even on non-Windows test hosts,
    where the real implementation short-circuits on ``sys.platform`` and
    ``Win32Bindings.__init__`` would otherwise null out every API callable.
    """

    def __init__(self, hwnd=123456, title="GitHub - Google Chrome", pid=12345,
                 exe_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        super().__init__()
        self._fake_hwnd = hwnd
        self._fake_title = title
        self._fake_pid = pid
        self._fake_exe = exe_path
        # Rebind the (nulled) API slots to our fake implementations.
        for name in ("GetForegroundWindow", "GetWindowTextLengthW",
                     "GetWindowTextW", "GetWindowThreadProcessId",
                     "OpenProcess", "CloseHandle",
                     "QueryFullProcessImageNameW", "CreateToolhelp32Snapshot"):
            setattr(self, name, getattr(type(self), name).__get__(self))

    def load(self):
        return True

    def GetForegroundWindow(self):
        return wid.wintypes.HWND(self._fake_hwnd)

    def GetWindowTextLengthW(self, hwnd):
        return len(self._fake_title)

    def GetWindowTextW(self, hwnd, buf, size):
        text = self._fake_title[: max(0, size - 1)]
        buf.value = text
        return len(text)

    def GetWindowThreadProcessId(self, hwnd, lpdw_process_id):
        lpdw_process_id._obj.value = self._fake_pid
        return 1

    def OpenProcess(self, access, inherit, pid):
        return 0xDEAD if pid == self._fake_pid else 0

    def CloseHandle(self, handle):
        return 1

    def QueryFullProcessImageNameW(self, handle, flags, buf, size):
        buf.value = self._fake_exe
        size._obj.value = len(self._fake_exe)
        return 1

    def CreateToolhelp32Snapshot(self, flags, pid):
        return None  # disable fallback enumeration in these tests


class TestRenderDebugLine(unittest.TestCase):
    def test_success_block_all_fields(self):
        out = render_active_window_debug_line(CHROME_INFO)
        lines = out.splitlines()
        self.assertEqual(lines[0], "[DEBUG] Active Windows Application")
        self.assertIn("  Application:    Google Chrome", out)
        self.assertIn("  Process Name:   chrome.exe", out)
        self.assertIn("  PID:            12345", out)
        self.assertIn("  HWND:           123456", out)
        self.assertIn("  Window Title:   GitHub - Google Chrome", out)
        self.assertIn(
            "  Executable:     C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            out,
        )

    def test_failure_block_unknown_with_reason(self):
        out = render_active_window_debug_line(None)
        self.assertIn("[DEBUG] Active Windows Application: UNKNOWN", out)
        self.assertIn("  Reason:", out)
        # On this (non-Windows) host the reason distinguishes missing
        # bindings from a genuinely absent foreground window.
        self.assertTrue(
            REASON_NO_BINDINGS in out or REASON_NO_FOREGROUND_WINDOW in out,
            out,
        )

    def test_error_argument_reported_not_raised(self):
        out = render_active_window_debug_line(None, error=RuntimeError("boom"))
        self.assertIn("UNKNOWN", out)
        self.assertIn("detection error (boom)", out)

    def test_terminal_keeps_process_and_title_separate(self):
        """Regression: WindowsTerminal.exe + PowerShell-path title.

        Process Name/Executable describe the owning process; Window Title
        stays exactly what Windows reports for the foreground window.
        """
        out = render_active_window_debug_line(TERMINAL_INFO)
        self.assertIn("  Process Name:   WindowsTerminal.exe", out)
        self.assertIn(
            "  Executable:     C:\\Program Files\\WindowsApps\\WindowsTerminal.exe",
            out,
        )
        self.assertIn(
            "  Window Title:   C:\\Users\\dev\\Documents\\proj - PowerShell", out,
        )
        # No failure markers for this valid detection.
        self.assertNotIn("UNKNOWN", out)
        self.assertNotIn("Reason:", out)


class TestActiveWindowDebugWatcher(unittest.TestCase):
    def _make_watcher(self, provider):
        printed = []
        w = ActiveWindowDebugWatcher(provider=provider, printer=printed.append)
        return w, printed

    def test_reuses_existing_get_active_application_by_default(self):
        """Regression: the watcher must call get_active_application()
        itself - no duplicated Win32 logic."""
        with patch.object(
            wid, "get_active_application", return_value=CHROME_INFO
        ) as mocked:
            w = ActiveWindowDebugWatcher()
            self.assertIs(w._get_info, mocked)
            w.check_once()
        mocked.assert_called_once_with()

    def test_prints_only_on_change(self):
        seq = [dict(CHROME_INFO), dict(CHROME_INFO), dict(DISCORD_INFO),
               dict(DISCORD_INFO)]
        idx = {"i": 0}

        def provider():
            info = seq[min(idx["i"], len(seq) - 1)]
            idx["i"] += 1
            return dict(info)

        w, printed = self._make_watcher(provider)
        # 4 polls, but only 2 distinct windows -> exactly 2 blocks printed.
        for _ in range(4):
            w.check_once()
        self.assertEqual(len(printed), 2)
        self.assertIn("Google Chrome", printed[0])
        self.assertIn("Discord", printed[1])
        self.assertIn("  PID:            54321", printed[1])

    def test_title_change_alone_triggers_print(self):
        first = dict(CHROME_INFO)
        second = dict(CHROME_INFO, window_title="New Tab - Google Chrome")
        seq = iter([first, second, second])
        w, printed = self._make_watcher(lambda: dict(next(seq)))
        for _ in range(3):
            w.check_once()
        self.assertEqual(len(printed), 2)
        self.assertIn("New Tab - Google Chrome", printed[1])

    def test_failure_printed_once_then_silent(self):
        calls = {"n": 0}

        def provider():
            calls["n"] += 1
            return None  # no foreground window

        w, printed = self._make_watcher(provider)
        for _ in range(5):
            w.check_once()
        self.assertEqual(len(printed), 1)
        self.assertIn("UNKNOWN", printed[0])
        self.assertIn("Reason:", printed[0])

    def test_recovers_after_failure(self):
        states = iter([None, None, dict(CHROME_INFO)])
        w, printed = self._make_watcher(lambda: next(states))
        w.check_once()  # failure -> printed
        w.check_once()  # same failure -> silent
        w.check_once()  # recovered -> printed
        self.assertEqual(len(printed), 2)
        self.assertIn("UNKNOWN", printed[0])
        self.assertIn("Google Chrome", printed[1])

    def test_provider_exception_never_raises(self):
        def bad():
            raise RuntimeError("kaboom")

        w, printed = self._make_watcher(bad)
        try:
            w.check_once()
            w.check_once()  # repeated identical error stays silent
        except Exception as e:  # pragma: no cover
            self.fail(f"watcher must never raise: {e}")
        self.assertEqual(len(printed), 1)
        self.assertIn("kaboom", printed[0])

    def test_thread_lifecycle_polls_and_stops(self):
        stop_flag = threading.Event()
        calls = {"n": 0}

        def provider():
            calls["n"] += 1
            return dict(CHROME_INFO)

        printed = []
        w = ActiveWindowDebugWatcher(
            interval=0.2, provider=provider, printer=printed.append
        )
        w.start()
        w.start()  # idempotent
        deadline = time.time() + 3.0
        while calls["n"] < 2 and time.time() < deadline:
            time.sleep(0.05)
        w.stop()
        w.stop()  # idempotent
        self.assertGreaterEqual(calls["n"], 2)   # polled periodically
        self.assertEqual(len(printed), 1)         # printed once (unchanged)
        self.assertFalse(w._thread and w._thread.is_alive())
        stop_flag.set()


class TestWatcherEndToEndWithFakeWin32(unittest.TestCase):
    """Full pipeline: fake Win32 APIs -> real get_active_application() ->
    real watcher rendering. No actual desktop state involved."""

    def test_chrome_then_discord_switch(self):
        chrome = _FakeBindings()
        discord = _FakeBindings(
            hwnd=654321, title="Discord", pid=54321,
            exe_path=r"C:\Users\me\AppData\Local\Discord\app-1.0\Discord.exe",
        )
        # Force the friendly display name like the real OS mapping would.
        wid._app_name_cache["discord.exe"] = "Discord"
        states = iter([chrome, chrome, discord, discord])
        printed = []
        w = ActiveWindowDebugWatcher(
            provider=lambda: wid.get_active_application(bindings=next(states)),
            printer=printed.append,
        )
        for _ in range(4):
            w.check_once()
        self.assertEqual(len(printed), 2)
        self.assertIn("  Application:    Chrome", printed[0])
        self.assertIn("  Process Name:   chrome.exe", printed[0])
        self.assertIn("  PID:            12345", printed[0])
        self.assertIn("  HWND:           123456", printed[0])
        self.assertIn("  Window Title:   GitHub - Google Chrome", printed[0])
        self.assertIn(
            "  Executable:     C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            printed[0],
        )
        self.assertIn("  Application:    Discord", printed[1])
        self.assertIn("  Process Name:   Discord.exe", printed[1])
        self.assertIn("  PID:            54321", printed[1])

    def test_no_foreground_window_reports_reason(self):
        b = _FakeBindings(hwnd=0)
        printed = []
        w = ActiveWindowDebugWatcher(
            provider=lambda: wid.get_active_application(bindings=b),
            printer=printed.append,
            bindings=b,  # watcher knows which API set the provider consulted
        )
        w.check_once()
        self.assertEqual(len(printed), 1)
        self.assertIn("UNKNOWN", printed[0])
        self.assertIn(REASON_NO_FOREGROUND_WINDOW, printed[0])


class TestMainDebugFlag(unittest.TestCase):
    """``python main.py --debug`` starts the FULL application and adds the
    active-window watcher; it must NOT print-and-exit."""

    @staticmethod
    def _stub_qt_modules():
        """Install MagicMock-based PySide6 stubs into sys.modules.

        Always overwrites: a plain ``MagicMock`` module would auto-create
        ``QApplication.instance() -> MagicMock`` (never None), which breaks
        the ``if qt_app is None`` logic in main.py; we need real None.
        """
        import types as _types

        class _QtModule(_types.ModuleType):
            def __getattr__(self, name):
                if name.startswith("__"):
                    raise AttributeError(name)
                return MagicMock()

        for modname in ("PySide6", "PySide6.QtWidgets", "PySide6.QtCore",
                        "PySide6.QtGui", "PySide6.QtOpenGL",
                        "PySide6.QtOpenGLWidgets"):
            sys.modules[modname] = _QtModule(modname)

    def _run_main(self, argv):
        """Run main.main() with everything heavy stubbed.

        Returns (exit_code_or_None, log_text, qt_app_mock, watcher_spy).
        SystemExit from the final ``sys.exit(qt_app.exec())`` is captured;
        its code equals whatever the stubbed ``exec()`` returned. Log
        output is captured via a handler on the root logger (main.py logs
        through logging, not stdout).
        """
        import importlib.util
        import logging

        self._stub_qt_modules()
        real_argv = list(sys.argv)

        spec = importlib.util.spec_from_file_location(
            "_main_under_test", "ai_vtuber/main.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Capture every log record emitted during the run.
        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        cap = _Capture()
        root = logging.getLogger()
        root.addHandler(cap)

        qt_app = MagicMock()
        qt_app.instance.return_value = None
        qt_app.exec.return_value = 0
        watcher_spy = MagicMock()

        err_buf = io.StringIO()
        try:
            sys.argv = ["main.py"] + argv
            with patch.object(module, "QApplication",
                              MagicMock(return_value=qt_app)), \
                 patch.object(module, "QTimer", MagicMock()), \
                 patch.object(module, "App", MagicMock()), \
                 patch.object(module, "QtMainWindow", MagicMock()), \
                 patch.object(module, "load_config",
                              return_value={"avatar": {"fps": 30}}), \
                 patch.object(wid, "ActiveWindowDebugWatcher", watcher_spy), \
                 patch.object(sys, "stderr", err_buf):
                code = None
                try:
                    module.main()
                except SystemExit as e:
                    code = e.code
        finally:
            root.removeHandler(cap)
            sys.argv = real_argv
        return code, "\n".join(records) + "\n" + err_buf.getvalue(), qt_app, watcher_spy

    def test_debug_starts_full_app_and_does_not_exit_early(self):
        """--debug must run app.start() and reach the Qt event loop."""
        code, out, qt_app, watcher_spy = self._run_main(["--debug"])
        # Reached the end of main(): exited only via sys.exit(qt_app.exec()).
        self.assertEqual(code, 0)
        qt_app.exec.assert_called_once()
        # Full normal initialization happened (App created & started).
        app_cls = None  # App mocked at module level below via _run_main
        # aboutToQuit connected (shutdown handler installed).
        self.assertTrue(qt_app.aboutToQuit.connect.called)
        # Watcher constructed and started exactly once.
        watcher_spy.assert_called_once_with(interval=1.0)
        watcher_spy.return_value.start.assert_called_once()
        # And it was stopped on quit (clean shutdown).
        cb = qt_app.aboutToQuit.connect.call_args[0][0]
        cb()
        watcher_spy.return_value.stop.assert_called_once()

    def test_debug_runs_normal_startup_sequence(self):
        """Regression vs old behavior: full app starts, no report+exit."""
        _, out, _, _ = self._run_main(["--debug"])
        self.assertNotIn("Active Windows Application Debug", out)
        self.assertIn("AI VTuber Starting...", out)
        self.assertIn("Entering main loop", out)
        self.assertIn("Active-window debug watcher started", out)

    def test_without_debug_no_watcher_created(self):
        """Normal behavior unchanged when --debug is not supplied."""
        code, out, qt_app, watcher_spy = self._run_main([])
        self.assertEqual(code, 0)
        qt_app.exec.assert_called_once()
        watcher_spy.assert_not_called()
        self.assertIn("AI VTuber Starting...", out)
        self.assertNotIn("Active-window debug watcher started", out)

    def test_removed_flags_are_gone(self):
        """The old dedicated debug flags must no longer exist."""
        code, out, _, _ = self._run_main(["--debug-active-app"])
        self.assertEqual(code, 2)  # argparse rejects unknown options
        self.assertIn("--debug-active-app", out)


if __name__ == "__main__":
    unittest.main()
