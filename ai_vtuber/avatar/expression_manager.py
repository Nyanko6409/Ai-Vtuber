"""AI VTuber - Live2D facial expression state & resolution.

Owns the FACIAL-expression half of the avatar's semantic layer:

* mood -> expression defaults (``DEFAULT_EXPRESSIONS``) and the parameter
  fallback table (``EMOTION_PARAMS``),
* resolving any accepted reference (semantic id / emotion / display name /
  file stem) to a discovered ``ExpressionInfo`` + path,
* triggering an expression by semantic id (items are rejected here — they
  belong to :mod:`ai_vtuber.avatar.item_manager`),
* the neutral reset (a logical state with NO .exp3.json file that clears
  the face only; active items are preserved),
* building the runtime mood -> expression map for startup diagnostics.

The low-level "apply one exp3 file to the runtime model" logic lives in
:mod:`ai_vtuber.avatar.expression_apply` to keep the dependency flow clean:

    expression_manager  ->  expression_apply  ->  (avatar duck-typed state)

Functions receive the avatar instance (duck-typed) and mutate its
expression state attributes (``_current_expression``,
``_active_expression_name``, ``_expression_owned``, ...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .model_discovery import (
    DEFAULT_SEMANTIC_NAMES,
    EXPRESSION_FILES,
    FACIAL_EXPRESSIONS,
    ITEMS,
    FACIAL_ID_ALIASES,
    canonicalize_semantic_id,
    exp3_stem,
    KIND_EXPRESSION,
    KIND_ITEM,
    ExpressionInfo,
)
from .expression_apply import load_expression_file, reset_expressions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AIRI LIVE2D AVATAR SHEET — expressions vs items, two SEPARATE systems.
#
# This is the single authoritative avatar definition for behaviour code.
# The actual .exp3.json assets live OUTSIDE this repository (external VTube
# Studio install, configured via avatar.model_path); nothing here copies or
# modifies model asset files.
#
#   FACIAL EXPRESSIONS (kind="expression") — exactly ONE active at a time;
#   changing the expression REPLACES the previous one but NEVER removes
#   items. Airi's LLM decides autonomously which expression fits (there is
#   NO hardcoded mood -> expression mapping anymore — see
#   ai_vtuber/avatar/avatar_control.py):
#
#     neutral      — no expression file; default state; use when no strong
#                    visual emotion is appropriate
#     dark_face    — h.exp3.json   😶  dark/awkward/deadpan comedic reaction
#     bow          — hdj.exp3.json 🎀  cute/feminine moments, styling
#     cry          — ku.exp3.json  😭  genuine sadness, emotional moments
#     angry        — sq.exp3.json  😡  genuine irritation/frustration
#     heart_eyes   — x.exp3.json   🥰  strong affection / deeply charmed
#     star_eyes    — xx.exp3.json  🤩  excitement / amazement / fascination
#
#   ITEMS / ACCESSORIES (kind="item") — MULTIPLE may be active at the same
#   time; they stack with each other and with the active expression. Adding
#   or removing an item NEVER changes the expression. Items persist until
#   Airi decides to remove them (see ai_vtuber/avatar/item_manager.py):
#
#     ghosts           — cw.exp3.json 👻  ghost/spooky/supernatural jokes
#     wand             — fz.exp3.json 🪄  magic / fantasy roleplay
#     hat              — mz.exp3.json 🎩  dressing up, character RP
#     glasses          — yj.exp3.json 👓  studying, coding, reading, nerdy
#     gamer_controller — zs1.exp3.json 🎮 gaming talk / roleplay
#     mic              — zs2.exp3.json 🎤 singing, streaming, performing
#
# The single authoritative filename -> semantic mapping lives in
# model_discovery.EXPRESSION_FILES (derived FACIAL_EXPRESSIONS / ITEMS);
# this block documents it, code must never re-hardcode filenames.
#
# Avatar state rules (enforced by AvatarController + validated here):
#   * Expression: max ONE active; change replaces; does NOT remove items.
#   * Items: many active; toggle does NOT change the expression.
#   * The USER never commands the avatar directly; the LLM decides via
#     structured {"avatar_action": ...} JSON (or chooses no action at all).
# ---------------------------------------------------------------------------

# Semantic ids of the 6 (+neutral) facial expressions on the canonical
# Live2D sheet (model_discovery.EXPRESSION_FILES / FACIAL_EXPRESSIONS —
# the single source of truth; this is derived, never a duplicate catalog).
FACIAL_EXPRESSION_IDS: tuple[str, ...] = ("neutral", *sorted(FACIAL_EXPRESSIONS))


def is_canonical_facial_id(name: Any) -> bool:
    """True iff ``name`` (case-insensitive) is one of the six canonical
    facial expression ids or the "neutral" reset state.

    This is the avatar-action-boundary whitelist: personality/mood words
    the LLM may hallucinate (smug, happy, sad, excited, ...) are NOT Live2D
    expressions and must never reach trigger_expression()/load_expression_file().
    """
    return str(name or "").strip().casefold() in FACIAL_EXPRESSION_IDS


def reject_non_facial(name: Any, context: str) -> Optional[str]:
    """Validate one LLM-supplied expression reference at the boundary.

    Returns the canonical facial id on success ("neutral" included), or
    None after logging a clear warning. Unsupported names — arbitrary mood
    text such as "smug" — are IGNORED, never guessed onto a real face and
    never looked up in the catalog (so no "Unknown expression" noise comes
    out of the resolver for pure personality tags).
    """
    if is_canonical_facial_id(name):
        return str(name).strip().casefold()
    logger.warning(
        "Unsupported avatar expression %r; ignoring avatar expression tag "
        "(canonical facial ids: %s)",
        str(name)[:60], ", ".join(FACIAL_EXPRESSION_IDS))
    return None


# ---------------------------------------------------------------------------
# DEFAULT_EXPRESSIONS — mood -> expression defaults. The default is NONE:
# every supported mood maps to "" (plain default face, no .exp3.json).
# Mood/emotion may still exist as internal conversational context
# (see ai_vtuber/emotion/analyzer.py) but it must NEVER automatically drive
# the Live2D expression. The LLM's autonomous avatar decision has priority.
# To opt back in to mood-driven faces, override per-mood targets via config:
#   avatar:
#     expressions:
#       happy: "star_eyes"
# ---------------------------------------------------------------------------
DEFAULT_EXPRESSIONS: dict[str, str] = {
    "neutral": "",      # plain default face (no exp3 file)
    "happy": "",
    "sad": "",
    "angry": "",
    "surprised": "",
    "embarrassed": "",
    # extended mood tags (explicit-tag only; keyword detection still uses
    # the six core categories above)
    "excited": "",
    "loving": "",
    "thinking": "",
    "sleepy": "",
    "gaming": "",
    "singing": "",
    "smug": "",
    "performing": "",
}

# Parameter fallback overrides keyed by SEMANTIC expression id (NOT mood).
# Used ONLY when no matching .exp3.json file can be resolved — e.g. a
# different model with fewer files. Values use standard Cubism param ids
# which are auto-resolved to the loaded model's actual ids.
# Legacy parameter-fallback faces, keyed by the OLD semantic id -> params.
_LEGACY_EMOTION_PARAMS: dict[str, dict[str, float]] = {
    "neutral": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0, "ParamMouthOpenY": 0.0},
    "black_face": {"ParamEyeLOpen": 0.9, "ParamEyeROpen": 0.9, "ParamBrowLY": -0.3, "ParamFaceDark": 1.0},
    "crying": {"ParamEyeLOpen": 0.5, "ParamEyeROpen": 0.5, "ParamBrowLY": -0.9, "ParamMouthOpenY": 0.15},
    "angry": {"ParamEyeLOpen": 0.8, "ParamEyeROpen": 0.8, "ParamBrowLY": -1.0, "ParamMouthOpenY": 0.1, "Param53": 1.0},
    "heart_eyes": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0, "ParamMouthOpenY": 0.2, "ParamBrowLY": 0.6, "ParamEyeLSmile": 0.8, "ParamEyeRSmile": 0.8},
    "star_eyes": {"ParamEyeLOpen": 1.2, "ParamEyeROpen": 1.2, "ParamMouthOpenY": 0.5, "ParamBrowLY": 1.0, "ParamEyeLSmile": 1.0, "ParamEyeRSmile": 1.0},
}

# EMOTION_PARAMS keyed by the NEW canonical semantic ids: each legacy face
# keeps its fallback parameters but follows the FILE it was authored for
# (e.g. the old "angry" face drove ku.exp3.json, which the canonical sheet
# names "cry"). Values are only used when no .exp3.json can be resolved.
EMOTION_PARAMS: dict[str, dict[str, float]] = {"neutral": _LEGACY_EMOTION_PARAMS["neutral"]}
for _legacy_key, _legacy_params in _LEGACY_EMOTION_PARAMS.items():
    if _legacy_key == "neutral":
        continue
    _canon = canonicalize_semantic_id(_legacy_key)
    if _canon in EXPRESSION_FILES:
        EMOTION_PARAMS[_canon] = _legacy_params
del _legacy_key, _legacy_params, _canon


# ---------------------------------------------------------------------------
# Mood -> expression triggering (semantic, deterministic; no LLM filenames)
# ---------------------------------------------------------------------------

EMOTION_EXPRESSION_MAP: dict[str, str] = {k: v for k, v in DEFAULT_EXPRESSIONS.items()}


def build_mood_expression_map(avatar: Any,
                              emotion_map: Optional[dict[str, str]] = None,
                              ) -> dict[str, str]:
    """Build the runtime mood -> expression mapping for one loaded model.

    Starts from the default emotion map merged with config overrides
    (``avatar.expressions``), then keeps only entries whose target actually
    resolves against the avatar's discovered expression catalog. Moods whose
    target is missing on this model are dropped (the caller then falls back
    to parameter-based faces), so switching models never breaks mood logic.

    Returns: {emotion: semantic_expression_id}
    """
    merged = {**DEFAULT_EXPRESSIONS, **(emotion_map or {})}
    result: dict[str, str] = {}
    for emotion, target in merged.items():
        exp, path = resolve_semantic_expression(avatar, target)
        if path:
            result[emotion] = (exp.id if exp else target)
        else:
            logger.debug("Mood '%s' -> expression '%s' not available on this "
                         "model; will use parameter fallback", emotion, target)
    return result


def sanitize_expressions_map(avatar: Any) -> None:
    """Validate mood -> expression targets against the loaded catalog.

    Rules (see DEFAULT_EXPRESSIONS comment block):
    - An empty/whitespace target means "plain default face" (kept).
    - A target that resolves to a kind="item" file is REJECTED — items
      are toggled explicitly via toggle_item(), never driven by moods.
    - A target that doesn't resolve at all is kept (the caller falls
      back to parameter-driven faces) unless it names a known item stem.
    """
    cleaned: dict[str, str] = {}
    for mood, target in avatar.expressions_map.items():
        t = (target or "").strip()
        if not t:
            cleaned[mood] = ""
            continue
        exp, _path = resolve_semantic_expression(avatar, t)
        if exp is not None:
            # Persist the CANONICAL sheet id (not a legacy spelling) so
            # downstream lookups always hit the current catalog.
            t = exp.id
        if exp is not None and exp.kind == KIND_ITEM:
            logger.warning(
                "Mood '%s' maps to '%s' which is an ITEM toggle, not a "
                "facial expression — ignoring this mapping (items are "
                "toggled with [item_on:...]/[item_off:...] instead).",
                mood, t)
            cleaned[mood] = ""
            continue
        cleaned[mood] = t
    avatar.expressions_map = cleaned


def resolve_semantic_expression(avatar: Any,
                                name: str) -> tuple[Optional[ExpressionInfo], str]:
    """Resolve any accepted expression reference to (ExpressionInfo, path).

    Accepts, in order of precedence:
    1. semantic id ("angry")          -> ku.exp3.json via catalog
    2. emotion name ("angry")         -> config expressions map
    3. display name ("生气")           -> catalog lookup by name
    4. file stem ("ku") or filename ("ku.exp3.json") -> direct file

    Legacy ids from the previous naming scheme (``glasses_toggle`` /
    ``bow_toggle`` / ``little_ghost`` / ``black_face`` / ...) are normalized
    to the canonical semantic ids of the new sheet via
    :func:`model_discovery.canonicalize_semantic_id` before lookup, so old
    configs and saved state still resolve instead of logging "Unknown
    expression".
    """
    key = (name or "").strip()
    if not key:
        return None, ""
    # "neutral" is a VALID state with no .exp3.json file by design: it
    # means "plain default face". Resolve it to the reset sentinel
    # (None, "") BEFORE any catalog lookup so it never logs an
    # "Unknown expression" warning. Callers treat an empty path as
    # "reset the facial layer" (trigger_expression / set_expression).
    if key.casefold() == "neutral":
        return None, ""
    # Canonicalize legacy aliases case-insensitively (Glasses_Toggle etc.)
    lowered = key.lower().replace(" ", "_").replace("-", "_")
    canonical = canonicalize_semantic_id(lowered)
    if canonical != lowered:
        key = canonical

    exp = avatar._expression_catalog.get(key)
    if exp:
        return exp, exp.path

    # Emotion -> semantic id (configurable via avatar.expressions).
    # SAFEGUARD: a mood target must resolve to a KNOWN catalog entry —
    # unknown words are never probed as raw filenames (that would let a
    # hallucinated mood name like "smug" load a same-named .exp3.json).
    mapped = avatar.expressions_map.get(key)
    if mapped and mapped != key:
        mapped_key = str(mapped).strip().casefold()
        exp = avatar._expression_catalog.get(mapped_key)
        if exp:
            return exp, exp.path
        logger.warning(
            "Unsupported avatar expression %r; ignoring avatar expression "
            "tag (mood target %r is not a known expression on this model)",
            name, mapped)
        return None, ""

    # Display-name lookup (Chinese names)
    for e in avatar._expression_catalog.values():
        if e.name == key:
            return e, e.path

    # Display-name lookup on the *canonicalized* key too: legacy configs may
    # carry an OLD semantic id ("crying") as a mood target. Canonicalization
    # renames it to the current sheet id ("bow"), which no longer equals the
    # Chinese display name stored in the exp3 file — without this second
    # pass such targets would silently stop resolving after a rename.
    if key != (name or "").strip():
        for e in avatar._expression_catalog.values():
            if e.name == key:
                return e, e.path

    # Direct file stem / filename lookup — ONLY for ids that exist in the
    # canonical discovery catalog (stem-level check of the sheet); arbitrary
    # LLM/mood words never reach the filesystem here.
    if key in DEFAULT_SEMANTIC_NAMES or key in {
            exp3_stem(f) for f in EXPRESSION_FILES.values()}:
        fname = key if key.endswith(".exp3.json") else f"{key}.exp3.json"
        search_dirs: list[Path] = []
        # Preferred: the directory discovery actually scanned (honours
        # avatar.expression_directory overrides).
        discovered_dir = getattr(avatar._discovered, "root", None) \
            if avatar._discovered is not None else None
        if discovered_dir is not None:
            search_dirs.append(Path(discovered_dir))
        if avatar._model_path:
            model_dir = avatar._model_path.parent
            search_dirs.extend((model_dir, model_dir / "expressions",
                                model_dir / "Exp"))
        for search_dir in search_dirs:
            candidate = search_dir / fname
            if candidate.exists():
                return None, str(candidate)

    logger.warning("Unknown expression '%s' (no semantic id, emotion, "
                   "display name, or file match)", name)
    return None, ""


def trigger_expression(avatar: Any, expression_id: str) -> bool:
    """Trigger an expression by SEMANTIC id (e.g. "angry", "heart_eyes").

    This is the deterministic API for the AI/LLM behaviour layer:
    semantic ids are translated to concrete .exp3.json files here —
    the LLM never needs to know filenames.

    ``trigger_expression("neutral")`` (or an empty id) is a VALID reset
    operation: it clears the facial-expression layer back to the plain
    default face and returns True. It never loads "neutral.exp3.json"
    (no such file exists by design) and never warns. Active ITEMS are
    preserved.

    Returns True if the expression was applied (or the reset succeeded).
    """
    if not avatar._initialized or not avatar._model:
        logger.debug("trigger_expression('%s') ignored: model not initialized",
                     expression_id)
        return False

    # BOUNDARY VALIDATION: only the six canonical facial ids (+ neutral, and
    # legacy sheet aliases that canonicalize onto them) may be triggered as
    # expressions. Personality/mood words from the LLM ("smug", "happy",
    # ...) are NOT Live2D expressions — reject them here with a clear
    # warning instead of probing the catalog (which would log
    # "Unknown expression 'smug'" and could load an arbitrary same-named
    # .exp3.json file). Items keep their own API (enable_item()).
    key = (expression_id or "").strip().casefold()
    if key and key != "neutral" \
            and canonicalize_semantic_id(key) not in FACIAL_EXPRESSIONS:
        logger.warning(
            "Unsupported avatar expression '%s'; ignoring avatar "
            "expression tag (canonical facial ids: %s)",
            expression_id, ", ".join(FACIAL_EXPRESSION_IDS))
        return False

    # Neutral / explicit reset: valid state, no .exp3.json involved.
    if not (expression_id or "").strip() or \
            (expression_id or "").strip().casefold() == "neutral":
        return reset_expressions(avatar)

    exp, path = resolve_semantic_expression(avatar, expression_id)
    if not path:
        # Resolution failed. If the name was a known FACIAL semantic id
        # whose file is simply missing/broken on disk, fall back to the
        # parameter-driven face instead of failing hard; otherwise treat
        # any other unresolved-but-empty case as neutral reset.
        raw_key = (expression_id or "").strip().lower()
        sem = DEFAULT_SEMANTIC_NAMES.get(raw_key)
        if not sem:
            # The caller may have used an OLD semantic id from the previous
            # naming scheme; resolve it through the canonical alias table.
            canon = canonicalize_semantic_id(raw_key)
            stem = next((st for st, (sid, *_r) in DEFAULT_SEMANTIC_NAMES.items()
                         if sid == canon), None)
            sem = DEFAULT_SEMANTIC_NAMES.get(stem) if stem else None
        if sem and sem[3] == KIND_EXPRESSION:
            logger.warning(
                "trigger_expression('%s'): expression file missing; "
                "using parameter fallback", expression_id)
            with avatar._lock:
                avatar._current_expression = sem[0]
            set_expression_params(avatar, sem[0])
            return True
        return False
    # Guard the two-layer contract: an ITEM must never be triggered as a
    # facial expression (use enable_item()/disable_item() for items).
    if exp is not None and exp.kind == KIND_ITEM:
        logger.warning(
            "trigger_expression('%s'): '%s' is an ITEM — use "
            "enable_item()/disable_item() instead.", expression_id, exp.id)
        return False
    return load_expression_file(
        avatar, path, label=(exp.id if exp else expression_id))


def set_expression(avatar: Any, emotion: str) -> None:
    """Set avatar expression based on emotion.

    An empty/whitespace ``emotion`` means "no expression": the face is
    reset to the plain default (the DEFAULT_EXPRESSIONS default is now
    "" for every mood, so mood changes land here and clear the face —
    only an explicit LLM avatar_action sets a real expression).

    Resolution order (all deterministic, no LLM-side filenames needed):
    1. semantic id / display name / file stem via the discovered catalog
       (e.g. "angry" -> ku.exp3.json, "heart_eyes" -> mz.exp3.json)
    2. legacy raw filename search ({name}.exp3.json in model dir)
    3. parameter-based fallback (EMOTION_PARAMS) so the face still works
       even with zero expression files present.
    """
    if not avatar._initialized or not avatar._model:
        return

    if not (emotion or "").strip() or \
            (emotion or "").strip().casefold() == "neutral":
        # "none" / "neutral" / plain default face: release any active
        # expression parameters (items untouched) and stop here. There is
        # intentionally NO neutral.exp3.json — never try to load one.
        reset_expressions(avatar)
        return

    # BOUNDARY VALIDATION (mood path): bracket tags such as [smug] are
    # legacy MOOD/personality annotations extracted by the emotion
    # analyzer — they are NOT Live2D expression commands and must never
    # reach the catalog resolver / trigger_expression() (which would log
    # "Unknown expression 'smug'" and could load an arbitrary same-named
    # .exp3.json file). Only the six canonical facial ids (+ "neutral")
    # or a configured mood name may arrive here; anything else simply
    # resets the face to neutral. No warning is emitted for plain mood
    # words on purpose — they are expected conversational context, and
    # per-mood targets are "" by default (DEFAULT_EXPRESSIONS /
    # config avatar.expressions), meaning "plain default face".
    key = (emotion or "").strip().casefold()
    key_norm = key.replace(" ", "_").replace("-", "_")
    # A CURRENT canonical facial id is always accepted as-is; a legacy
    # spelling is accepted only if it canonicalizes onto one of the six
    # current faces (e.g. old "crying" -> hdj = "bow").
    if key_norm in FACIAL_EXPRESSIONS:
        canonical_id = key_norm
    else:
        canon = canonicalize_semantic_id(key_norm)
        canonical_id = canon if canon in FACIAL_EXPRESSIONS else ""
    if not canonical_id and key not in avatar.expressions_map:
        logger.debug(
            "Mood %r is not a Live2D expression; resetting face to "
            "neutral (canonical facial ids: %s)",
            emotion, ", ".join(FACIAL_EXPRESSION_IDS))
        reset_expressions(avatar)
        return

    # FIX: Protect shared state with lock
    with avatar._lock:
        avatar._current_expression = emotion

    # 1) Emotion -> semantic id via the (config-overridable) expression
    #    map FIRST, so e.g. mood "happy" triggers star_eyes even if the
    #    model happens to ship a file literally named happy.exp3.json.
    #    A mood whose target is "" (the DEFAULT_EXPRESSIONS default)
    #    means "no expression": fall through to the direct-match steps,
    #    which resolve a canonical facial id to its file and reset the
    #    face for everything else.
    mapped = avatar.expressions_map.get(emotion, "")
    if mapped and mapped != emotion:
        exp, path = resolve_semantic_expression(avatar, mapped)
        if path and load_expression_file(
                avatar, path, label=(exp.id if exp else mapped)):
            return

    # 2) Canonical facial id / display name direct match against the
    #    discovered catalog ONLY. The raw mood word is never probed as a
    #    filename here — that legacy step could load an arbitrary
    #    same-named .exp3.json for a pure mood tag (e.g. smug.exp3.json).
    if canonical_id:
        exp = avatar._expression_catalog.get(canonical_id)
        if exp and exp.path:
            if load_expression_file(avatar, exp.path, label=exp.id):
                return
        elif canonical_id in EMOTION_PARAMS:
            # Known canonical face whose file is missing on this model:
            # parameter-driven fallback.
            logger.debug("No expression file for '%s'; "
                         "using parameter fallback", canonical_id)
            set_expression_params(avatar, canonical_id)
            return

    # 3) No Live2D target for this mood (every DEFAULT_EXPRESSIONS entry
    #    maps to "" unless overridden in config): plain default face.
    #    This is where conversational mood tags such as "smug" end up —
    #    they reset the face instead of triggering anything.
    reset_expressions(avatar)


def set_expression_params(avatar: Any, emotion: str) -> None:
    """Set expression via model parameters."""
    if not avatar._model:
        return
    # Map standard-name dict keys to this model's resolved actual IDs
    # (only eye/mouth are auto-resolved; other params pass through as-is)
    id_overrides = {
        "ParamEyeLOpen": avatar._param_eye_l_open,
        "ParamEyeROpen": avatar._param_eye_r_open,
        "ParamMouthOpenY": avatar._param_mouth_open,
    }
    # Try the raw mood name first, then the semantic id it maps to.
    params = EMOTION_PARAMS.get(emotion)
    if params is None:
        mapped = avatar.expressions_map.get(emotion, "")
        params = EMOTION_PARAMS.get(mapped) or EMOTION_PARAMS["neutral"]
    for param_id, value in params.items():
        resolved_id = id_overrides.get(param_id, param_id)
        try:
            avatar._model.SetParameterValue(resolved_id, value)
        except Exception as e:
            logger.error(f"Live2D param error (expression '{resolved_id}'): {e}")


def set_emotion(avatar: Any, emotion: str) -> bool:
    """Set the facial expression from an emotion/mood/semantic name.

    Backwards-compatible alias used by older pipelines/tests:
    ``set_emotion("")`` / ``set_emotion("neutral")`` reset the FACE only
    (items stay on); any other value behaves like trigger_expression().
    """
    if not (emotion or "").strip() or \
            (emotion or "").strip().casefold() == "neutral":
        if not avatar._initialized or not avatar._model:
            return False
        return reset_expressions(avatar)
    return trigger_expression(avatar, emotion)


def apply_action_tag(avatar: Any, tag: str) -> bool:
    """Apply one structured avatar action tag. Never raises.

    Accepted forms (canonical runtime actions; all take SEMANTIC ids —
    filenames are resolved internally by the discovery catalog):

        expression:<id> | item_on:<id> | item_off:<id>
        mode_on:<mode>  | mode_off:<mode>

    ``expression:neutral`` (and empty ids) reset the face only. Items
    and modes never touch the face; expressions never touch items.
    Unknown ids/modes log a warning and return False.
    """
    # Imported lazily: item_manager imports this module at module level,
    # so a top-level import here would create an import cycle.
    from . import item_manager, mode_manager

    text = str(tag or "").strip().strip("[]")
    action, _, arg = text.partition(":")
    action = action.strip().casefold()
    arg = arg.strip()
    if action == "expression":
        # BOUNDARY: bracket tags like [smug] are legacy mood/personality
        # annotations, NOT avatar expression commands. Only the six
        # canonical facial ids (+ neutral) may drive trigger_expression();
        # anything else is ignored with a clear warning (and never falls
        # through to another action type).
        from .model_discovery import FACIAL_EXPRESSIONS as _FACIAL
        from .model_discovery import canonicalize_semantic_id as _canon
        key = (arg or "neutral").casefold()
        if key != "neutral" and _canon(key) not in _FACIAL:
            logger.warning(
                "apply_action_tag: unsupported avatar expression %r; "
                "ignoring avatar expression tag", arg)
            return False
        return trigger_expression(avatar, arg or "neutral")
    if action == "item_on":
        return item_manager.enable_item(avatar, arg)
    if action == "item_off":
        return item_manager.disable_item(avatar, arg)
    if action == "mode_on":
        return mode_manager.enable_mode(avatar, arg)
    if action == "mode_off":
        return mode_manager.disable_mode(avatar, arg)
    logger.warning("apply_action_tag: unknown action %r", tag)
    return False
