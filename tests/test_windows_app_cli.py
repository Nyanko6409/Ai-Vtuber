"""Unit tests for the Windows 11 active-application CLI debugging tool.

These tests never touch real Win32 APIs:

* Formatting/CLI-output tests feed mock dicts / mock providers directly.
* One end-to-end test injects fake ``Win32Bindings`` into the *real*
  ``get_active_application()`` implementation, proving the CLI prints what
  the identifier actually detects - without depending on whichever app
  happens to be open on the machine running the tests.
"""

import io
import unittest
from unittest.mock import patch

from ai_vtuber.vision import windows_app_identifier as wid
from ai_vtuber.vision.windows_app_cli import (
    REASON_NO_FOREGROUND_WINDOW,
    REASON_PROCESS_LOOKUP_FAILED,
    REASON_UNKNOWN_EXECUTABLE,
    build_parser,
    diagnose_failure,
    format_active_application,
    main,
    run_debug_once,
    run_debug_watch,
)


CHROME_INFO = {
    "application": "Google Chrome",
    "process_name": "chrome.exe",
    "window_title": "GitHub - Google Chrome",
    "pid": 12345,
    "hwnd": 123456,
}

EXPECTED_CHROME_OUTPUT = "\n".join([
    "Active Windows Application",
    "--------------------------",
    "Application: Google Chrome",
    "Process:     chrome.exe",
    "PID:         12345",
    "HWND:        123456",
    "Window:      GitHub - Google Chrome",
])


