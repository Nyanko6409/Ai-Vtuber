"""AI VTuber - ``/look`` chat command (single authoritative parser).

This module is the ONE place that understands the ``/look`` syntax. Both
the UI layer (chat submit handler) and the core App message path call
:func:`parse_look_command` - there are no competing parsers anywhere else.

Supported forms (all case-insensitive):

    /look <target>     Lock vision onto an application window, e.g.
                       "/look Discord", "/look VS Code", "/look Genshin Impact"
    /look              Report the current vision target (and refresh it)
    /look off          Clear the vision target
    /look none         Alias of "/look off"

The parse step performs NO Win32 work; execution happens in
:meth:`ai_vtuber.vision.manager.VisionManager.set_vision_target` etc., so
parsing stays trivially testable on any platform.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

LOOK_COMMAND_PREFIX = "/look"

#: Sub-queries that are NOT window names (clear / status actions).
_CLEAR_WORDS = {"off", "none", "clear", "stop"}


@dataclass(frozen=True)
class LookCommand:
    """Parsed ``/look`` command.

    Attributes:
        action: ``"set"`` | ``"status"`` | ``"clear"``
        query: normalized (lowercased, whitespace-collapsed) target name
            for ``action == "set"``, otherwise ``None``.
    """
    action: str
    query: Optional[str] = None


def parse_look_command(text: str) -> Optional[LookCommand]:
    """Parse a chat message into a :class:`LookCommand`.

    Returns ``None`` when the text is not a ``/look`` command, so callers
    can simply fall through to the normal chat pipeline.
    """
    if not text or not isinstance(text, str):
        return None
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered != LOOK_COMMAND_PREFIX and not lowered.startswith(LOOK_COMMAND_PREFIX + " "):
        return None

    arg = stripped[len(LOOK_COMMAND_PREFIX):].strip()
    norm = " ".join(arg.split()).lower()

    if not norm:
        return LookCommand(action="status")
    if norm in _CLEAR_WORDS:
        return LookCommand(action="clear")
    return LookCommand(action="set", query=norm)


def handle_look_command(text: str, vision_manager) -> Optional[str]:
    """Execute a ``/look`` command against the real VisionManager.

    This is the single authoritative dispatch function every caller (UI
    submit handler, core App message path) must use - it never re-implements
    parsing or target logic of its own.

    Args:
        text: raw chat message text.
        vision_manager: the live
            :class:`ai_vtuber.vision.manager.VisionManager` instance (or
            ``None`` when the vision system is unavailable).

    Returns:
        The response string for the status/chat UI when ``text`` was a
        ``/look`` command, or ``None`` when it was NOT a ``/look`` command
        (callers then continue with their normal chat pipeline).
    """
    cmd = parse_look_command(text)
    if cmd is None:
        return None
    if vision_manager is None:
        return ("\U0001F50E Vision system is not available. "
                "Enable it via config (vision.enabled: true).")
    try:
        return vision_manager.execute_look_command(text)
    except Exception as e:  # defensive: a bad command must never crash chat
        logger.error(f"/look command execution failed: {e}", exc_info=True)
        return f"\U0001F50E /look error: {e}"
