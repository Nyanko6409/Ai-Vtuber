"""AI VTuber - Live2D item / accessory state.

Owns the ITEM half of the avatar's two-layer semantic system for
:class:`ai_vtuber.avatar.live2d.Live2DAvatar`:

* item/accessory state (kind="item" .exp3.json files: glasses, hat, ...),
* activation / deactivation of single items — multiple items stay active
  simultaneously and NEVER touch the active facial expression,
* semantic item resolution (canonical ids + legacy ``*_toggle`` aliases),
* manual-ownership bookkeeping (``_manual_items``) that the mode layer
  (:mod:`ai_vtuber.avatar.mode_manager`) consults before releasing items.

Functions receive the avatar instance (duck-typed) and mutate its item
state attributes (``_active_items``, ``_manual_items``,
``_expression_owned``, ``_expression_params``).
"""

import logging
from typing import Any

from .model_discovery import (
    ITEMS,
    canonicalize_semantic_id,
    KIND_ITEM,
    ExpressionInfo,
    exp3_stem,
)
from .expression_manager import EMOTION_PARAMS, resolve_semantic_expression
from .expression_apply import load_expression_file

logger = logging.getLogger(__name__)

# Semantic ids of the 6 stackable items on the canonical Live2D sheet
# (derived from model_discovery.ITEMS — the single source of truth).
ITEM_IDS: tuple[str, ...] = tuple(sorted(ITEMS))


def item_default_params(avatar: Any, exp: ExpressionInfo) -> dict[str, float]:
    """Best-effort 'off' values for an item's parameters.

    live2d-py 0.7.x exposes no parameter-defaults API, so we use the
    model's own neutral fallback values where they overlap and 0.0
    otherwise (the standard Cubism 'part hidden / deformer neutral'
    value). This is a best-effort inverse of the emulated apply path.
    """
    defaults: dict[str, float] = {}
    for pid in exp.parameters:
        defaults[pid] = EMOTION_PARAMS["neutral"].get(pid, 0.0)
    return defaults


def enable_item(avatar: Any, item_id: str, via_mode: bool = False) -> bool:
    """Activate one discovered kind="item" .exp3.json (stackable).

    Accepts canonical semantic ids ("glasses", "hat", ...) as well as
    legacy aliases via _resolve_semantic_expression. Unknown ids or
    non-item ids are rejected (returns False, never raises). Enabling
    an item does NOT change the active facial expression.

    ``via_mode=True`` marks the activation as mode-owned: a manually
    requested item stays flagged in ``_manual_items`` so disabling the
    mode later will not strip it (§ ownership tracking).
    """
    if not avatar._initialized or not avatar._model:
        logger.debug("enable_item('%s') ignored: model not initialized",
                     item_id)
        return False
    exp, path = resolve_semantic_expression(avatar, item_id)
    if exp is None or exp.kind != KIND_ITEM or not path:
        logger.warning("enable_item('%s'): not a known item on this model",
                       item_id)
        return False
    stem = exp3_stem(exp.file)
    if stem in avatar._active_items.values():
        # Idempotent: already wearing this file. A direct request also
        # marks the item as manually owned so mode teardown won't strip
        # it (see disable_mode()).
        if not via_mode:
            avatar._manual_items.add(exp.id)
        return True
    if load_expression_file(avatar, path, label=exp.id):
        avatar._active_items[exp.id] = stem
        if not via_mode:
            avatar._manual_items.add(exp.id)
        return True
    return False


def disable_item(avatar: Any, item_id: str) -> bool:
    """Deactivate one item without touching the facial expression.

    Releases only the parameters owned by that item's exp3 file whose
    current values were set by the item itself (values re-set by the
    active face are preserved). Returns False for unknown/non-item ids.
    """
    if not avatar._initialized or not avatar._model:
        logger.debug("disable_item('%s') ignored: model not initialized",
                     item_id)
        return False
    exp, _path = resolve_semantic_expression(avatar, item_id)
    if exp is None or exp.kind != KIND_ITEM:
        logger.warning("disable_item('%s'): not a known item on this model",
                       item_id)
        return False
    stem = avatar._active_items.pop(exp.id, None) or exp3_stem(exp.file)
    # Explicit removal clears every reason the item was active (manual
    # request + any owning modes), keeping the state bookkeeping honest.
    avatar._manual_items.discard(exp.id)
    for m_items in avatar._active_modes.values():
        if exp.id in m_items:
            m_items.remove(exp.id)
    owned = avatar._expression_owned.pop(stem, set())
    # Also release any params from the parsed exp3 file not tracked yet.
    owned |= set(exp.parameters.keys())
    face_active = avatar._active_expression_name
    for pid in sorted(owned):
        # Don't clobber a value currently owned by the active FACE.
        for f_stem, f_ids in avatar._expression_owned.items():
            if f_stem != stem and pid in f_ids:
                break
        else:
            try:
                avatar._model.ResetParameterValue(pid)
            except Exception:
                try:
                    default = item_default_params(avatar, exp).get(pid, 0.0)
                    avatar._model.SetParameterValue(pid, default)
                except Exception:
                    pass
        avatar._expression_params.pop(pid, None)
    if face_active:
        logger.debug("Item '%s' disabled (face %s untouched)",
                     exp.id, face_active)
    return True


def get_active_items(avatar: Any) -> list[str]:
    """Semantic ids of the currently enabled items."""
    return sorted(avatar._active_items.keys())
