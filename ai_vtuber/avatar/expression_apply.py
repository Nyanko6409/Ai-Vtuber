"""AI VTuber - Live2D facial-expression application layer.

Owns the FACIAL expression state transitions for
:class:`ai_vtuber.avatar.live2d.Live2DAvatar`:

* applying one ``.exp3.json`` parameter set to the runtime model
  (native ``LoadExpression`` path when available, otherwise the
  deterministic parameter-emulation path used by live2d-py 0.7.x),
* releasing ("归零") the parameters owned by the previously active FACE
  while never touching active ITEMS — items stack with expressions and
  persist across mood switches,
* the neutral reset: "neutral" is a LOGICAL reset state with no
  ``neutral.exp3.json`` file; it clears the face only.

Semantic-id resolution (angry -> ku.exp3.json etc.) lives in
``expression_manager.py``'s sibling :mod:`ai_vtuber.avatar.expression_manager`;
this module only applies already-resolved files to the runtime model.

Functions receive the avatar instance (duck-typed) and mutate its
expression state attributes (``_expression_params``, ``_expression_owned``,
``_active_expression_name``, ``_current_expression``, ``_active_items``).
"""

import logging
from pathlib import Path
from typing import Any

from .model_discovery import (
    DEFAULT_SEMANTIC_NAMES,
    KIND_ITEM,
    exp3_stem,
)

logger = logging.getLogger(__name__)


def load_expression_file(avatar: Any, path: str, label: str = "") -> bool:
    """Apply one .exp3.json to the runtime model. Never raises.

    Compatibility note: live2d-py 0.7.0.4 (third-party wrapper) exposes a
    Cubism4-style API surface, but its LAppModel has NO LoadExpression /
    SetExpression methods (calling them raises AttributeError — this was
    the exact crash seen at runtime). Rather than failing, we *emulate*
    expressions deterministically: read the .exp3.json "Parameters" list
    (already parsed during discovery) and push each Id/Value pair through
    SetParameterValue. Parameters owned by the previously active
    expression are released first, so switching moods is clean
    (equivalent of VTube Studio's 归零 before applying the next one).

    If a future/other live2d-py build DOES expose LoadExpression +
    SetExpression, we prefer the native path (proper fade support);
    otherwise we fall back to parameter emulation transparently.
    """
    name = Path(path).name  # live2d-py keys expressions by filename
    stem = exp3_stem(name) or (label.lower() if label else "") or "?"
    # Which layer does this file belong to? Prefer the discovered catalog
    # (authoritative kind); fall back to the semantic-id -> kind map from
    # model_discovery for uncatalogued files.
    catalog_kinds = {exp3_stem(e.file): e.kind
                     for e in avatar._expression_catalog.values()}
    kind = catalog_kinds.get(stem)
    if kind is None and label:
        sem = DEFAULT_SEMANTIC_NAMES.get(label.lower())
        kind = sem[3] if sem else None
    item_layer = kind == KIND_ITEM

    # --- Native path (only when the installed build supports it) ----------
    # IMPORTANT: this branch must run BEFORE any parameter work. Older
    # live2d-py builds (0.7.0.x) expose NO GetParameterValue, so probing it
    # would raise AttributeError and silently drop us into the emulated
    # path — which in turn cannot read params on such models (no
    # SetParameterValue either). Keep the probe strictly to the methods we
    # actually call below.
    if hasattr(avatar._model, "LoadExpression") and \
            hasattr(avatar._model, "SetExpression"):
        try:
            if not item_layer:
                # Facial switch: cleanly deactivate the previous FACE
                # only — loaded item files stay active (stacking).
                prev = avatar._active_expression_name
                if prev and prev != name:
                    try:
                        avatar._model.DeleteExpression(prev)
                    except Exception:
                        pass
            avatar._model.LoadExpression(path)
            avatar._model.SetExpression(name, 1.0)
            with avatar._lock:
                if not item_layer:
                    avatar._active_expression_name = name
                avatar._current_expression = label or avatar._current_expression
            logger.info("Expression applied (native): %s (%s)",
                        label or stem, name)
            return True
        except Exception as e:
            logger.error(f"Native expression '{label or stem}' failed: {e}; "
                         f"falling back to parameter emulation")

    try:
        # --- Emulated path: apply exp3 parameters directly ---
        # 1) Prefer parameters already parsed during discovery (no re-read).
        #    Match case-insensitively on the stem so an on-disk file named
        #    "FZ.exp3.json" still resolves via its catalog entry.
        params: dict[str, float] = {}
        for exp in avatar._expression_catalog.values():
            if exp3_stem(exp.file) == stem and exp.parameters:
                params = dict(exp.parameters)
                break

        # 2) Fallback: parse the file directly (handles uncatalogued files).
        if not params:
            import json
            raw = Path(path).read_text(encoding="utf-8-sig")
            data = json.loads(raw)
            for item in data.get("Parameters", []):
                pid = item.get("Id")
                val = item.get("Value")
                if isinstance(pid, str) and isinstance(val, (int, float)):
                    params[pid] = float(val)

        # 3) Release parameters owned by the previously active FACE.
        #    Item (accessory/prop) files are NEVER released here — items
        #    persist across mood switches and only change through the
        #    explicit enable_item()/disable_item() layer.
        face_stems = {exp3_stem(e.file)
                      for e in avatar._expression_catalog.values()
                      if e.kind != KIND_ITEM}
        item_stems = {exp3_stem(e.file)
                      for e in avatar._expression_catalog.values()
                      if e.kind == KIND_ITEM}
        for old_stem, old_ids in list(avatar._expression_owned.items()):
            if old_stem == stem:
                continue
            is_face = (old_stem in face_stems
                       or (not face_stems and old_stem not in item_stems))
            if not is_face:
                continue  # keep active item layers untouched
            for pid in old_ids:
                # Only release ids this new expression doesn't also set.
                if pid not in params:
                    try:
                        avatar._model.ResetParameterValue(pid)
                    except Exception:
                        try:
                            # Older builds: reset by setting default-ish 0.
                            avatar._model.SetParameterValue(pid, 0.0)
                        except Exception:
                            pass
            avatar._expression_owned.pop(old_stem, None)

        # 4) Apply the expression's parameter values.
        applied = 0
        skipped = 0
        for pid, val in params.items():
            try:
                avatar._model.SetParameterValue(pid, float(val))
                applied += 1
            except Exception:
                skipped += 1
        if applied == 0 and skipped > 0:
            logger.warning("Expression '%s': all %d parameter(s) failed to "
                           "apply from %s", label or stem, skipped, path)
            return False

        avatar._expression_params = dict(params)
        avatar._expression_owned[stem] = set(params.keys())
        with avatar._lock:
            avatar._active_expression_name = name
            avatar._current_expression = label or avatar._current_expression
        logger.info("Expression applied (params): %s (%s, %d param(s)%s)",
                    label or stem, name, applied,
                    f", {skipped} skipped" if skipped else "")
        return True
    except FileNotFoundError:
        logger.error("Expression file not found: %s", path)
        return False
    except Exception as e:
        logger.error("Failed to apply expression '%s' from %s: %s",
                     label or "?", path, e)
        return False


