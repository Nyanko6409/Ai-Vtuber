"""AI VTuber - Live2D Avatar Module

Handles Live2D model loading, rendering, expressions, and animations.
CRITICAL: Checks Python/native compatibility BEFORE importing to prevent SIGSEGV.
"""

import logging
import math
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Any

import numpy as np

from .model_discovery import (
    DEFAULT_SEMANTIC_NAMES,
    ITEM_ID_ALIASES,
    KIND_EXPRESSION,
    KIND_ITEM,
    DiscoveredModel,
    ExpressionInfo,
    classify_parameter,
    discover_model,
    exp3_stem,
    format_diagnostic,
)

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
#     black_face   — fz.exp3.json  😶  dark/awkward/deadpan comedic reaction
#                    (awkward silence, disbelief, uncomfortable comedy).
#                    Never interpret the name literally as a racial expression.
#     crying       — hdj.exp3.json 😭  genuine sadness, emotional moments,
#                    sympathy, dramatic crying
#     angry        — ku.exp3.json  😠  genuine irritation/frustration, being
#                    provoked, appropriate mock anger
#     heart_eyes   — mz.exp3.json  🥰  strong affection / deeply charmed
#                    (not for every compliment)
#     star_eyes    — sq.exp3.json  🤩  excitement / amazement / fascination
#
#   ITEMS / ACCESSORIES (kind="item") — MULTIPLE may be active at the same
#   time; they stack with each other and with the active expression. Adding
#   or removing an item NEVER changes the expression. Items persist until
#   Airi decides to remove them:
#
#     little_ghost        — cw.exp3.json  👻  ghost/spooky/supernatural jokes
#     bow                 — h.exp3.json   🎀  cute/feminine moments, styling
#     glasses             — x.exp3.json   👓  studying, coding, reading, nerdy
#     gaming_gesture      — xx.exp3.json  🎮  gaming talk / roleplay
#     microphone_gesture  — yj.exp3.json  🎤  singing, streaming, performing
#     magic_wand          — zs1.exp3.json 🪄  magic / fantasy roleplay
#     hat                 — zs2.exp3.json 🎩  dressing up, character RP
#
# Avatar state rules (enforced by AvatarController + validated here):
#   * Expression: max ONE active; change replaces; does NOT remove items.
#   * Items: many active; toggle does NOT change the expression.
#   * The USER never commands the avatar directly; the LLM decides via
#     structured {"avatar_action": ...} JSON (or chooses no action at all).
# ---------------------------------------------------------------------------

# Semantic ids of the 5 (+neutral) facial expressions on Airi's sheet.
FACIAL_EXPRESSION_IDS: tuple[str, ...] = (
    "neutral", "black_face", "crying", "angry", "heart_eyes", "star_eyes",
)

# Semantic ids of the 7 stackable items on Airi's sheet.
ITEM_IDS: tuple[str, ...] = (
    "little_ghost", "bow", "glasses", "gaming_gesture",
    "microphone_gesture", "magic_wand", "hat",
)

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
EMOTION_PARAMS: dict[str, dict[str, float]] = {
    "neutral": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0, "ParamMouthOpenY": 0.0},
    "black_face": {"ParamEyeLOpen": 0.9, "ParamEyeROpen": 0.9, "ParamBrowLY": -0.3, "ParamFaceDark": 1.0},
    "crying": {"ParamEyeLOpen": 0.5, "ParamEyeROpen": 0.5, "ParamBrowLY": -0.9, "ParamMouthOpenY": 0.15},
    "angry": {"ParamEyeLOpen": 0.8, "ParamEyeROpen": 0.8, "ParamBrowLY": -1.0, "ParamMouthOpenY": 0.1, "Param53": 1.0},
    "heart_eyes": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0, "ParamMouthOpenY": 0.2, "ParamBrowLY": 0.6, "ParamEyeLSmile": 0.8, "ParamEyeRSmile": 0.8},
    "star_eyes": {"ParamEyeLOpen": 1.2, "ParamEyeROpen": 1.2, "ParamMouthOpenY": 0.5, "ParamBrowLY": 1.0, "ParamEyeLSmile": 1.0, "ParamEyeRSmile": 1.0},
}


def _find_live2d_package_path() -> Optional[Path]:
    """Find the live2d package location WITHOUT importing it.
    
    This is critical to prevent SIGSEGV from loading incompatible native extensions.
    """
    import importlib.util
    
    try:
        spec = importlib.util.find_spec("live2d")
        if spec and spec.origin:
            return Path(spec.origin).parent
    except (ImportError, AttributeError, ValueError):
        pass
    
    # Fallback: search sys.path
    for path in sys.path:
        live2d_path = Path(path) / "live2d"
        if live2d_path.is_dir() and (live2d_path / "__init__.py").exists():
            return live2d_path
    
    return None


def _check_native_compatibility(package_path: Path) -> tuple[bool, str]:
    """Check if the native .so files are compatible with current Python version.
    
    Returns (is_compatible, error_message).
    """
    current_python = f"cp{sys.version_info.major}{sys.version_info.minor}"
    
    # Find all .so files
    so_files = list(package_path.glob("*.so")) + list(package_path.glob("**/*.so"))
    
    if not so_files:
        return True, ""  # No native files, assume compatible
    
    # Check each .so file
    for so_file in so_files:
        try:
            # Read first 50KB to check for Python version markers
            with open(so_file, 'rb') as f:
                content = f.read(50000)
            
            # Look for Python version markers in the binary
            for py_ver in ['cp38', 'cp39', 'cp310', 'cp311', 'cp312', 'cp313']:
                if py_ver.encode() in content:
                    if py_ver != current_python:
                        error_msg = (
                            f"Python version mismatch detected!\n"
                            f"  Current Python: {current_python} (Python {sys.version_info.major}.{sys.version_info.minor})\n"
                            f"  live2d-py native extension built for: {py_ver}\n"
                            f"  This will cause SIGSEGV (segmentation fault).\n"
                            f"\n"
                            f"SOLUTION - Choose one:\n"
                            f"  Option A: Install Python {sys.version_info.major}.{sys.version_info.minor} compatible live2d-py\n"
                            f"    pip uninstall live2d-py\n"
                            f"    pip install live2d-py  # Try to get correct version\n"
                            f"\n"
                            f"  Option B: Use Python that matches live2d-py\n"
                            f"    If live2d-py is for Python 3.12, use Python 3.12:\n"
                            f"    sudo apt install python3.12 python3.12-venv\n"
                            f"    python3.12 -m venv venv312\n"
                            f"    source venv312/bin/activate\n"
                            f"    pip install -r requirements.txt\n"
                        )
                        return False, error_msg
                    else:
                        # Found matching version
                        return True, ""
            
            # No version marker found - can't determine
            logger.debug(f"Could not determine Python version for {so_file.name}")
            
        except Exception as e:
            logger.debug(f"Could not check {so_file}: {e}")
    
    return True, ""  # Assume compatible if we can't determine


def _fix_mojibake(text: str) -> str:
    """Repair text that was decoded as cp1252/latin-1 but is really UTF-8.

    On Windows, ``open()`` without an explicit encoding uses the system code
    page (cp1252 / cp936 / ...).  A config.yaml saved as UTF-8 containing
    non-ASCII paths (e.g. 魔女) then loads as garbled text like 'é­"å¥³'.
    Re-encoding through the original code page recovers the real string.
    Returns the input unchanged if it is not double-decoded UTF-8.
    """
    if not text or text.isascii():
        return text
    for enc in ("cp1252", "latin-1"):
        try:
            fixed = text.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        # Only accept when the repair actually changed something and the
        # result contains no replacement chars / control junk.
        if fixed != text and "\ufffd" not in fixed:
            return fixed
    return text


