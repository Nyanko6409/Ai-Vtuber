"""Unit tests for ``python main.py --debug`` (Windows 11 active-window report).

The debug mode must:
  * reuse ``get_active_application()`` (no duplicated Win32 logic),
  * print the full field set (Application / Process Name / PID / HWND /
    Window Title / Executable / Detection / Reason),
  * exit immediately after printing,
  * clearly explain failures.

No real Win32 APIs and no real desktop state are involved: results come
from mocks or from fake bindings injected into the identifier itself.
"""

import io

import unittest
from unittest.mock import patch

from ai_vtuber.vision import windows_app_identifier as wid
from ai_vtuber.vision.windows_app_identifier import (
    REASON_NO_BINDINGS,
    REASON_NO_FOREGROUND_WINDOW,
    REASON_PROCESS_LOOKUP_FAILED,
    REASON_UNKNOWN_EXECUTABLE,
    diagnose_failure,
    format_debug_report,
    run_debug_report,
)


CHROME_INFO = {
    "application": "Google Chrome",
    "process_name": "chrome.exe",
    "window_title": "GitHub - Google Chrome",
    "pid": 12345,
    "hwnd": 123456,
    "exe_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

EXPECTED_HEADER = [
    "Active Windows Application Debug",
    "=" * 32,
]


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


class TestFormatDebugReport(unittest.TestCase):
    def test_success_layout_all_fields(self):
        out = format_debug_report(CHROME_INFO)
        lines = out.splitlines()
        self.assertEqual(lines[:2], EXPECTED_HEADER)
        self.assertIn("Application:    Google Chrome", out)
        self.assertIn("Process Name:   chrome.exe", out)
        self.assertIn("PID:            12345", out)
        self.assertIn("HWND:           123456", out)
        self.assertIn("Window Title:   GitHub - Google Chrome", out)
        self.assertIn(
            "Executable:     C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            out,
        )
        self.assertIn("Detection:      SUCCESS", out)
        self.assertIn("Reason:         -", out)

    def test_none_info_shows_failed_with_reason(self):
        out = format_debug_report(None)
        self.assertIn("Detection:      FAILED", out)
        self.assertIn("Application:    UNKNOWN", out)
        # On this (non-Windows) host the reason distinguishes missing
        # bindings from a genuinely absent foreground window.
        self.assertTrue(
            REASON_NO_BINDINGS in out or REASON_NO_FOREGROUND_WINDOW in out,
            out,
        )
        self.assertIn("PID:            N/A", out)
        self.assertIn("HWND:           N/A", out)
        self.assertIn("Executable:     (unavailable)", out)

    def test_process_lookup_failed(self):
        info = {"application": "Unknown Application", "process_name": None,
                "window_title": "Some Window", "pid": None, "hwnd": 42}
        out = format_debug_report(info)
        self.assertIn("Detection:      FAILED", out)
        self.assertIn(f"Reason:         {REASON_PROCESS_LOOKUP_FAILED}", out)
        self.assertIn("HWND:           42", out)

    def test_unknown_executable(self):
        info = {"application": "Unknown Application", "process_name": None,
                "window_title": "Protected App", "pid": 999, "hwnd": 7}
        out = format_debug_report(info)
        self.assertIn("Detection:      FAILED", out)
        self.assertIn(f"Reason:         {REASON_UNKNOWN_EXECUTABLE}", out)

    def test_error_argument_is_reported_not_raised(self):
        out = format_debug_report(None, error=RuntimeError("boom"))
        self.assertIn("Detection:      FAILED", out)
        self.assertIn("detection error (boom)", out)


class TestDiagnoseFailure(unittest.TestCase):
    def test_success_returns_empty(self):
        self.assertEqual(diagnose_failure(CHROME_INFO), "")

    def test_missing_pid_is_process_lookup_failed(self):
        self.assertEqual(
            diagnose_failure(dict(CHROME_INFO, pid=None)),
            REASON_PROCESS_LOOKUP_FAILED,
        )

    def test_placeholder_exe_is_unknown_executable(self):
        self.assertEqual(
            diagnose_failure(dict(CHROME_INFO, process_name="Unknown Application")),
            REASON_UNKNOWN_EXECUTABLE,
        )


class TestRunDebugReport(unittest.TestCase):
    def test_reuses_existing_get_active_application(self):
        """Regression: --debug must call get_active_application() exactly
        once and never duplicate Win32 detection logic."""
        buf = io.StringIO()
        with patch(
            "ai_vtuber.vision.windows_app_identifier.get_active_application",
            return_value=CHROME_INFO,
        ) as mocked:
            code = run_debug_report(stream=buf)
        mocked.assert_called_once_with()
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertEqual(out.splitlines()[:2], EXPECTED_HEADER)
        self.assertIn("Application:    Google Chrome", out)
        self.assertIn("Detection:      SUCCESS", out)

    def test_provider_exception_reported(self):
        buf = io.StringIO()
        code = run_debug_report(
            stream=buf,
            provider=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        self.assertEqual(code, 1)
        self.assertIn("Detection:      FAILED", buf.getvalue())
        self.assertIn("boom", buf.getvalue())

    def test_failure_exit_code(self):
        buf = io.StringIO()
        with patch(
            "ai_vtuber.vision.windows_app_identifier.get_active_application",
            return_value=None,
        ):
            code = run_debug_report(stream=buf)
        self.assertEqual(code, 1)
        self.assertIn("Detection:      FAILED", buf.getvalue())
        self.assertIn("Reason:", buf.getvalue())


class TestDebugEndToEndWithFakeWin32(unittest.TestCase):
    """Full pipeline: fake Win32 APIs -> real get_active_application() ->
    real debug formatting. No actual desktop state involved."""

    def test_prints_detected_chrome_with_exe_path(self):
        buf = io.StringIO()
        # default bindings = module-level real Win32Bindings, which cannot
        # load on this non-Windows host; inject fakes through the supported
        # bindings parameter instead (no detection logic duplicated).
        code = wid._run_debug_report_with(_FakeBindings(), stream=buf)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Application:    Chrome", out)
        self.assertIn("Process Name:   chrome.exe", out)
        self.assertIn("PID:            12345", out)
        self.assertIn("HWND:           123456", out)
        self.assertIn("Window Title:   GitHub - Google Chrome", out)
        self.assertIn(
            "Executable:     C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            out,
        )
        self.assertIn("Detection:      SUCCESS", out)

    def test_no_foreground_window(self):
        buf = io.StringIO()
        code = wid._run_debug_report_with(_FakeBindings(hwnd=0), stream=buf)
        self.assertEqual(code, 1)
        out = buf.getvalue()
        self.assertIn("Detection:      FAILED", out)
        self.assertIn(f"Reason:         {REASON_NO_FOREGROUND_WINDOW}", out)

    def test_inaccessible_process(self):
        b = _FakeBindings()
        b.OpenProcess = lambda *a: 0  # permission error / protected process
        buf = io.StringIO()
        code = wid._run_debug_report_with(b, stream=buf)
        self.assertEqual(code, 1)
        out = buf.getvalue()
        self.assertIn("Detection:      FAILED", out)
        self.assertIn(f"Reason:         {REASON_UNKNOWN_EXECUTABLE}", out)
        # Raw information still shown to help diagnose the failure.
        self.assertIn("PID:            12345", out)
        self.assertIn("HWND:           123456", out)


class TestMainDebugFlag(unittest.TestCase):
    """``python main.py --debug`` prints the report and exits before Qt."""

    @staticmethod
    def _load_main_module():
        """Load ai_vtuber/main.py by path (stubbing PySide6 with MagicMock
        modules if Qt is not installed) so the test works headless."""
        import importlib.util
        import sys
        import types
        from unittest.mock import MagicMock

        try:
            import PySide6  # noqa: F401
        except ImportError:
            class _QtModule(types.ModuleType):
                def __getattr__(self, name):
                    if name.startswith("__"):
                        raise AttributeError(name)
                    return MagicMock()

            for modname in ("PySide6", "PySide6.QtWidgets", "PySide6.QtCore",
                            "PySide6.QtGui", "PySide6.QtOpenGL",
                            "PySide6.QtOpenGLWidgets"):
                sys.modules.setdefault(modname, _QtModule(modname))

        spec = importlib.util.spec_from_file_location(
            "_main_under_test", "ai_vtuber/main.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run_main(self, argv):
        import sys
        buf = io.StringIO()
        err = io.StringIO()
        real_argv = list(sys.argv)
        module = self._load_main_module()
        try:
            sys.argv = ["main.py"] + argv
            with patch.object(sys, "stdout", buf), patch.object(
                sys, "stderr", err
            ), patch.object(
                wid, "get_active_application", return_value=CHROME_INFO
            ):
                with self.assertRaises(SystemExit) as ctx:
                    module.main()
        finally:
            sys.argv = real_argv
        return ctx.exception.code, buf.getvalue(), err.getvalue()

    def test_debug_flag_prints_report_and_exits(self):
        code, out, _ = self._run_main(["--debug"])
        self.assertEqual(code, 0)
        self.assertIn("Active Windows Application Debug", out)
        self.assertIn("Application:    Google Chrome", out)
        self.assertIn("Detection:      SUCCESS", out)

    def test_short_flag_d_also_works(self):
        code, out, _ = self._run_main(["-d"])
        self.assertEqual(code, 0)
        self.assertIn("Active Windows Application Debug", out)

    def test_removed_flags_are_gone(self):
        """The old dedicated debug flags must no longer exist."""
        code, _, err = self._run_main(["--debug-active-app"])
        # argparse rejects unknown options with exit code 2
        self.assertEqual(code, 2)
        self.assertIn("--debug-active-app", err)


if __name__ == "__main__":
    unittest.main()
