"""AI VTuber - Live2D Model File & Metadata Discovery

Pure-Python (no live2d-py / OpenGL required) discovery layer for Cubism 3
(.model3.json) models. Used by:

- ``ai_vtuber.avatar.live2d.Live2DAvatar`` at model-load time (to validate
  files, build the semantic expression catalog, and print startup diagnostics)
- ``scripts/live2d_standalone_test.py`` / ``tests/test_live2d_integration.py``
  (headless verification without a GPU)

Responsibilities:
- Resolve every referenced file of a model from its .model3.json
  (moc3 / physics / cdi3 / pose / expressions list), instead of assuming
  filenames. Replacing the model later requires no code changes.
- Parse the CDI3 (.cdi3.json) metadata: parameter ids, groups, parts.
- Scan the model directory for *.exp3.json expression files and parse each
  one's actual parameter ids/values (never trusting UI-reported counts).
- Classify parameters into tracking / expression / internal buckets so the
  AI behaviour layer is never exposed to hundreds of generated ArtMesh
  rotation deformers.
- Provide a deterministic semantic-id -> expression-file mapping
  (e.g. "angry" -> "ku.exp3.json"), with built-in defaults for known VTube
  Studio naming conventions plus config-driven overrides.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter classification
# ---------------------------------------------------------------------------

# Generated/hard-coded ArtMesh rotation deformers etc. — needed by the
# Live2D runtime but must NOT be exposed to the LLM/avatar behaviour layer.
_INTERNAL_PATTERNS = [
    re.compile(r"^Param_Angle_Rotation", re.IGNORECASE),
    re.compile(r"_ArtMesh\d+", re.IGNORECASE),
    re.compile(r"^ParamPartOpacity", re.IGNORECASE),
]

# Head/body/eye/breath tracking parameters (driven by tracking or by our
# own animation code — lip sync, blinking, mouse look).
_TRACKING_KEYWORDS = [
    "anglex", "angley", "anglez", "bodyangle", "eyeball",
    "breath", "centerx", "centery",
]

# Facial/behaviour parameters the AI layer may legitimately touch.
_EXPRESSION_KEYWORDS = [
    "eye", "brow", "mouth", "cheek", "nose", "jaw", "smile",
    "face", "facepinch", "hair", "sweat", "tear", "blush",
]


def classify_parameter(param_id: str) -> str:
    """Classify a Live2D parameter id into 'internal', 'tracking' or 'expression'.

    Returns:
        One of: "internal" | "tracking" | "expression".
    """
    for pattern in _INTERNAL_PATTERNS:
        if pattern.search(param_id):
            return "internal"

    normalized = re.sub(r"[^a-z0-9]", "", param_id.lower())
    if any(k in normalized for k in _TRACKING_KEYWORDS):
        return "tracking"
    if any(k in normalized for k in _EXPRESSION_KEYWORDS):
        return "expression"
    # Unknown short params (e.g. Param21, Param48 custom mouth shapes) are
    # treated as expression-capable; they stay settable via the clean API.
    return "expression"


# ---------------------------------------------------------------------------
# Built-in semantic expression-name dictionary
# ---------------------------------------------------------------------------
# Kind of a discovered expression file:
#   "expression" — a facial/mood look (crying, angry, star eyes...). Exactly
#                  ONE of these is active at a time; switching moods replaces it.
#   "item"       — a toggleable accessory / prop (glasses, hat, bow, ghost,
#                  wand, mic, controller...). Items are INDEPENDENT of each
#                  other and of the active expression: they stack/co-exist and
#                  are toggled on/off explicitly. Never mapped from moods.
KIND_EXPRESSION = "expression"
KIND_ITEM = "item"

# Maps an ASCII "semantic hint" (usually the pinyin abbreviation used in the
# .exp3.json filename) to (semantic_id, english_description, emoji, kind).
# Config `avatar.expression_semantics` can override/add entries per model.
DEFAULT_SEMANTIC_NAMES: dict[str, tuple[str, str, str, str]] = {
    # --- facial expressions (5) — mood-driven, mutually exclusive ---
    "fz":  ("black_face",         "Black Face / Dark Face", "😠", KIND_EXPRESSION),
    "hdj": ("crying",             "Crying",                "😭", KIND_EXPRESSION),
    "ku":  ("angry",              "Angry",                 "😡", KIND_EXPRESSION),
    "mz":  ("heart_eyes",         "Heart Eyes",            "🥰", KIND_EXPRESSION),
    "sq":  ("star_eyes",          "Star Eyes / Sparkly Eyes", "🤩", KIND_EXPRESSION),
    # --- item / accessory toggles (7) — stack with each other + expressions ---
    "cw":  ("little_ghost",       "Little Ghost",          "👻", KIND_ITEM),
    "h":   ("bow",                "Bow",                   "🎀", KIND_ITEM),
    "x":   ("glasses",            "Glasses",               "👓", KIND_ITEM),
    "xx":  ("gaming_gesture",     "Gaming Gesture",        "🎮", KIND_ITEM),
    "yj":  ("microphone_gesture", "Microphone Gesture",    "🎤", KIND_ITEM),
    "zs1": ("magic_wand",         "Magic Wand",            "🪄", KIND_ITEM),
    "zs2": ("hat",                "Hat",                   "🎩", KIND_ITEM),
}

# Backward-compatible aliases for the old "*_toggle" item ids. Anything that
# still references an alias (configs, saved state, older prompts) resolves to
# the canonical id above via ALIAS_TO_SEMANTIC_ID.
ITEM_ID_ALIASES: dict[str, str] = {
    "bow_toggle":         "bow",
    "glasses_toggle":     "glasses",
    "hat_toggle":         "hat",
    "magic_wand_summon":  "magic_wand",
}

# Reverse lookup: canonical semantic id -> default (exp3 filename stem,
# description, emoji, kind). Used by the avatar controller to translate the
# config.yaml `live2d.expressions` / `live2d.items` semantic blocks into the
# per-model `expression_semantics` overrides understood by discovery.
SEMANTIC_ID_DEFAULTS: dict[str, tuple[str, str, str, str]] = {
    sid: (stem, desc, emoji, kind)
    for stem, (sid, desc, emoji, kind) in DEFAULT_SEMANTIC_NAMES.items()
}

# VTube Studio per-model hotkey file (<model_name>.vtube.json) layout:
#   Hotkeys[].Type == "HotkeyExpressionParameter" carries
#   { "Name": <Chinese display name>, "Path": <exp3 filename>,
#     "Hotkey": "Q", "ToggleKey": ... }
# We read it purely for metadata (hotkey chars + authoritative display
# names). It NEVER overrides the discovered *.exp3.json files themselves.
_VTUBE_HOTKEY_TYPE = "HotkeyExpressionParameter"


def load_vtube_hotkeys(model3_path: Path | str) -> dict[str, dict]:
    """Parse ``<model_name>.vtube.json`` next to a .model3.json if present.

    Returns a mapping of expression FILENAME -> {"hotkey": str, "name": str}.
    Missing/unparseable files simply yield an empty dict (never raises).
    """
    result: dict[str, dict] = {}
    try:
        p = Path(model3_path)
        vtube = p.parent / f"{p.name[: -len('.model3.json')]}.vtube.json"
        if not vtube.is_file():
            candidates = sorted(p.parent.glob("*.vtube.json"))
            vtube = candidates[0] if candidates else None
        if vtube is None:
            return result
        with open(vtube, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        for hk in data.get("Hotkeys", []) or []:
            if not isinstance(hk, dict):
                continue
            if hk.get("Type") != _VTUBE_HOTKEY_TYPE:
                continue
            fname = str(hk.get("Path") or "").strip()
            if not fname:
                continue
            entry = result.setdefault(fname, {})
            key = str(hk.get("Hotkey") or "").strip()
            if key and not entry.get("hotkey"):
                entry["hotkey"] = key
            name = str(hk.get("Name") or "").strip()
            if name and not entry.get("name"):
                entry["name"] = name
    except Exception as e:  # robustness: never break discovery over metadata
        logger.debug("Could not read .vtube.json hotkey metadata: %s", e)
    return result


# Fallback semantic ids derived from Chinese display names (CDI ExpName or
# the "Name" field inside the exp3.json), when no better match exists.
CHINESE_NAME_FALLBACK: dict[str, tuple[str, str, str, str]] = {
    "小幽灵切换": ("little_ghost", "Little Ghost", "👻", KIND_ITEM),
    "黑脸": ("black_face", "Black Face / Dark Face", "😠", KIND_EXPRESSION),
    "蝴蝶结切换": ("bow", "Bow", "🎀", KIND_ITEM),
    "哭哭": ("crying", "Crying", "😭", KIND_EXPRESSION),
    "生气": ("angry", "Angry", "😡", KIND_EXPRESSION),
    "爱心眼": ("heart_eyes", "Heart Eyes", "🥰", KIND_EXPRESSION),
    "星星眼": ("star_eyes", "Star Eyes / Sparkly Eyes", "🤩", KIND_EXPRESSION),
    "眼镜切换": ("glasses", "Glasses", "👓", KIND_ITEM),
    "打游戏手势": ("gaming_gesture", "Gaming Gesture", "🎮", KIND_ITEM),
    "话筒手势": ("microphone_gesture", "Microphone Gesture", "🎤", KIND_ITEM),
    "法杖召唤": ("magic_wand", "Magic Wand", "🪄", KIND_ITEM),
    "帽子切换": ("hat", "Hat", "🎩", KIND_ITEM),
    # VTube Studio UI action "归零" (reset-to-zero) is NOT an expression
    # file on this model — it is VTube Studio's HotkeyReset action. If a
    # future model ships a real reset exp3.json, it maps here:
    "归零": ("reset", "Reset / Return To Zero", "🔄", KIND_EXPRESSION),
}


@dataclass
class ExpressionInfo:
    """Metadata for one discovered .exp3.json expression."""
    id: str                     # semantic id used by the AI layer ("angry")
    name: str                   # display name (Chinese, from the exp3 file)
    description: str            # English description
    emoji: str                  # icon for diagnostics/UI
    file: str                   # e.g. "ku.exp3.json"
    path: str                   # absolute path
    hotkey: str = ""            # optional (config-provided; not in exp3 files)
    parameters: dict[str, float] = field(default_factory=dict)
    kind: str = KIND_EXPRESSION  # "expression" (mood face) | "item" (toggleable accessory)

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "emoji": self.emoji,
            "file": self.file,
            "path": self.path,
            "hotkey": self.hotkey,
            "kind": self.kind,
            "parameter_count": self.parameter_count,
            "parameters": dict(self.parameters),
        }


@dataclass
class DiscoveredModel:
    """Everything we can learn about a Live2D model from its files alone."""
    root: Path
    model3_path: Path
    model_name: str
    moc3_path: Optional[Path] = None
    physics_path: Optional[Path] = None
    cdi3_path: Optional[Path] = None
    pose_path: Optional[Path] = None
    texture_paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)      # fatal-ish problems
    warnings: list[str] = field(default_factory=list)    # non-fatal problems
    parameter_ids: list[str] = field(default_factory=list)
    parameter_groups: list[dict] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    combined_parameters: list[str] = field(default_factory=list)
    expressions: list[ExpressionInfo] = field(default_factory=list)

    # -- convenience ------------------------------------------------------
    @property
    def parameter_count(self) -> int:
        return len(self.parameter_ids)

    def param_set(self) -> set[str]:
        return set(self.parameter_ids)

    def classified_parameters(self) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = {"tracking": [], "expression": [], "internal": []}
        for pid in self.parameter_ids:
            buckets[classify_parameter(pid)].append(pid)
        return buckets

    def expression_by_id(self, semantic_id: str) -> Optional[ExpressionInfo]:
        for exp in self.expressions:
            if exp.id == semantic_id:
                return exp
        return None

    def expressions_of_kind(self, kind: str) -> list[ExpressionInfo]:
        """All discovered files of one kind ('expression' or 'item')."""
        return [e for e in self.expressions if e.kind == kind]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_model(model3_json: Path | str,
                   expression_directory: Path | str | None = None,
                   semantic_overrides: dict[str, dict] | None = None,
                   hotkeys: dict[str, str] | None = None) -> DiscoveredModel:
    """Discover all files/metadata of a Cubism 3 model from its .model3.json.

    Args:
        model3_json: Path to the .model3.json file.
        expression_directory: Optional override for where *.exp3.json files
            are scanned (defaults to the model directory + expressions/ subdir).
        semantic_overrides: Per-model semantic id overrides, keyed by the
            expression filename stem, e.g.::

                {"ku": {"id": "angry", "name": "生气", "description": "Angry",
                        "emoji": "😡"}}

        hotkeys: Optional map of filename-stem -> hotkey char (metadata only;
            hotkeys live in VTube Studio, not in exp3.json files).

    Returns:
        DiscoveredModel (possibly with errors/warnings populated).

    Raises:
        FileNotFoundError: if the .model3.json itself does not exist.
        ValueError: if the .model3.json cannot be parsed / has no FileReferences.
    """
    model3_path = Path(model3_json).expanduser().resolve()
    if not model3_path.is_file():
        raise FileNotFoundError(f"Model file not found: {model3_path}")

    try:
        with open(model3_path, "r", encoding="utf-8-sig") as f:
            model_data = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse {model3_path.name}: {e}") from e

    refs = model_data.get("FileReferences")
    if not isinstance(refs, dict):
        raise ValueError(f"{model3_path.name} is missing a valid 'FileReferences' section")

    root = model3_path.parent
    dm = DiscoveredModel(
        root=root,
        model3_path=model3_path,
        model_name=model3_path.stem.replace(".model3", ""),
    )

    def resolve(rel: Any) -> Optional[Path]:
        if not rel or not isinstance(rel, str):
            return None
        p = (root / rel).resolve()
        return p if p.is_file() else None

    # --- referenced files -------------------------------------------------
    dm.moc3_path = resolve(refs.get("Moc"))
    if dm.moc3_path is None:
        # Fallback auto-discovery: scan the model dir for *.moc3
        candidates = sorted(root.glob("*.moc3"))
        if candidates:
            dm.moc3_path = candidates[0]
            dm.warnings.append(
                f"Moc reference '{refs.get('Moc')}' missing/unreadable; "
                f"auto-discovered {candidates[0].name} instead")
        else:
            dm.errors.append(
                f"No .moc3 file found (referenced: {refs.get('Moc')!r}, "
                f"searched {root})")

    dm.physics_path = resolve(refs.get("Physics"))
    if refs.get("Physics") and dm.physics_path is None:
        dm.warnings.append(f"Physics file missing (optional): {refs['Physics']}")

    dm.pose_path = resolve(refs.get("Pose"))

    for tex in refs.get("Textures", []) or []:
        tp = resolve(tex)
        if tp:
            dm.texture_paths.append(tp)
        else:
            dm.errors.append(f"Texture file missing: {tex}")

    # Expressions declared inside the model3.json (may be empty even though
    # exp3.json files exist on disk — common for VTube Studio models).
    declared_exp_files: set[str] = set()
    for exp in model_data.get("expressions", []) or []:
        if isinstance(exp, dict) and exp.get("File"):
            declared_exp_files.add(Path(str(exp["File"])).name)

    # --- CDI3 -------------------------------------------------------------
    cdi_rel = refs.get("DisplayInfos") or refs.get("Cdi")  # some exporters vary
    dm.cdi3_path = resolve(cdi_rel) if isinstance(cdi_rel, str) else None
    if dm.cdi3_path is None:
        stem = model3_path.name[: -len(".model3.json")] if model3_path.name.endswith(".model3.json") else model3_path.stem
        candidate = root / f"{stem}.cdi3.json"
        if candidate.is_file():
            dm.cdi3_path = candidate
        else:
            candidates = sorted(root.glob("*.cdi3.json"))
            if candidates:
                dm.cdi3_path = candidates[0]
    if dm.cdi3_path:
        _load_cdi(dm.cdi3_path, dm)
    else:
        dm.warnings.append(
            "No .cdi3.json found — parameter/group/part metadata unavailable; "
            "runtime parameter access will rely on the loaded model only.")

    # --- expressions ------------------------------------------------------
    exp_dirs: list[Path] = []
    if expression_directory:
        exp_dirs.append(Path(expression_directory).expanduser())
    exp_dirs.append(root)
    exp_dirs.append(root / "expressions")
    exp_dirs.append(root / "Exp")

    # VTube Studio per-model metadata (hotkey chars + display names), read
    # from <model>.vtube.json next to the .model3.json when it exists.
    vtube_meta = load_vtube_hotkeys(model3_path)

    seen_files: set[str] = set()
    for d in exp_dirs:
        if not d.is_dir():
            continue
        for exp_file in sorted(d.glob("*.exp3.json")):
            if exp_file.name in seen_files:
                continue
            seen_files.add(exp_file.name)
            info = _parse_expression(exp_file, declared_exp_files,
                                     semantic_overrides or {}, hotkeys or {},
                                     vtube_meta.get(exp_file.name, {}))
            if info is not None:
                dm.expressions.append(info)

    # Duplicate semantic id detection (keep first occurrence, rename dupes)
    _dedupe_expression_ids(dm)

    # Normalize legacy "*_toggle" ids that may come from older configs or
    # per-model overrides (bow_toggle -> bow, glasses_toggle -> glasses, ...).
    for exp in dm.expressions:
        canon = ITEM_ID_ALIASES.get(exp.id)
        if canon:
            exp.id = canon

    return dm


def _load_cdi(cdi_path: Path, dm: DiscoveredModel) -> None:
    """Parse CDI3 metadata into the DiscoveredModel (non-fatal on errors)."""
    try:
        with open(cdi_path, "r", encoding="utf-8-sig") as f:
            cdi = json.load(f)
    except Exception as e:
        dm.warnings.append(f"Failed to parse CDI file {cdi_path.name}: {e}")
        return

    groups = cdi.get("Groups") or {}
    # Per the Cubism CDI spec, "Groups" is a LIST of group objects
    # ({Name, Ids}); some exporters emit a dict layout instead — support both.
    if isinstance(groups, list):
        param_groups = [g for g in groups if isinstance(g, dict)
                        and (g.get("Name") or "").lower() == "parameters"]
        part_groups = [g for g in groups if isinstance(g, dict)
                       and (g.get("Name") or "").lower() == "parts"]

        def _ids(g: dict) -> list[str]:
            return [i for i in (g.get("Ids") or []) if isinstance(i, str)]

        for grp in param_groups:
            dm.parameter_groups.append({
                "id": grp.get("GroupId", ""),
                "name": grp.get("GroupName", "") or grp.get("Name", ""),
                "params": _ids(grp),
            })
            for pid in _ids(grp):
                if pid not in dm.parameter_ids:
                    dm.parameter_ids.append(pid)
        for pg in part_groups:
            for pid in _ids(pg):
                if pid not in dm.parts:
                    dm.parts.append(pid)
    else:
        for grp in groups.get("ParameterGroups", []) or []:
            dm.parameter_groups.append({
                "id": grp.get("GroupId", ""),
                "name": grp.get("GroupName", ""),
                "params": [p.get("Id") for p in (grp.get("Parameters") or []) if p.get("Id")],
            })
            for p in grp.get("Parameters", []) or []:
                pid = p.get("Id")
                if pid and pid not in dm.parameter_ids:
                    dm.parameter_ids.append(pid)

        for part in (groups.get("Parts", []) or []):
            pid = part.get("Id")
            if pid:
                dm.parts.append(pid)

        # Alternate CDI layout: PartGroups with PartIds lists
        for pg in (groups.get("PartGroups", []) or []):
            for pid in (pg.get("PartIds", []) or []):
                if pid and pid not in dm.parts:
                    dm.parts.append(pid)

    for cp in cdi.get("CombinedParameters", []) or []:
        if isinstance(cp, list):
            for item in cp:
                if isinstance(item, dict) and item.get("Id"):
                    dm.combined_parameters.append(item["Id"])

    # Some CDIs list parameters outside groups too:
    for p in (cdi.get("Parameters") or []):
        pid = p.get("Id") if isinstance(p, dict) else None
        if pid and pid not in dm.parameter_ids:
            dm.parameter_ids.append(pid)


_EXP_ID_SANITIZE = re.compile(r"[^a-z0-9_]+")


def _slug(name: str) -> str:
    s = _EXP_ID_SANITIZE.sub("_", name.strip().lower()).strip("_")
    return s or "expression"


def _parse_expression(exp_file: Path,
                      declared_files: set[str],
                      semantic_overrides: dict[str, dict],
                      hotkeys: dict[str, str],
                      vtube_meta: Optional[dict] = None) -> Optional[ExpressionInfo]:
    """Parse one .exp3.json into ExpressionInfo. Broken files are skipped."""
    stem = exp_file.name[: -len(".exp3.json")] if exp_file.name.endswith(".exp3.json") else exp_file.stem
    vtube_meta = vtube_meta or {}

    try:
        with open(exp_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("Malformed expression file %s: %s (skipping)", exp_file.name, e)
        return None

    params: dict[str, float] = {}
    for entry in data.get("Parameters", []) or []:
        if isinstance(entry, dict) and entry.get("Id"):
            try:
                params[str(entry["Id"])] = float(entry.get("Value", 0.0))
            except (TypeError, ValueError):
                logger.warning("Expression %s has invalid value for %r (ignored)",
                               exp_file.name, entry.get("Id"))

    override = semantic_overrides.get(stem, {})
    # Display-name precedence: explicit config override > VTube Studio
    # .vtube.json Name (authoritative — matches the VTS UI exactly) >
    # the exp3.json's own "Name" field > filename stem.
    display_name = str(override.get("name") or vtube_meta.get("name")
                       or data.get("Name") or stem)

    sem: Optional[tuple[str, str, str, str]] = None
    kind = KIND_EXPRESSION
    if "id" in override:
        default_desc = DEFAULT_SEMANTIC_NAMES.get(stem, ("", "", "", ""))[1]
        default_emoji = DEFAULT_SEMANTIC_NAMES.get(stem, ("", "", "", "🙂"))[2]
        default_kind = DEFAULT_SEMANTIC_NAMES.get(stem, ("", "", "", KIND_EXPRESSION))[3]
        sem = (str(override["id"]),
               str(override.get("description", default_desc)),
               str(override.get("emoji", default_emoji) or "🙂"),
               str(override.get("kind", default_kind)))
    elif stem in DEFAULT_SEMANTIC_NAMES:
        sem = DEFAULT_SEMANTIC_NAMES[stem]
    elif display_name in CHINESE_NAME_FALLBACK:
        sem = CHINESE_NAME_FALLBACK[display_name]
    else:
        sem = (_slug(stem), display_name, "🙂", KIND_EXPRESSION)
    kind = sem[3] if len(sem) > 3 else KIND_EXPRESSION

    info = ExpressionInfo(
        id=sem[0],
        name=display_name,
        description=sem[1] or display_name,
        emoji=sem[2],
        file=exp_file.name,
        path=str(exp_file.resolve()),
        hotkey=str(hotkeys.get(stem, "") or vtube_meta.get("hotkey", "")),
        parameters=params,
        kind=kind,
    )
    if exp_file.name not in declared_files:
        logger.debug("Expression %s not declared in .model3.json (VTube Studio "
                     "models often omit them); discovered from disk.", exp_file.name)
    return info


def _dedupe_expression_ids(dm: DiscoveredModel) -> None:
    seen: dict[str, int] = {}
    for exp in dm.expressions:
        if exp.id in seen:
            seen[exp.id] += 1
            new_id = f"{exp.id}_{seen[exp.id]}"
            logger.warning("Duplicate expression id '%s' (from %s); renamed to '%s'",
                           exp.id, exp.file, new_id)
            exp.id = new_id
        else:
            seen[exp.id] = 0


# ---------------------------------------------------------------------------
# Startup diagnostic
# ---------------------------------------------------------------------------

def format_diagnostic(dm: DiscoveredModel) -> str:
    """Build the human-readable startup diagnostic block."""
    lines = [
        "Live2D Model",
        "------------",
        f"Name: {dm.model_name}",
        f"Model: {dm.model3_path.name}",
        f"MOC3: {dm.moc3_path.name if dm.moc3_path else 'MISSING'}",
        f"CDI: {dm.cdi3_path.name if dm.cdi3_path else 'not found (optional)'}",
        f"Physics: {dm.physics_path.name if dm.physics_path else 'not found (optional)'}",
        "",
        f"Parameters: {dm.parameter_count}",
        f"Parameter Groups: {len(dm.parameter_groups)}",
        f"Parts: {len(dm.parts)}",
        f"Combined Parameters: {len(dm.combined_parameters)}",
        f"Expressions: {sum(1 for e in dm.expressions if e.kind == KIND_EXPRESSION)}",
        f"Item Toggles: {sum(1 for e in dm.expressions if e.kind == KIND_ITEM)}",
        "",
        "Facial expressions (mood-driven, one active at a time):",
    ]
    faces = [e for e in dm.expressions if e.kind != KIND_ITEM]
    items = [e for e in dm.expressions if e.kind == KIND_ITEM]
    if faces:
        width = max(len(e.id) for e in faces)
        for e in faces:
            hk = f" [{e.hotkey}]" if e.hotkey else ""
            lines.append(f"  {e.emoji} {e.id:<{width}} -> {e.file}{hk}  "
                         f"({e.name}, {e.parameter_count} param(s))")
    else:
        lines.append("  (none discovered)")
    lines += ["", "Item toggles (stack with each other and with the face):"]
    if items:
        width = max(len(e.id) for e in items)
        for e in items:
            hk = f" [{e.hotkey}]" if e.hotkey else ""
            lines.append(f"  {e.emoji} {e.id:<{width}} -> {e.file}{hk}  "
                         f"({e.name}, {e.parameter_count} param(s))")
    else:
        lines.append("  (none discovered)")

    buckets = dm.classified_parameters()
    lines += [
        "",
        f"Parameter classes: tracking={len(buckets['tracking'])}, "
        f"expression={len(buckets['expression'])}, internal={len(buckets['internal'])}",
    ]
    for w in dm.warnings:
        lines.append(f"  WARNING: {w}")
    for err in dm.errors:
        lines.append(f"  ERROR: {err}")
    return "\n".join(lines)
