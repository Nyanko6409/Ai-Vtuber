"""AI VTuber - CLI debugging for the Windows 11 active-window identifier.

Windows-11-only debug tooling that prints the *current* foreground window
exactly as the vision system sees it, so you can manually verify detection
while switching between Chrome, Discord, VS Code, games, and other apps.

Usage (on Windows 11):
    python main.py --debug-active-app          # single snapshot
    python main.py --debug-active-app --watch  # live-refresh every 0.5s

This module contains NO Win32 detection logic of its own: everything is
obtained by calling ``windows_app_identifier.get_active_application()``,
the exact same entry point used by VisionManager before each capture.
"""

import argparse
import sys
import time
from typing import Any, Dict, Optional, TextIO

from .windows_app_identifier import get_active_application

# ---------------------------------------------------------------------------
# Failure reasons (kept here so the CLI and tests share one definition).
# ---------------------------------------------------------------------------
REASON_NO_BINDINGS = "Win32 bindings unavailable (Windows 11 required)"
REASON_NO_FOREGROUND_WINDOW = "No foreground window"
REASON_PROCESS_LOOKUP_FAILED = "Process lookup failed"
REASON_UNKNOWN_EXECUTABLE = "Unknown executable"


def _is_placeholder(value: Optional[str]) -> bool:
    """True when a field carries no usable information."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    lowered = text.lower()
    return lowered.startswith("unknown") or lowered in ("none", "?")


def diagnose_failure(info: Optional[Dict[str, Any]]) -> Optional[str]:
    """Derive a human-readable failure reason from an identifier result.

    Returns ``None`` when detection succeeded fully, otherwise a short
    reason string suitable for the ``Reason: ...`` debug line. This only
    inspects the dict produced by ``get_active_application()``; it never
    touches the Win32 APIs itself.
    """
    if info is None:
        return REASON_NO_FOREGROUND_WINDOW

    pid = info.get("pid")
    process_name = info.get("process_name")

    if pid is None:
        return REASON_PROCESS_LOOKUP_FAILED
    if _is_placeholder(process_name):
        return REASON_UNKNOWN_EXECUTABLE
    if _is_placeholder(info.get("application")):
        return REASON_UNKNOWN_EXECUTABLE
    return None


def format_active_application(
    info: Optional[Dict[str, Any]],
    reason_override: Optional[str] = None,
) -> str:
    """Render the identifier result in the fixed debug layout.

    Success::

        Active Windows Application
        --------------------------
        Application: Google Chrome
        Process:     chrome.exe
        PID:         12345
        HWND:        123456
        Window:      GitHub - Google Chrome

    Failure::

        Active Windows Application: UNKNOWN
        Reason: No foreground window / process lookup failed
    """
    if info is None:
        reason = reason_override or REASON_NO_FOREGROUND_WINDOW
        return (
            "Active Windows Application: UNKNOWN\n"
            f"Reason: {reason}"
        )

    reason = diagnose_failure(info)
    if reason is not None:
        if reason_override:
            reason = reason_override
        return (
            "Active Windows Application: UNKNOWN\n"
            f"Reason: {reason}"
        )

    lines = [
        "Active Windows Application",
        "--------------------------",
        f"Application: {info.get('application')}",
        f"Process:     {info.get('process_name')}",
        f"PID:         {info.get('pid')}",
        f"HWND:        {info.get('hwnd')}",
        f"Window:      {info.get('window_title') or '(no title)'}",
    ]
    return "\n".join(lines)


def run_debug_once(
    stream: Optional[TextIO] = None,
    provider=None,
) -> int:
    """Print one snapshot of the current foreground application.

    ``provider`` defaults to ``get_active_application()`` (the exact same
    function VisionManager uses). Returns a process exit code: 0 on
    successful detection, 1 otherwise.
    """
    out = stream if stream is not None else sys.stdout
    get_info = provider if provider is not None else get_active_application
    try:
        info = get_info()
    except Exception as e:  # defensive: the provider must never raise
        print(
            "Active Windows Application: UNKNOWN\n"
            f"Reason: detection error ({e})",
            file=out,
        )
        return 1

    print(format_active_application(info), file=out)
    return 0 if info is not None and diagnose_failure(info) is None else 1


def run_debug_watch(
    interval: float = 0.5,
    iterations: Optional[int] = None,
    stream: Optional[TextIO] = None,
    provider=None,
) -> int:
    """Repeatedly refresh the debug output while you alt-tab between apps.

    ``iterations=None`` runs until Ctrl+C (interactive use); tests pass a
    finite count. Always returns 0.
    """
    out = stream if stream is not None else sys.stdout
    get_info = provider if provider is not None else get_active_application
    count = 0
    last_raw: Optional[str] = None
    try:
        while iterations is None or count < iterations:
            try:
                info = get_info()
            except Exception as e:
                info = None
                rendered = (
                    "Active Windows Application: UNKNOWN\n"
                    f"Reason: detection error ({e})"
                )
            else:
                rendered = format_active_application(info)

            raw = rendered.replace("\n", " | ")
            if raw != last_raw:
                print(raw, flush=True, file=out)
                last_raw = raw
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval)
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="windows_app_cli",
        description=(
            "Debug the Windows 11 foreground-application identifier "
            "(native Win32 user32/kernel32 detection)."
        ),
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Keep refreshing every --interval seconds (Ctrl+C to stop)",
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=0.5,
        help="Refresh interval in seconds for --watch (default: 0.5)",
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=None,
        help="Stop after N refreshes (debug/testing aid for --watch)",
    )
    return parser


def main(argv=None) -> int:
    """Entry point for the standalone CLI (also wired into main.py)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.watch:
        return run_debug_watch(
            interval=args.interval,
            iterations=args.iterations,
        )
    return run_debug_once()


if __name__ == "__main__":
    sys.exit(main())