def reset_expressions(avatar: Any) -> bool:
    """Release all FACIAL-expression-driven parameters (归零 equivalent).

    Note: 归零 (Reset/Return to Zero) in VTube Studio is a built-in app
    action (HotkeyReset), NOT one of this model's .exp3.json files. We
    reproduce its effect here instead of inventing an expression file:
    every parameter currently owned by an applied FACIAL expression is
    reset back to the model default via ResetParameterValue.

    IMPORTANT: This clears the FACE ONLY. Active ITEMS (kind="item"
    accessories/props tracked in self._active_items) are never released
    here — items persist until explicitly removed via disable_item().
    """
    if not avatar._initialized or not avatar._model:
        return False
    try:
        # Which exp3 stems belong to discovered facial expressions vs
        # items (case-insensitive stems; see exp3_stem).
        face_stems = {exp3_stem(e.file)
                      for e in avatar._expression_catalog.values()
                      if e.kind != KIND_ITEM}
        item_stems = {exp3_stem(e.file)
                      for e in avatar._expression_catalog.values()
                      if e.kind == KIND_ITEM}
        # Stems currently owned by enabled items must be preserved.
        active_item_stems = set(avatar._active_items.values())

        # 1) Release parameters owned by emulated FACIAL expressions
        #    (reset to model defaults — works on every live2d-py build).
        kept_params: dict[str, float] = {}
        for stem, ids in list(avatar._expression_owned.items()):
            is_item_layer = (stem in item_stems
                             or stem in active_item_stems
                             or (stem not in face_stems and item_stems
                                 and stem not in face_stems))
            if is_item_layer:
                # Keep item layers (owned params + values) intact.
                for pid in ids:
                    if pid in avatar._expression_params:
                        kept_params[pid] = avatar._expression_params[pid]
                continue
            for pid in ids:
                try:
                    avatar._model.ResetParameterValue(pid)
                except Exception:
                    try:
                        avatar._model.SetParameterValue(pid, 0.0)
                    except Exception:
                        pass
            avatar._expression_owned.pop(stem, None)
        avatar._expression_params = kept_params

        # 2) Legacy native-expression cleanup: delete only the active
        #    FACIAL expression file (harmless on builds without
        #    DeleteExpression, e.g. live2d-py 0.7.0.4). Items loaded via
        #    the native path stay active.
        names = {avatar._active_expression_name}
        for n in names:
            if not n:
                continue
            try:
                avatar._model.DeleteExpression(n)
            except Exception:
                pass
        with avatar._lock:
            avatar._active_expression_name = ""
            avatar._current_expression = "neutral"
        logger.debug("Facial expressions reset (归零 equivalent); items kept")
        return True
    except Exception as e:
        logger.error(f"reset_expressions failed: {e}")
        return False