class _FakeBindings(wid.Win32Bindings):
    """Drop-in bindings replacement that emulates a fixed desktop state."""

    def __init__(self, hwnd=123456, title="GitHub - Google Chrome", pid=12345,
                 exe_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        # Skip parent __init__ state but keep attributes consistent.
        super().__init__()
        self._fake_hwnd = hwnd
        self._fake_title = title
        self._fake_pid = pid
        self._fake_exe = exe_path
        self._loaded = True  # load() will short-circuit to True

    def GetForegroundWindow(self):
        # Real Win32 returns an HWND handle object; exercise the same path.
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


class TestFormatActiveApplication(unittest.TestCase):
    """The exact debug layout required by the spec."""

    def test_success_layout(self):
        self.assertEqual(format_active_application(CHROME_INFO),
                         EXPECTED_CHROME_OUTPUT)

    def test_no_foreground_window(self):
        out = format_active_application(None)
        self.assertIn("Active Windows Application: UNKNOWN", out)
        self.assertIn(f"Reason: {REASON_NO_FOREGROUND_WINDOW}", out)

    def test_process_lookup_failure(self):
        info = dict(CHROME_INFO, pid=None, process_name=None,
                    application="Unknown Application")
        out = format_active_application(info)
        self.assertIn("UNKNOWN", out)
        self.assertIn(f"Reason: {REASON_PROCESS_LOOKUP_FAILED}", out)

    def test_inaccessible_process_unknown_executable(self):
        info = {"application": "Unknown Application", "process_name": None,
                "window_title": "Protected App", "pid": 999, "hwnd": 42}
        out = format_active_application(info)
        self.assertIn("UNKNOWN", out)
        self.assertIn(f"Reason: {REASON_UNKNOWN_EXECUTABLE}", out)

    def test_missing_window_title_shows_placeholder(self):
        info = dict(CHROME_INFO, window_title="")
        self.assertIn("Window:      (no title)", format_active_application(info))


class TestDiagnoseFailure(unittest.TestCase):
    def test_success_returns_none(self):
        self.assertIsNone(diagnose_failure(CHROME_INFO))

    def test_none_is_no_foreground_window(self):
        self.assertEqual(diagnose_failure(None), REASON_NO_FOREGROUND_WINDOW)

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


class TestRunDebugOnce(unittest.TestCase):
    def test_uses_existing_get_active_application(self):
        """Regression: the CLI must call get_active_application(), not
        duplicate Win32 detection logic."""
        buf = io.StringIO()
        with patch(
            "ai_vtuber.vision.windows_app_cli.get_active_application",
            return_value=CHROME_INFO,
        ) as mocked:
            code = run_debug_once(stream=buf)
        mocked.assert_called_once_with()
        self.assertEqual(buf.getvalue().rstrip("\n"), EXPECTED_CHROME_OUTPUT)
        self.assertEqual(code, 0)

    def test_failure_exit_code_and_output(self):
        buf = io.StringIO()
        with patch(
            "ai_vtuber.vision.windows_app_cli.get_active_application",
            return_value=None,
        ):
            code = run_debug_once(stream=buf)
        self.assertEqual(code, 1)
        self.assertIn("Active Windows Application: UNKNOWN", buf.getvalue())
        self.assertIn("Reason:", buf.getvalue())

    def test_provider_exception_is_reported_not_raised(self):
        buf = io.StringIO()
        code = run_debug_once(
            stream=buf,
            provider=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN", buf.getvalue())
        self.assertIn("boom", buf.getvalue())


class TestRunDebugWatch(unittest.TestCase):
    def test_watch_refreshes_and_dedupes(self):
        calls = {"n": 0}

        def provider():
            calls["n"] += 1
            if calls["n"] <= 2:
                return CHROME_INFO
            return dict(CHROME_INFO, application="Discord",
                        process_name="Discord.exe", pid=2222, hwnd=3333,
                        window_title="#general - Discord")

        buf = io.StringIO()
        code = run_debug_watch(interval=0.0, iterations=4, stream=buf,
                               provider=provider)
        self.assertEqual(code, 0)
        lines = [ln for ln in buf.getvalue().splitlines() if ln]
        # Chrome printed once (deduped), then the switch to Discord printed.
        self.assertEqual(len(lines), 2)
        self.assertIn("Google Chrome", lines[0])
        self.assertIn("Discord", lines[1])


class TestMainEntryPoint(unittest.TestCase):
    def test_main_single_snapshot(self):
        buf = io.StringIO()
        with patch(
            "ai_vtuber.vision.windows_app_cli.get_active_application",
            return_value=CHROME_INFO,
        ):
            with patch("sys.stdout", buf):
                code = main([])
        self.assertEqual(code, 0)
        self.assertIn(EXPECTED_CHROME_OUTPUT, buf.getvalue())

    def test_main_watch_flag_parsing(self):
        args = build_parser().parse_args(["--watch", "--interval", "0.1",
                                          "--iterations", "2"])
        self.assertTrue(args.watch)
        self.assertAlmostEqual(args.interval, 0.1)
        self.assertEqual(args.iterations, 2)

    def test_main_watch_runs_bounded_iterations(self):
        buf = io.StringIO()
        with patch(
            "ai_vtuber.vision.windows_app_cli.get_active_application",
            return_value=CHROME_INFO,
        ):
            with patch("sys.stdout", buf):
                code = main(["--watch", "--interval", "0",
                             "--iterations", "3"])
        self.assertEqual(code, 0)
        self.assertIn("Google Chrome", buf.getvalue())


class TestCliEndToEndWithFakeWin32(unittest.TestCase):
    """Full pipeline: fake Win32 APIs -> real get_active_application() ->
    real CLI formatting. No real desktop state involved."""

    def setUp(self):
        self._orig_bindings = wid.get_bindings()

    def tearDown(self):
        wid.set_bindings(self._orig_bindings)

    def test_prints_detected_chrome(self):
        wid.set_bindings(_FakeBindings())
        buf = io.StringIO()
        code = run_debug_once(stream=buf)  # default provider = real function
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().rstrip("\n"), EXPECTED_CHROME_OUTPUT)

    def test_detects_vscode_and_discord(self):
        cases = [
            (r"C:\Users\me\AppData\Local\Programs\Microsoft VS Code\Code.exe",
             "Visual Studio Code - main.py - src - Visual Studio Code",
             "Code.exe"),
            (r"C:\Users\me\AppData\Local\Discord\app-1.0.9012\Discord.exe",
             "#general - Discord",
             "Discord.exe"),
        ]
        for exe, title, expected_proc in cases:
            wid.set_bindings(_FakeBindings(title=title, exe_path=exe, pid=4242,
                                           hwnd=99))
            buf = io.StringIO()
            code = run_debug_once(stream=buf)
            out = buf.getvalue()
            self.assertEqual(code, 0, f"failed for {exe}: {out}")
            self.assertIn(f"Process:     {expected_proc}", out)
            self.assertIn("PID:         4242", out)
            self.assertIn("HWND:        99", out)
            self.assertIn(f"Window:      {title}", out)

    def test_no_foreground_window_via_fake_bindings(self):
        wid.set_bindings(_FakeBindings(hwnd=0))
        buf = io.StringIO()
        code = run_debug_once(stream=buf)
        self.assertEqual(code, 1)
        self.assertIn("Active Windows Application: UNKNOWN", buf.getvalue())
        self.assertIn(f"Reason: {REASON_NO_FOREGROUND_WINDOW}", buf.getvalue())

    def test_inaccessible_process_via_fake_bindings(self):
        b = _FakeBindings()
        b.OpenProcess = lambda *a: 0  # permission error / protected process
        wid.set_bindings(b)
        buf = io.StringIO()
        code = run_debug_once(stream=buf)
        self.assertEqual(code, 1)
        out = buf.getvalue()
        self.assertIn("UNKNOWN", out)
        self.assertIn(f"Reason: {REASON_UNKNOWN_EXECUTABLE}", out)


if __name__ == "__main__":
    unittest.main()
