"""AI VTuber - Live2D avatar MODE state (config-driven item bundles).

Owns the MODE layer for :class:`ai_vtuber.avatar.live2d.Live2DAvatar`.
Modes sit ABOVE the item layer (:mod:`ai_vtuber.avatar.item_manager`):

* mode state (which modes are active, which items each activated),
* activation / deactivation of modes (entering a mode turns its items on;
  leaving it releases ONLY the items that mode activated),
* ownership interactions: an item stays active while ANY remaining reason
  for it exists — a manual request (``_manual_items``) or another active
  mode. Exclusive modes (``exclusive: true``) clear other active modes
  first but never strip manually-owned items.

Mode definitions come from config (``avatar.modes``) — NEVER hardcoded
here. Functions receive the avatar instance (duck-typed) and mutate its
mode state attributes (``_active_modes``, ``_mode_defs``).
"""

import logging
from typing import Any

from .model_discovery import ITEM_ID_ALIASES
from .item_manager import enable_item, disable_item

logger = logging.getLogger(__name__)


def available_modes(avatar: Any) -> list[str]:
    """Configured avatar mode names (empty when none are defined)."""
    return sorted(str(k) for k in avatar._mode_defs)


def mode_items(avatar: Any, mode: str) -> list[str]:
    """Canonical item ids belonging to one mode definition."""
    defn = avatar._mode_defs.get(mode)
    if defn is None:
        # Case-insensitive mode lookup (Nerd -> nerd).
        for k, v in avatar._mode_defs.items():
            if str(k).casefold() == mode.casefold():
                mode, defn = str(k), v
                break
    if not isinstance(defn, dict):
        return []
    raw_items = defn.get("items") or []
    if isinstance(raw_items, str):
        raw_items = [raw_items]
    out: list[str] = []
    for it in raw_items:
        key = str(it or "").strip().casefold()
        canonical = ITEM_ID_ALIASES.get(key, key)
        if canonical and canonical not in out:
            out.append(canonical)
    return out


def enable_mode(avatar: Any, mode_name: str) -> bool:
    """Enter an avatar mode: activate its configured items.

    Multiple modes may be active simultaneously unless a mode is
    explicitly configured ``exclusive: true``. Unknown modes and
    unknown items inside a mode fail safely (logged, never raise).
    Returns True when at least the mode bookkeeping succeeded.
    """
    mode = str(mode_name or "").strip().casefold()
    if not mode or mode not in {str(k).casefold() for k in avatar._mode_defs}:
        logger.warning("enable_mode('%s'): unknown avatar mode", mode_name)
        return False
    defn = next(v for k, v in avatar._mode_defs.items()
                if str(k).casefold() == mode)
    canonical_name = next(str(k) for k in avatar._mode_defs
                          if str(k).casefold() == mode)
    # Exclusive modes clear OTHER active modes first (never items that
    # were requested manually or owned solely by another source).
    if isinstance(defn, dict) and defn.get("exclusive"):
        for other in list(avatar._active_modes):
            if other != canonical_name:
                disable_mode(avatar, other)
    activated: list[str] = []
    ok = True
    for item_id in mode_items(avatar, canonical_name):
        if enable_item(avatar, item_id, via_mode=True):
            activated.append(item_id)
        else:
            ok = False
    avatar._active_modes[canonical_name] = activated
    logger.info("Mode '%s' ON (items: %s)", canonical_name, activated or "-")
    return ok or bool(activated) or not mode_items(avatar, canonical_name)


def disable_mode(avatar: Any, mode_name: str) -> bool:
    """Leave an avatar mode: remove ONLY the items that mode activated.

    Ownership rule: an item stays active while ANY remaining reason for
    it exists (manual request, another active mode). Disabling 'nerd'
    therefore keeps a manually-requested hat — and even glasses the user
    explicitly asked to keep.
    """
    mode = str(mode_name or "").strip().casefold()
    canonical_name = next((str(k) for k in avatar._mode_defs
                           if str(k).casefold() == mode), None)
    if canonical_name is None:
        logger.warning("disable_mode('%s'): unknown avatar mode", mode_name)
        return False
    owned = avatar._active_modes.pop(canonical_name, [])
    for item_id in owned:
        still_needed = (item_id in avatar._manual_items
                        or any(item_id in m for m in avatar._active_modes.values()))
        if still_needed:
            logger.debug("Item '%s' kept active after mode '%s' off "
                         "(other ownership reasons remain)",
                         item_id, canonical_name)
            continue
        disable_item(avatar, item_id)
    logger.info("Mode '%s' OFF (released: %s)", canonical_name, owned or "-")
    return True


def toggle_mode(avatar: Any, mode_name: str) -> bool:
    if str(mode_name or "").strip().casefold() in \
            {k.casefold() for k in avatar._active_modes}:
        return disable_mode(avatar, mode_name)
    return enable_mode(avatar, mode_name)


def get_active_modes(avatar: Any) -> list[str]:
    return sorted(avatar._active_modes.keys())