def _repair_path_on_fs(p: Path) -> Optional[Path]:
    """Last-resort recovery: walk the path components and match each one
    case-insensitively against its parent directory listing.

    This fixes paths whose characters got mangled by a wrong text decoding
    (or wrong case on Windows): a directory literally named 'é­"å¥³'
    does not exist but '魔女' does — scanning the parent finds it.
    Returns a Path that exists on disk, or None.
    """
    try:
        resolved = Path(os.path.abspath(str(p)))
    except (OSError, ValueError):
        return None

    # Collect the chain of components down to the deepest existing ancestor.
    missing: list[str] = []
    cur = resolved
    while not cur.exists():
        parent = cur.parent
        if parent == cur:  # reached filesystem root
            return None
        missing.insert(0, cur.name)
        cur = parent

    for name in missing:
        try:
            entries = list(cur.iterdir())
        except OSError:
            return None
        match = next((e for e in entries if e.name == name), None)
        if match is None:
            match = next(
                (e for e in entries if e.name.casefold() == name.casefold()),
                None,
            )
        if match is None:
            fixed = _fix_mojibake(name)
            if fixed != name:
                match = next((e for e in entries if e.name == fixed), None)
                if match is None:
                    match = next(
                        (e for e in entries
                         if e.name.casefold() == fixed.casefold()),
                        None,
                    )
        if match is None:
            return None
        cur = match
    return cur if cur.exists() else None


def _resolve_model_path(raw_path: str) -> Optional[Path]:
    """Resolve and validate a Live2D model path.
    
    Supports:
    - Absolute paths (Windows, Linux, WSL)
    - Relative paths (resolved from project root)
    - Paths with spaces
    - Environment variable expansion
    
    Args:
        raw_path: Raw path string from configuration
        
    Returns:
        Resolved Path object if valid, None otherwise
    """
    if not raw_path or not raw_path.strip():
        return None

    # Repair double-decoded UTF-8 before touching the filesystem.
    raw_path = _fix_mojibake(raw_path)

    p = Path(raw_path).expanduser()

    # Some code pages (e.g. cp936/GBK on Chinese Windows) mangle the whole
    # string differently than per-component; try a component-wise repair too.
    if not p.exists():
        parts = p.parts
        candidate = Path(*[_fix_mojibake(part) for part in parts])
        if candidate != p and candidate.exists():
            logger.info(
                f"Live2D model path repaired component-wise:\n"
                f"  {p}\n  -> {candidate}"
            )
            p = candidate
    
    # If path is relative, resolve it relative to the project root
    # Project root is 2 levels up from ai_vtuber/avatar/live2d.py
    if not p.is_absolute():
        try:
            project_root = Path(__file__).resolve().parents[2]
            p = project_root / p
        except Exception as e:
            logger.warning(f"Could not determine project root for relative path: {e}")
    
    p = p.resolve()

    if not p.exists():
        recovered = _repair_path_on_fs(p)
        if recovered is not None:
            logger.warning(
                f"Live2D model path did not match exactly; recovered via "
                f"directory scan:\n  {p}\n  -> {recovered}"
            )
            p = recovered

    if not p.exists():
        logger.error("Live2D model not found:")
        logger.error(f"{p}")
        logger.error(
            "Please update config.yaml 'avatar.model_path' (or 'avatar.models') to point to your Live2D model file.\n"
            "You can use:\n"
            "  - Absolute path: C:/Users/Name/Models/model.model3.json\n"
            "  - Relative path: assets/avatars/my_model/model.model3.json (from project root)\n"
            "  - WSL path: /mnt/e/SteamLibrary/.../model.model3.json"
        )
        return None

    if not p.is_file():
        logger.error(f"Live2D model path is not a file: {p}")
        return None

    if p.suffix.lower() != ".json":
        logger.error(f"Live2D model must be a .json file, got: {p.suffix}")
        return None

    return p


def _resolve_active_model(config: dict) -> tuple[str, Optional[str]]:
    """Resolve which model path to use from the avatar config block.

    Priority:
      1. avatar.active_model  -> name lookup in avatar.models registry
      2. first entry of avatar.models (if active_model empty/unknown)
      3. avatar.model_path    -> legacy single-path option

    Returns (path_string, selected_name). Path may be "" if nothing configured.
    """
    models = config.get("models") or {}
    active = str(config.get("active_model", "") or "").strip()

    if isinstance(models, dict) and models:
        names = list(models.keys())
        if active and active in models:
            chosen = active
        else:
            if active:
                logger.warning(
                    f"avatar.active_model '{active}' not found in avatar.models "
                    f"(available: {', '.join(names)}). Falling back to first entry."
                )
            chosen = names[0]
        entry = models[chosen] or {}
        path = entry.get("path", "") if isinstance(entry, dict) else str(entry)
        desc = entry.get("description", "") if isinstance(entry, dict) else ""
        logger.info(f"Live2D model selected by name: '{chosen}'"
                    + (f" ({desc})" if desc else "")
                    + f" -> {path}")
        return str(path), chosen

    # Legacy: single model_path
    return str(config.get("model_path", "") or ""), None


class Live2DAvatar:
    """Live2D avatar using live2d-py library.
    
    CRITICAL: Checks Python/native compatibility BEFORE importing to prevent SIGSEGV.
    FIX: Uses threading.Lock for thread-safe access to shared state from pipeline/render threads.
    """

    def __init__(self, config: dict) -> None:
        # ---- Model selection (config-driven, no code changes needed) -----
        # Preferred: pick a model by NAME from the 'models' registry:
        #   avatar:
        #     active_model: "majo"
        #     models:
        #       majo:  {path: ".../魔女.model3.json", description: "..."}
        #       ganyu: {path: ".../ganyu.model3.json"}
        # Fallback (legacy): avatar.model_path pointing directly at a .model3.json.
        resolved_path, selected_name = _resolve_active_model(config)
        self.active_model_name: Optional[str] = selected_name
        self.model_registry: dict = config.get("models", {}) or {}
        self.model_path_raw: str = resolved_path
        # Optional override for where *.exp3.json files are scanned;
        # defaults to the model's own directory (auto-discovery).
        self.expression_directory_raw: str = config.get("expression_directory", "")
        self.scale: float = config.get("scale", 2.0)
        self.expressions_map: dict[str, str] = {
            **DEFAULT_EXPRESSIONS,
            **config.get("expressions", {}),
        }
        # Per-model semantic expression overrides, keyed by exp3 filename stem:
        #   avatar:
        #     expression_semantics:
        #       ku: {id: angry, name: 生气, description: Angry, emoji: "😡"}
        self._semantic_overrides: dict[str, dict] = config.get("expression_semantics", {}) or {}
        self._expression_hotkeys: dict[str, str] = config.get("expression_hotkeys", {}) or {}

        self._live2d: Any = None
        self._live2d_version: int = 0
        self._model: Any = None

        # Discovered model metadata (files, CDI params, expression catalog).
        self._discovered: Optional[DiscoveredModel] = None
        # semantic id -> ExpressionInfo (built after discovery)
        self._expression_catalog: dict[str, ExpressionInfo] = {}
        # Valid parameter ids from the loaded runtime model (or CDI fallback)
        self._valid_param_ids: set[str] = set()

        # Expression emulation state (live2d-py 0.7.x has no LoadExpression API,
        # so we apply .exp3.json parameter sets ourselves):
        #   param_id -> value currently forced by the active expression(s)
        self._expression_params: dict[str, float] = {}
        #   exp3 filename stem -> set of param ids it owns (for clean switching)
        self._expression_owned: dict[str, set] = {}
        self._is_talking: bool = False
        self._current_expression: str = "neutral"
        # Filename (e.g. "ku.exp3.json") of the expression currently active
        # on the runtime model — tracked so mood switches can cleanly
        # deactivate the previous one (live2d-py keeps loaded expressions).
        self._active_expression_name: str = ""
        # --- item layer (accessories/props; independent of the face layer) ---
        # Semantic ids of all discovered kind="item" files (glasses, hat, ...)
        self._item_ids: set[str] = set()
        # Currently ON items, in toggle order: semantic id -> owning exp3 stem
        self._active_items: dict[str, str] = {}
        self._mouth_value: float = 0.0

        # Resolved parameter IDs — filled in after model load by _resolve_parameter_ids().
        # Default to Cubism standard names; will be corrected to whatever this
        # specific model actually uses, if different.
        self._param_mouth_open: str = "ParamMouthOpenY"
        self._param_eye_l_open: str = "ParamEyeLOpen"
        self._param_eye_r_open: str = "ParamEyeROpen"
        self._param_angle_x: str = "ParamAngleX"
        self._param_angle_y: str = "ParamAngleY"
        self._param_eye_ball_x: str = "ParamEyeBallX"
        self._param_eye_ball_y: str = "ParamEyeBallY"
        self._blink_timer: float = 0.0
        self._blink_interval: float = 3.0
        self._blink_duration: float = 0.15
        self._is_blinking: bool = False
        self._initialized: bool = False
        self._gl_initialized: bool = False
        self._error_message: Optional[str] = None
        self._model_path: Optional[Path] = None
        
        # Lip sync audio data
        self._lipsync_audio: Optional[np.ndarray] = None
        self._lipsync_rate: int = 0
        self._lipsync_start: float = 0.0
        self._lipsync_last_offset: int = 0
        
        # Zoom and position controls
        self._zoom: float = self.scale
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0
        self._min_zoom: float = 0.5
        self._max_zoom: float = 5.0
        
        # Store config reference for potential reloads
        self._config: dict = config
        
        # FIX: Thread safety lock for shared state accessed from pipeline/render threads
        self._lock = threading.Lock()

        # CRITICAL: Check compatibility BEFORE importing
        self._safe_import_live2d()

        # Pure-file model/expression discovery does NOT require the GPU
        # runtime, so run it here as well. This keeps the semantic
        # expression layer (trigger_expression / list_expressions) and the
        # startup diagnostic functional even on machines where live2d-py
        # is unavailable; _initialize() will refresh against the loaded
        # runtime when rendering is actually possible.
        # (Discovery runs regardless of whether the GPU runtime imported OK.)
        self._model_path = _resolve_model_path(self.model_path_raw)
        if self._model_path is not None:
            self._discover_model()

    def _safe_import_live2d(self) -> None:
        """Safely import live2d module with compatibility check.
        
        This prevents SIGSEGV by checking native extension compatibility first.
        """
        # Step 1: Find package location WITHOUT importing
        package_path = _find_live2d_package_path()
        
        if package_path is None:
            error_msg = (
                "live2d-py is not installed.\n"
                "Install with: pip install live2d-py\n"
                "Or download from: https://github.com/EasyLive2D/live2d-py/releases"
            )
            logger.error(error_msg)
            self._error_message = error_msg
            return
        
        logger.debug(f"Found live2d package at: {package_path}")
        
        # Step 2: Check native compatibility BEFORE importing
        is_compatible, error_msg = _check_native_compatibility(package_path)
        
        if not is_compatible:
            logger.error(error_msg)
            self._error_message = error_msg
            # DO NOT IMPORT - this would cause SIGSEGV
            return
        
        # Step 3: Safe to import
        try:
            import live2d.v3 as live2d
            self._live2d = live2d
            self._live2d_version = 3
            logger.info("live2d-py loaded successfully (Cubism v3)")
        except ImportError:
            try:
                import live2d.v2 as live2d
                self._live2d = live2d
                self._live2d_version = 2
                logger.info("live2d-py loaded successfully (Cubism v2)")
            except ImportError as e:
                error_msg = f"Failed to import live2d module: {e}"
                logger.error(error_msg)
                self._error_message = error_msg

    def init_gl(self) -> bool:
        """Initialize Live2D after OpenGL context exists."""
        if self._live2d is None:
            if self._error_message:
                logger.error(f"Cannot init_gl: {self._error_message}")
            else:
                logger.error("Cannot init_gl: live2d module not loaded")
            return False

        if self._gl_initialized:
            return self._initialized

        try:
            logger.debug("Calling live2d.init()...")
            self._live2d.init()
            logger.debug("live2d.init() successful")

            logger.debug("Calling live2d.glInit()...")
            self._live2d.glInit()
            logger.debug("live2d.glInit() successful")
            self._gl_initialized = True

        except Exception as e:
            error_msg = f"Live2D OpenGL initialization failed: {e}"
            logger.error(error_msg, exc_info=True)
            self._error_message = error_msg
            return False

        # Resolve model path
        self._model_path = _resolve_model_path(self.model_path_raw)
        if self._model_path is None:
            error_msg = (
                "No Live2D model configured.\n"
                "Set 'avatar.model_path' in config.yaml to a valid .model3.json file."
            )
            logger.warning(error_msg)
            self._error_message = error_msg
            self._initialized = False
            return False

        # Auto-discover all model files/metadata from the .model3.json
        # (moc3/physics/cdi3 + every *.exp3.json expression). This runs
        # BEFORE validation so we can report precise missing-file errors.
        self._discover_model()

        # Validate model files before loading
        if not self._validate_model_files():
            return False

        # Load model with enhanced error handling
        try:
            model_path_str = str(self._model_path)
            logger.info(f"Loading Live2D model: {model_path_str}")

            logger.debug("Creating LAppModel instance...")
            self._model = self._live2d.LAppModel()
            logger.debug("LAppModel instance created")
            
            logger.debug("Loading model JSON...")
            self._model.LoadModelJson(model_path_str)
            logger.debug("Model JSON loaded successfully")

            self._initialized = True
            logger.info(f"✓ Live2D model loaded successfully: {self._model_path.name}")
            logger.info(f"  Model directory: {self._model_path.parent}")

            self._resolve_parameter_ids()
            # One-time capability probe: live2d-py builds differ in their
            # expression API (0.7.x LAppModel has no LoadExpression at all).
            # We emulate expressions via SetParameterValue, so just log it.
            if not hasattr(self._model, "LoadExpression"):
                logger.info("live2d-py build has no LoadExpression API — "
                            "expressions will be applied by setting their "
                            ".exp3.json parameters directly (emulated).")
            self._log_startup_diagnostic()

        except Exception as e:
            error_msg = f"Failed to load Live2D model: {type(e).__name__}: {e}"
            logger.error(error_msg, exc_info=True)
            self._error_message = error_msg
            self._initialized = False
            self._model = None
            return False
        except BaseException as e:
            # Catch SIGSEGV and other fatal errors
            error_msg = f"Fatal error during model loading: {type(e).__name__}"
            logger.error(error_msg)
            self._error_message = error_msg
            self._initialized = False
            self._model = None
            return False

        return True

    def _validate_model_files(self) -> bool:
        """Validate that all required model files exist."""
        import json
        
        if not self._model_path or not self._model_path.exists():
            self._error_message = f"Model file does not exist: {self._model_path}"
            logger.error(self._error_message)
            return False

        model_dir = self._model_path.parent
        logger.info(f"Validating model files in: {model_dir}")

        try:
            with open(self._model_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
        except Exception as e:
            self._error_message = f"Failed to read model JSON: {e}"
            logger.error(self._error_message)
            return False

        # Check FileReferences
        if 'FileReferences' not in model_data:
            self._error_message = "Model JSON missing 'FileReferences' section"
            logger.error(self._error_message)
            return False

        refs = model_data['FileReferences']
        missing_files = []

        # Check moc3 file (required)
        if 'Moc' in refs:
            moc_path = model_dir / refs['Moc']
            if not moc_path.exists():
                missing_files.append(f"Moc: {moc_path}")
            else:
                logger.debug(f"✓ Moc file exists: {moc_path.name}")

        # Check textures (required)
        if 'Textures' in refs:
            for tex in refs['Textures']:
                tex_path = model_dir / tex
                if not tex_path.exists():
                    missing_files.append(f"Texture: {tex_path}")
                else:
                    logger.debug(f"✓ Texture exists: {tex_path.name}")

        # Check physics (optional but recommended)
        if 'Physics' in refs:
            phys_path = model_dir / refs['Physics']
            if not phys_path.exists():
                logger.warning(f"Physics file missing (optional): {phys_path}")
            else:
                logger.debug(f"✓ Physics file exists: {phys_path.name}")

        # Check pose (optional)
        if 'Pose' in refs:
            pose_path = model_dir / refs['Pose']
            if not pose_path.exists():
                logger.warning(f"Pose file missing (optional): {pose_path}")
            else:
                logger.debug(f"✓ Pose file exists: {pose_path.name}")

        # Check motions (optional)
        if 'motions' in model_data:
            motion_count = 0
            for group_name, group_data in model_data['motions'].items():
                if isinstance(group_data, list):
                    for motion in group_data:
                        if 'File' in motion:
                            motion_path = model_dir / motion['File']
                            if motion_path.exists():
                                motion_count += 1
                            else:
                                logger.warning(f"Motion file missing: {motion_path}")
            logger.debug(f"✓ Found {motion_count} motion files")

        # Check expressions (optional)
        if 'expressions' in model_data:
            exp_count = 0
            for exp in model_data['expressions']:
                if 'File' in exp:
                    exp_path = model_dir / exp['File']
                    if exp_path.exists():
                        exp_count += 1
                    else:
                        logger.warning(f"Expression file missing: {exp_path}")
            logger.debug(f"✓ Found {exp_count} expression files")

        # Report missing required files
        if missing_files:
            error_msg = "Missing required model files:\n" + "\n".join(f"  - {f}" for f in missing_files)
            logger.error(error_msg)
            self._error_message = error_msg
            return False

        logger.info("✓ All required model files validated")
        return True

    def _resolve_parameter_ids(self) -> None:
        """Discover this model's actual mouth/eye parameter IDs instead of
        assuming Cubism standard names.

        Some fan-rigged models (this includes many community VTube Studio
        models) use nonstandard, prefixed, or differently-cased parameter
        IDs. Blinking and lip sync silently do nothing if the ID we set
        doesn't exist on the model, so we look up the real IDs here.
        """
        try:
            all_ids = self._model.GetParamIds()
        except Exception as e:
            logger.warning(f"Could not query model parameter IDs, using Cubism defaults: {e}")
            return

        logger.debug(f"Model exposes {len(all_ids)} parameters: {all_ids}")

        def normalize(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())

        def find(needle: str, default: str, exact_aliases: list[str]) -> str:
            # 1. Exact match (case-insensitive) against known standard/alias names
            for pid in all_ids:
                if pid.lower() in (a.lower() for a in exact_aliases):
                    return pid
            # 2. Fuzzy match: normalized id contains the needle substring
            for pid in all_ids:
                if needle in normalize(pid):
                    return pid
            logger.warning(
                f"No parameter matching '{needle}' found on this model "
                f"(tried {exact_aliases}); falling back to '{default}', "
                f"which may not exist and will silently no-op."
            )
            return default

        self._param_mouth_open = find(
            "mouthopen", "ParamMouthOpenY",
            ["ParamMouthOpenY", "PARAM_MOUTH_OPEN_Y", "ParamMouthOpen"]
        )
        self._param_eye_l_open = find(
            "eyelopen", "ParamEyeLOpen",
            ["ParamEyeLOpen", "PARAM_EYE_L_OPEN"]
        )
        self._param_eye_r_open = find(
            "eyeropen", "ParamEyeROpen",
            ["ParamEyeROpen", "PARAM_EYE_R_OPEN"]
        )
        self._param_angle_x = find(
            "anglex", "ParamAngleX",
            ["ParamAngleX", "PARAM_ANGLE_X"]
        )
        self._param_angle_y = find(
            "angley", "ParamAngleY",
            ["ParamAngleY", "PARAM_ANGLE_Y"]
        )
        self._param_eye_ball_x = find(
            "eyeballx", "ParamEyeBallX",
            ["ParamEyeBallX", "PARAM_EYE_BALL_X"]
        )
        self._param_eye_ball_y = find(
            "eyebally", "ParamEyeBallY",
            ["ParamEyeBallY", "PARAM_EYE_BALL_Y"]
        )

        logger.info(
            f"Resolved parameters — mouth: '{self._param_mouth_open}', "
            f"eyeL: '{self._param_eye_l_open}', eyeR: '{self._param_eye_r_open}', "
            f"angleX: '{self._param_angle_x}', angleY: '{self._param_angle_y}', "
            f"eyeBallX: '{self._param_eye_ball_x}', eyeBallY: '{self._param_eye_ball_y}'"
        )

    # ------------------------------------------------------------------
    # Discovery / semantic expression layer
    # ------------------------------------------------------------------

    def _discover_model(self) -> None:
        """Run pure-file auto-discovery for the configured model.

        Populates self._discovered, self._expression_catalog and (as a
        fallback when the runtime is unavailable) self._valid_param_ids.
        Never raises: discovery failures are logged and leave the avatar
        in degraded-but-functional mode.
        """
        # If config.yaml has no per-model semantic overrides yet, fall back
        # to the built-in baked mapping so the documented expression table
        # (angry/heart_eyes/glasses_toggle/...) works out of the box.
        # DEFAULT_SEMANTIC_NAMES carries a 4th field: the kind
        # ("expression" facial mood face | "item" toggleable accessory).
        # (model_discovery.DEFAULT_SEMANTIC_NAMES is keyed by exp3 filename
        #  stems; an explicit config `expression_semantics` block always wins.)
        if not self._semantic_overrides:
            self._semantic_overrides = {
                stem: {"id": sid, "kind": kind}
                for stem, (sid, _desc, _emoji, kind) in DEFAULT_SEMANTIC_NAMES.items()
            }

        exp_dir = None
        if self.expression_directory_raw:
            candidate = Path(self.expression_directory_raw).expanduser()
            if not candidate.is_absolute():
                candidate = Path(__file__).resolve().parents[2] / candidate
            if candidate.is_dir():
                exp_dir = candidate
            else:
                logger.warning(
                    "avatar.expression_directory does not exist: %s "
                    "(falling back to model directory)", candidate)

        try:
            self._discovered = discover_model(
                self._model_path,
                expression_directory=exp_dir,
                semantic_overrides=self._semantic_overrides,
                hotkeys=self._expression_hotkeys,
            )
        except Exception as e:
            logger.error("Live2D model discovery failed: %s", e)
            self._discovered = None

        if self._discovered is None:
            return

        for err in self._discovered.errors:
            logger.error("Model discovery: %s", err)
        for warn in self._discovered.warnings:
            logger.warning("Model discovery: %s", warn)

        self._expression_catalog = {e.id: e for e in self._discovered.expressions}
        self._item_ids = {e.id for e in self._discovered.expressions
                          if e.kind == KIND_ITEM}
        if self._discovered.parameter_ids:
            self._valid_param_ids = set(self._discovered.parameter_ids)

        # Enforce the expression/item split on the mood map (config included):
        # moods may only target facial expressions; empty target = plain face.
        self._sanitize_expressions_map()

        n_faces = sum(1 for e in self._discovered.expressions
                      if e.kind != KIND_ITEM)
        logger.info(
            "Discovered model '%s': %d parameters, %d facial expressions, "
            "%d item toggles",
            self._discovered.model_name,
            self._discovered.parameter_count,
            n_faces,
            len(self._item_ids),
        )

    def _sanitize_expressions_map(self) -> None:
        """Validate mood -> expression targets against the loaded catalog.

        Rules (see DEFAULT_EXPRESSIONS comment block):
        - An empty/whitespace target means "plain default face" (kept).
        - A target that resolves to a kind="item" file is REJECTED — items
          are toggled explicitly via toggle_item(), never driven by moods.
        - A target that doesn't resolve at all is kept (the caller falls
          back to parameter-driven faces) unless it names a known item stem.
        """
        cleaned: dict[str, str] = {}
        for mood, target in self.expressions_map.items():
            t = (target or "").strip()
            if not t:
                cleaned[mood] = ""
                continue
            exp, _path = self._resolve_semantic_expression(t)
            if exp is not None and exp.kind == KIND_ITEM:
                logger.warning(
                    "Mood '%s' maps to '%s' which is an ITEM toggle, not a "
                    "facial expression — ignoring this mapping (items are "
                    "toggled with [item_on:...]/[item_off:...] instead).",
                    mood, t)
                cleaned[mood] = ""
                continue
            cleaned[mood] = t
        self.expressions_map = cleaned

    def _log_startup_diagnostic(self) -> None:
        """Log the startup diagnostic block (files, counts, expression map)."""
        if self._discovered is None:
            return
        # Refresh valid param ids from the live runtime now that it's loaded
        try:
            runtime_ids = set(self._model.GetParamIds())
            if runtime_ids:
                self._valid_param_ids = runtime_ids
        except Exception as e:
            logger.debug(f"Could not query runtime param ids (using CDI): {e}")
        logger.info("\n%s", format_diagnostic(self._discovered))
        # Mood -> expression map actually usable on THIS model (after the
        # config override merge). Logged so you can verify at startup which
        # face each detected emotion will trigger.
        mood_map = build_mood_expression_map(self, self.expressions_map)
        lines = "\n".join(f"    {emo:<12} -> {exp}" for emo, exp in sorted(mood_map.items()))
        logger.info("Mood -> expression mapping (active model):\n%s", lines)

    def list_expressions(self) -> list[dict]:
        """All discovered expressions with metadata (for UI/LLM prompts)."""
        return [e.to_dict() for e in self._expression_catalog.values()]

    def available_expression_ids(self) -> list[str]:
        """Semantic expression ids the AI layer may trigger."""
        return sorted(self._expression_catalog.keys())

    def list_parameters(self, category: Optional[str] = None) -> list[str]:
        """Parameter ids known to exist on this model.

        Args:
            category: optional filter — "tracking" | "expression" | "internal".
                      Pass None to get everything (the Live2D runtime still
                      operates on the complete model either way).
        """
        if category is None:
            return sorted(self._valid_param_ids)
        return sorted(p for p in self._valid_param_ids
                      if classify_parameter(p) == category)

    def _resolve_semantic_expression(self, name: str) -> tuple[Optional[ExpressionInfo], str]:
        """Resolve any accepted expression reference to (ExpressionInfo, path).

        Accepts, in order of precedence:
        1. semantic id ("angry")          -> ku.exp3.json via catalog
        2. emotion name ("angry")         -> config expressions map
        3. display name ("生气")           -> catalog lookup by name
        4. file stem ("ku") or filename ("ku.exp3.json") -> direct file

        Legacy ``*_toggle`` item ids (glasses_toggle / bow_toggle / ...) and
        other ITEM_ID_ALIASES spellings are normalized to their canonical
        semantic ids before lookup, so old configs and saved state still
        resolve instead of logging "Unknown expression".
        """
        key = (name or "").strip()
        if not key:
            return None, ""
        # Canonicalize legacy aliases case-insensitively (Glasses_Toggle etc.)
        lowered = key.lower().replace(" ", "_").replace("-", "_")
        canonical = ITEM_ID_ALIASES.get(lowered)
        if canonical:
            key = canonical

        exp = self._expression_catalog.get(key)
        if exp:
            return exp, exp.path

        # Emotion -> semantic id (configurable via avatar.expressions)
        mapped = self.expressions_map.get(key)
        if mapped and mapped != key:
            exp = self._expression_catalog.get(mapped)
            if exp:
                return exp, exp.path
            key_file = mapped

        # Display-name lookup (Chinese names)
        for e in self._expression_catalog.values():
            if e.name == key:
                return e, e.path

        # Direct file stem / filename lookup
        fname = key if key.endswith(".exp3.json") else f"{key}.exp3.json"
        if self._model_path:
            model_dir = self._model_path.parent
            for search_dir in (model_dir, model_dir / "expressions", model_dir / "Exp"):
                candidate = search_dir / fname
                if candidate.exists():
                    return None, str(candidate)

        logger.warning("Unknown expression '%s' (no semantic id, emotion, "
                       "display name, or file match)", name)
        return None, ""

    def trigger_expression(self, expression_id: str) -> bool:
        """Trigger an expression by SEMANTIC id (e.g. "angry", "heart_eyes").

        This is the deterministic API for the AI/LLM behaviour layer:
        semantic ids are translated to concrete .exp3.json files here —
        the LLM never needs to know filenames.

        Returns True if the expression was applied.
        """
        if not self._initialized or not self._model:
            logger.debug("trigger_expression('%s') ignored: model not initialized",
                         expression_id)
            return False

        exp, path = self._resolve_semantic_expression(expression_id)
        if not path:
            return False
        # Guard the two-layer contract: an ITEM must never be triggered as a
        # facial expression (use enable_item()/disable_item() for items).
        if exp is not None and exp.kind == KIND_ITEM:
            logger.warning(
                "trigger_expression('%s'): '%s' is an ITEM — use "
                "enable_item()/disable_item() instead.", expression_id, exp.id)
            return False
        return self._load_expression_file(path, label=(exp.id if exp else expression_id))

    def _load_expression_file(self, path: str, label: str = "") -> bool:
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
                         for e in self._expression_catalog.values()}
        kind = catalog_kinds.get(stem)
        if kind is None and label:
            sem = DEFAULT_SEMANTIC_NAMES.get(label.lower())
            kind = sem[3] if sem else None
        item_layer = kind == KIND_ITEM
        try:
            # --- Native path (only when the installed build supports it) ---
            if hasattr(self._model, "LoadExpression") and \
                    hasattr(self._model, "SetExpression"):
                if not item_layer:
                    # Facial switch: cleanly deactivate the previous FACE
                    # only — loaded item files stay active (stacking).
                    prev = self._active_expression_name
                    if prev and prev != name:
                        try:
                            self._model.DeleteExpression(prev)
                        except Exception:
                            pass
                self._model.LoadExpression(path)
                self._model.SetExpression(name, 1.0)
                with self._lock:
                    if not item_layer:
                        self._active_expression_name = name
                    self._current_expression = label or self._current_expression
                logger.info("Expression applied (native): %s (%s)",
                            label or stem, name)
                return True

            # --- Emulated path: apply exp3 parameters directly ---
            # 1) Prefer parameters already parsed during discovery (no re-read).
            #    Match case-insensitively on the stem so an on-disk file named
            #    "FZ.exp3.json" still resolves via its catalog entry.
            params: dict[str, float] = {}
            for exp in self._expression_catalog.values():
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
                          for e in self._expression_catalog.values()
                          if e.kind != KIND_ITEM}
            item_stems = {exp3_stem(e.file)
                          for e in self._expression_catalog.values()
                          if e.kind == KIND_ITEM}
            for old_stem, old_ids in list(self._expression_owned.items()):
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
                            self._model.ResetParameterValue(pid)
                        except Exception:
                            try:
                                # Older builds: reset by setting default-ish 0.
                                self._model.SetParameterValue(pid, 0.0)
                            except Exception:
                                pass
                self._expression_owned.pop(old_stem, None)

            # 4) Apply the expression's parameter values.
            applied = 0
            skipped = 0
            for pid, val in params.items():
                try:
                    self._model.SetParameterValue(pid, float(val))
                    applied += 1
                except Exception:
                    skipped += 1
            if applied == 0 and skipped > 0:
                logger.warning("Expression '%s': all %d parameter(s) failed to "
                               "apply from %s", label or stem, skipped, path)
                return False

            self._expression_params = dict(params)
            self._expression_owned[stem] = set(params.keys())
            with self._lock:
                self._active_expression_name = name
                self._current_expression = label or self._current_expression
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

    def reset_expressions(self) -> bool:
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
        if not self._initialized or not self._model:
            return False
        try:
            # Which exp3 stems belong to discovered facial expressions vs
            # items (case-insensitive stems; see exp3_stem).
            face_stems = {exp3_stem(e.file)
                          for e in self._expression_catalog.values()
                          if e.kind != KIND_ITEM}
            item_stems = {exp3_stem(e.file)
                          for e in self._expression_catalog.values()
                          if e.kind == KIND_ITEM}
            # Stems currently owned by enabled items must be preserved.
            active_item_stems = set(self._active_items.values())

            # 1) Release parameters owned by emulated FACIAL expressions
            #    (reset to model defaults — works on every live2d-py build).
            kept_params: dict[str, float] = {}
            for stem, ids in list(self._expression_owned.items()):
                is_item_layer = (stem in item_stems
                                 or stem in active_item_stems
                                 or (stem not in face_stems and item_stems
                                     and stem not in face_stems))
                if is_item_layer:
                    # Keep item layers (owned params + values) intact.
                    for pid in ids:
                        if pid in self._expression_params:
                            kept_params[pid] = self._expression_params[pid]
                    continue
                for pid in ids:
                    try:
                        self._model.ResetParameterValue(pid)
                    except Exception:
                        try:
                            self._model.SetParameterValue(pid, 0.0)
                        except Exception:
                            pass
                self._expression_owned.pop(stem, None)
            self._expression_params = kept_params

            # 2) Legacy native-expression cleanup: delete only the active
            #    FACIAL expression file (harmless on builds without
            #    DeleteExpression, e.g. live2d-py 0.7.0.4). Items loaded via
            #    the native path stay active.
            names = {self._active_expression_name}
            for n in names:
                if not n:
                    continue
                try:
                    self._model.DeleteExpression(n)
                except Exception:
                    pass
            with self._lock:
                self._active_expression_name = ""
                self._current_expression = "neutral"
            logger.debug("Facial expressions reset (归零 equivalent); items kept")
            return True
        except Exception as e:
            logger.error(f"reset_expressions failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Item layer (accessories/props) — independent of the facial layer.
    # Multiple items may be active simultaneously; enabling/removing an
    # item NEVER touches the active facial expression.
    # ------------------------------------------------------------------

    def _item_default_params(self, exp: ExpressionInfo) -> dict[str, float]:
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

    def enable_item(self, item_id: str) -> bool:
        """Activate one discovered kind="item" .exp3.json (stackable).

        Accepts canonical semantic ids ("glasses", "hat", ...) as well as
        legacy aliases via _resolve_semantic_expression. Unknown ids or
        non-item ids are rejected (returns False, never raises). Enabling
        an item does NOT change the active facial expression.
        """
        if not self._initialized or not self._model:
            logger.debug("enable_item('%s') ignored: model not initialized",
                         item_id)
            return False
        exp, path = self._resolve_semantic_expression(item_id)
        if exp is None or exp.kind != KIND_ITEM or not path:
            logger.warning("enable_item('%s'): not a known item on this model",
                           item_id)
            return False
        stem = exp3_stem(exp.file)
        if stem in self._active_items.values():
            return True  # idempotent: already wearing this file
        if self._load_expression_file(path, label=exp.id):
            self._active_items[exp.id] = stem
            return True
        return False

    def disable_item(self, item_id: str) -> bool:
        """Deactivate one item without touching the facial expression.

        Releases only the parameters owned by that item's exp3 file whose
        current values were set by the item itself (values re-set by the
        active face are preserved). Returns False for unknown/non-item ids.
        """
        if not self._initialized or not self._model:
            logger.debug("disable_item('%s') ignored: model not initialized",
                         item_id)
            return False
        exp, _path = self._resolve_semantic_expression(item_id)
        if exp is None or exp.kind != KIND_ITEM:
            logger.warning("disable_item('%s'): not a known item on this model",
                           item_id)
            return False
        stem = self._active_items.pop(exp.id, None) or exp3_stem(exp.file)
        owned = self._expression_owned.pop(stem, set())
        # Also release any params from the parsed exp3 file not tracked yet.
        owned |= set(exp.parameters.keys())
        face_active = self._active_expression_name
        for pid in sorted(owned):
            # Don't clobber a value currently owned by the active FACE.
            for f_stem, f_ids in self._expression_owned.items():
                if f_stem != stem and pid in f_ids:
                    break
            else:
                try:
                    self._model.ResetParameterValue(pid)
                except Exception:
                    try:
                        default = self._item_default_params(exp).get(pid, 0.0)
                        self._model.SetParameterValue(pid, default)
                    except Exception:
                        pass
            self._expression_params.pop(pid, None)
        if face_active:
            logger.debug("Item '%s' disabled (face %s untouched)",
                         exp.id, face_active)
        return True

    def get_active_items(self) -> list[str]:
        """Semantic ids of the currently enabled items."""
        return sorted(self._active_items.keys())

    def set_parameter(self, param_id: str, value: float) -> bool:
        """Set one Live2D parameter by ID with validation.

        Clean API for the behaviour layer; the full 279-parameter model is
        still driven normally by the runtime — this just exposes controlled
        access. Invalid IDs/values are rejected (logged), never crash.
        """
        if not self._initialized or not self._model:
            return False
        if not isinstance(param_id, str) or not param_id:
            logger.warning("set_parameter: invalid parameter id %r", param_id)
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            logger.warning("set_parameter('%s', %r): value is not numeric",
                           param_id, value)
            return False
        if math.isnan(v) or math.isinf(v):
            logger.warning("set_parameter('%s', %r): non-finite value rejected",
                           param_id, value)
            return False
        if self._valid_param_ids and param_id not in self._valid_param_ids:
            logger.warning("set_parameter: unknown parameter id '%s' "
                           "(not present on this model)", param_id)
            return False
        try:
            self._model.SetParameterValue(param_id, max(-100.0, min(100.0, v)))
            return True
        except Exception as e:
            logger.error("set_parameter('%s', %s) failed: %s", param_id, v, e)
            return False

    def resize(self, width: int, height: int) -> None:
        """Resize the model viewport."""
        if self._model:
            try:
                self._model.Resize(width, height)
            except Exception as e:
                logger.error(f"Live2D resize failed: {e}")

    def update(self, delta_time: float) -> None:
        """Update model state."""
        if not self._initialized or not self._model:
            return
        try:
            self._model.Update()            # recalc breathing/motion/physics first
            self._update_blink(delta_time)  # then apply our overrides
            self._update_lip_sync(delta_time)
        except Exception as e:
            logger.error(f"Live2D update error: {e}")

    def draw(self) -> None:
        """Draw the Live2D model with zoom and position transforms."""
        if not self._initialized or not self._model:
            return
        try:
            # FIX: Clear buffer before drawing to ensure correct background color compositing
            # Without this, LAppModel.Draw() renders against its own default white buffer
            self._live2d.clearBuffer()
            # Use live2d-py's native transform methods instead of OpenGL matrices
            # LAppModel.SetOffset(x, y) expects screen-space pixel coordinates
            # LAppModel.SetScale(scale) expects a multiplier (1.0 = normal size)
            self._model.SetOffset(self._offset_x, self._offset_y)
            self._model.SetScale(self._zoom)
            self._model.Draw()
        except Exception as e:
            logger.error(f"Live2D draw error: {e}")
            try:
                self._model.Draw()
            except Exception as e:
                logger.debug(f"Live2D fallback draw failed: {e}")

    def set_expression(self, emotion: str) -> None:
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
        if not self._initialized or not self._model:
            return

        if not (emotion or "").strip():
            # "none" / plain default face: release any active expression
            # parameters (items untouched) and stop here.
            self.reset_expressions()
            return

        # FIX: Protect shared state with lock
        with self._lock:
            self._current_expression = emotion

        # 1) Emotion -> semantic id via the (config-overridable) expression
        #    map FIRST, so e.g. mood "happy" triggers star_eyes even if the
        #    model happens to ship a file literally named happy.exp3.json.
        mapped = self.expressions_map.get(emotion)
        if mapped and mapped != emotion:
            exp, path = self._resolve_semantic_expression(mapped)
            if path and self._load_expression_file(
                    path, label=(exp.id if exp else mapped)):
                return

        # 2) Semantic catalog / display name / file stem direct match
        exp, path = self._resolve_semantic_expression(emotion)
        if path and self._load_expression_file(path, label=(exp.id if exp else emotion)):
            return

        # 3) Legacy: try the raw mapped/legacy filename too
        #    (e.g. expressions: {happy: "happy"} -> happy.exp3.json)
        if self._model_path:
            candidates = [emotion]
            mapped = self.expressions_map.get(emotion)
            if mapped and mapped != emotion:
                candidates.append(mapped)
            model_dir = self._model_path.parent
            for name in candidates:
                for search_dir in [model_dir, model_dir / "expressions", model_dir / "Exp"]:
                    exp_file = search_dir / f"{name}.exp3.json"
                    if exp_file.exists():
                        if self._load_expression_file(str(exp_file), label=name):
                            return

        # 4) Fallback: set parameters directly
        logger.debug("No expression file for '%s'; using parameter fallback", emotion)
        self._set_expression_params(emotion)

    def _set_expression_params(self, emotion: str) -> None:
        """Set expression via model parameters."""
        if not self._model:
            return
        # Map standard-name dict keys to this model's resolved actual IDs
        # (only eye/mouth are auto-resolved; other params pass through as-is)
        id_overrides = {
            "ParamEyeLOpen": self._param_eye_l_open,
            "ParamEyeROpen": self._param_eye_r_open,
            "ParamMouthOpenY": self._param_mouth_open,
        }
        # Try the raw mood name first, then the semantic id it maps to.
        params = EMOTION_PARAMS.get(emotion)
        if params is None:
            mapped = self.expressions_map.get(emotion, "")
            params = EMOTION_PARAMS.get(mapped) or EMOTION_PARAMS["neutral"]
        for param_id, value in params.items():
            resolved_id = id_overrides.get(param_id, param_id)
            try:
                self._model.SetParameterValue(resolved_id, value)
            except Exception as e:
                logger.error(f"Live2D param error (expression '{resolved_id}'): {e}")

    def set_talking(self, talking: bool) -> None:
        """Set talking state for lip sync."""
        # FIX: Protect shared state with lock
        with self._lock:
            self._is_talking = talking
            if not talking and self._model:
                self._mouth_value = 0.0
        
        # Apply to model outside lock (GL calls must stay on main thread anyway)
        if not talking and self._model:
            try:
                self._model.SetParameterValue(self._param_mouth_open, 0.0)
            except Exception as e:
                logger.debug(f"Failed to reset mouth parameter: {e}")

    def _update_blink(self, delta_time: float) -> None:
        """Update blink animation."""
        if not self._model:
            return

        # FIX: Protect shared state with lock (read on main thread, write from pipeline)
        with self._lock:
            self._blink_timer += delta_time

            if self._is_blinking:
                if self._blink_timer >= self._blink_duration:
                    self._is_blinking = False
                    self._blink_timer = 0.0
                    eyes_open = True
                else:
                    # Still mid-blink — keep eyes closed
                    eyes_open = False
            elif self._blink_timer >= self._blink_interval:
                self._is_blinking = True
                self._blink_timer = 0.0
                eyes_open = False
            else:
                eyes_open = True
        
        # Apply GL calls outside lock
        eye_value = 0.0 if not eyes_open else 1.0
        try:
            self._model.SetParameterValue(self._param_eye_l_open, eye_value)
            self._model.SetParameterValue(self._param_eye_r_open, eye_value)
        except Exception as e:
            logger.debug(f"Failed to set eye parameters during blink: {e}")

    def _update_lip_sync(self, delta_time: float) -> None:
        """Update lip sync animation driven by actual TTS audio amplitude."""
        if not self._model:
            return

        # FIX: Protect shared state with lock
        with self._lock:
            should_compute = self._is_talking and self._lipsync_audio is not None
            if should_compute:
                elapsed = time.time() - self._lipsync_start
                offset = int(elapsed * self._lipsync_rate)
                offset = min(offset, len(self._lipsync_audio))
                chunk = self._lipsync_audio[self._lipsync_last_offset:offset]
                self._lipsync_last_offset = offset
                compute_mouth = len(chunk) > 0
            else:
                compute_mouth = False
        
        # Compute mouth value and apply GL calls outside lock
        if should_compute and compute_mouth:
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            mouth = max(0.0, min(1.0, rms * 4.0))
            with self._lock:
                self._mouth_value = mouth
            try:
                self._model.SetParameterValue(self._param_mouth_open, mouth)
            except Exception as e:
                logger.debug(f"Failed to set mouth parameter for lip sync: {e}")
        elif self._mouth_value > 0.01:
            # Decay mouth value when not talking or when talking but no new audio chunk
            with self._lock:
                self._mouth_value *= 0.8
            try:
                self._model.SetParameterValue(self._param_mouth_open, self._mouth_value)
            except Exception as e:
                logger.debug(f"Failed to decay mouth parameter: {e}")

    def start_lip_sync(self, audio_data: np.ndarray, sample_rate: int) -> None:
        """Begin real lip sync driven by actual TTS audio amplitude."""
        # FIX: Protect shared state with lock
        with self._lock:
            self._lipsync_audio = audio_data
            self._lipsync_rate = sample_rate
            self._lipsync_start = time.time()
            self._lipsync_last_offset = 0
            self._is_talking = True

    def drag(self, x: int, y: int, width: int = 0, height: int = 0) -> None:
        """Handle mouse movement for eye tracking - makes avatar look at cursor.
        
        Args:
            x: Mouse X position in screen coordinates
            y: Mouse Y position in screen coordinates  
            width: OpenGL widget width (for normalization)
            height: OpenGL widget height (for normalization)
        """
        if not self._initialized or not self._model:
            return
        
        try:
            # Normalize mouse position to Live2D coordinate space (-1 to 1)
            # Live2D uses a coordinate system where (0, 0) is center
            if width > 0 and height > 0:
                # Convert screen coordinates to normalized device coordinates
                norm_x = (x / width) * 2.0 - 1.0  # Range: -1 to 1
                norm_y = ((height - y) / height) * 2.0 - 1.0  # Flip Y, range: -1 to 1
            else:
                # Fallback: assume 800x600 default
                norm_x = (x / 800.0) * 2.0 - 1.0
                norm_y = ((600 - y) / 600.0) * 2.0 - 1.0
            
            # Clamp values to reasonable range
            norm_x = max(-1.0, min(1.0, norm_x))
            norm_y = max(-1.0, min(1.0, norm_y))
            
            # Set eye ball position (direct eye movement)
            # Values typically range from -1 to 1
            self._model.SetParameterValue(self._param_eye_ball_x, norm_x * 0.8)
            self._model.SetParameterValue(self._param_eye_ball_y, norm_y * 0.8)
            
            # Set head angle for more natural looking
            # Angle values typically range from -30 to 30 degrees
            self._model.SetParameterValue(self._param_angle_x, norm_x * 20.0)
            self._model.SetParameterValue(self._param_angle_y, norm_y * 15.0)
            
        except Exception as e:
            logger.debug(f"Eye tracking error: {e}")

    def zoom_in(self, amount: float = 0.1) -> None:
        """Zoom in the model."""
        self._zoom = min(self._max_zoom, self._zoom + amount)
        logger.debug(f"Zoom: {self._zoom:.2f}")

    def zoom_out(self, amount: float = 0.1) -> None:
        """Zoom out the model."""
        self._zoom = max(self._min_zoom, self._zoom - amount)
        logger.debug(f"Zoom: {self._zoom:.2f}")

    def reset_zoom(self) -> None:
        """Reset zoom to default scale."""
        self._zoom = self.scale
        self._offset_x = 0.0
        self._offset_y = 0.0
        logger.debug("Zoom reset")

    def move_up(self, amount: float = 10.0) -> None:
        """Move model up."""
        self._offset_y -= amount
        self._clamp_offset()
        logger.debug(f"Offset Y: {self._offset_y:.1f}")

    def move_down(self, amount: float = 10.0) -> None:
        """Move model down."""
        self._offset_y += amount
        self._clamp_offset()
        logger.debug(f"Offset Y: {self._offset_y:.1f}")

    def move_left(self, amount: float = 10.0) -> None:
        """Move model left."""
        self._offset_x -= amount
        self._clamp_offset()
        logger.debug(f"Offset X: {self._offset_x:.1f}")

    def move_right(self, amount: float = 10.0) -> None:
        """Move model right."""
        self._offset_x += amount
        self._clamp_offset()
        logger.debug(f"Offset X: {self._offset_x:.1f}")

    def move_by(self, dx: float, dy: float) -> None:
        """Move model by delta x and y (for mouse dragging).
        
        SetOffset expects screen-space pixel coordinates.
        We apply a sensitivity factor to make dragging feel natural.
        
        Bounds are applied to prevent the avatar from being dragged
        completely off-screen.
        """
        # Sensitivity factor: 0.01 = very slow/precise movement, 1.0 = 1:1 movement
        sensitivity = 0.01
        self._offset_x += dx * sensitivity
        self._offset_y += dy * sensitivity
        
        # Apply bounds to keep avatar reachable
        # Live2D models are typically centered at (0, 0) with visible area ~800x600
        # Allow reasonable movement while preventing permanent loss off-screen
        max_offset = 500.0  # pixels in any direction
        self._offset_x = max(-max_offset, min(max_offset, self._offset_x))
        self._offset_y = max(-max_offset, min(max_offset, self._offset_y))
        
        logger.debug(f"Offset X: {self._offset_x:.1f}, Y: {self._offset_y:.1f}")

    def _clamp_offset(self) -> None:
        """Clamp offset values to safe bounds."""
        max_offset = 500.0  # pixels in any direction
        self._offset_x = max(-max_offset, min(max_offset, self._offset_x))
        self._offset_y = max(-max_offset, min(max_offset, self._offset_y))

    @property
    def zoom(self) -> float:
        """Get current zoom level."""
        return self._zoom

    @property
    def offset_x(self) -> float:
        """Get current X offset."""
        return self._offset_x

    @property
    def offset_y(self) -> float:
        """Get current Y offset."""
        return self._offset_y

    def dispose(self) -> None:
        """Clean up Live2D resources."""
        if self._live2d:
            try:
                self._live2d.dispose()
            except Exception as e:
                logger.debug(f"Failed to dispose Live2D model: {e}")
        self._model = None
        self._initialized = False
        self._gl_initialized = False
    
    def update_config(self, config: dict) -> None:
        """Update configuration and reset zoom/scale settings.
        
        This allows changing avatar settings (like scale) without full reinitialization.
        Call this after saving settings to apply changes immediately.
        """
        self._config = config
        # Update scale from new config
        new_scale = config.get("scale", 2.0)
        if new_scale != self.scale:
            self.scale = new_scale
            # Reset zoom to new default scale
            self._zoom = new_scale
            logger.info(f"Avatar scale updated to {new_scale}")

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_talking(self) -> bool:
        return self._is_talking

    @property
    def error_message(self) -> Optional[str]:
        return self._error_message

# ---------------------------------------------------------------------------
# Mood -> expression triggering (semantic, deterministic; no LLM filenames)
# ---------------------------------------------------------------------------

EMOTION_EXPRESSION_MAP: dict[str, str] = {k: v for k, v in DEFAULT_EXPRESSIONS.items()}


def build_mood_expression_map(avatar: "Live2DAvatar",
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
        exp, path = avatar._resolve_semantic_expression(target)
        if path:
            result[emotion] = (exp.id if exp else target)
        else:
            logger.debug("Mood '%s' -> expression '%s' not available on this "
                         "model; will use parameter fallback", emotion, target)
    return result
