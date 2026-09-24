"""AI VTuber - Live2D avatar runtime coordinator.

Owns the :class:`Live2DAvatar` object itself: native runtime lifecycle
(safe import / GL init / model load), pure-file discovery wiring, thread
locks, blink & lip-sync animation state, zoom/pan input state, and the
public façade consumed by the rest of the app.

The cohesive subsystems that previously lived inline are now separate
modules; this file delegates to them:

* ``live2d_runtime``   - package finding, ABI checks, path resolution,
                         ``.model3.json`` validation helpers.
* ``live2d_render``    - OpenGL per-frame update/draw/resize/drag.
* ``expression_manager`` - semantic expression resolution & triggering.
* ``expression_apply``   - applying one .exp3.json to the runtime model.
* ``item_manager``       - stackable item/accessory layer + ownership.
* ``mode_manager``       - config-driven modes above the item layer.

CRITICAL: Checks Python/native compatibility BEFORE importing live2d-py
to prevent SIGSEGV (see live2d_runtime).
"""

import logging
import math
import re
import threading
import time
from pathlib import Path
from typing import Optional, Any

import numpy as np

from .model_discovery import (
    DEFAULT_SEMANTIC_NAMES,
    KIND_ITEM,
    DiscoveredModel,
    ExpressionInfo,
    classify_parameter,
    discover_model,
    exp3_stem,
    format_diagnostic,
)
from .live2d_runtime import (
    _find_live2d_package_path,
    _check_native_compatibility,
    _resolve_model_path,
    _resolve_active_model,
    validate_model_files,
)
from . import live2d_render
from . import expression_manager
from . import expression_apply
from . import item_manager
from . import mode_manager

# ---------------------------------------------------------------------------
# Re-exported shared constants / helpers (canonical homes in the split
# modules) so callers of the former monolith keep working unchanged.
# ---------------------------------------------------------------------------
from .expression_manager import (  # noqa: F401
    FACIAL_EXPRESSION_IDS,
    DEFAULT_EXPRESSIONS,
    EMOTION_PARAMS,
    EMOTION_EXPRESSION_MAP,
    build_mood_expression_map,
)
from .model_discovery import (  # noqa: F401
    EXPRESSION_FILES,
    FACIAL_EXPRESSIONS,
    ITEMS,
    canonicalize_semantic_id,
)
from .item_manager import ITEM_IDS  # noqa: F401
from .live2d_runtime import (  # noqa: F401
    _fix_mojibake,
    _repair_path_on_fs,
)

logger = logging.getLogger(__name__)

# The AIRI sheet documentation block (expressions vs items, canonical
# semantic ids) lives with the expression/item managers:
# see ai_vtuber/avatar/expression_manager.py and item_manager.py.


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
        # --- avatar MODES layer (config-driven, sits ABOVE the item layer) ---
        # config "modes": mode name -> {"items": [...], "exclusive": bool}
        self._mode_defs: dict[str, dict] = config.get("modes", {}) or {}
        # Active modes: mode name -> list of item ids that mode activated
        self._active_modes: dict[str, list] = {}
        # Items the user/LLM requested directly (not via a mode). A mode
        # going OFF never removes a manually-requested item it also owns.
        self._manual_items: set[str] = set()
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
        """Validate that all required model files exist.

        Pure-file check lives in :mod:`ai_vtuber.avatar.live2d_runtime`;
        this wrapper just wires the error-message callback into avatar state.
        """
        return validate_model_files(
            self._model_path,
            set_error=lambda m: setattr(self, "_error_message", m))

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

    # ------------------------------------------------------------------
    # Delegation to the split-out subsystem modules (thin wrappers keep
    # the public method surface identical to the old monolith).
    # ------------------------------------------------------------------

    def _sanitize_expressions_map(self) -> None:
        expression_manager.sanitize_expressions_map(self)

    def _resolve_semantic_expression(self, name: str) -> tuple[Optional[ExpressionInfo], str]:
        return expression_manager.resolve_semantic_expression(self, name)

    def trigger_expression(self, expression_id: str) -> bool:
        return expression_manager.trigger_expression(self, expression_id)

    # Backwards-compatible alias used by older pipelines/tests:
    # set_emotion("") / set_emotion("neutral") reset the FACE only (items
    # stay on); any other value behaves like trigger_expression().
    def set_emotion(self, emotion: str) -> bool:
        return expression_manager.set_emotion(self, emotion)

    def apply_action_tag(self, tag: str) -> bool:
        return expression_manager.apply_action_tag(self, tag)

    def _load_expression_file(self, path: str, label: str = "") -> bool:
        return expression_apply.load_expression_file(self, path, label=label)

    def reset_expressions(self) -> bool:
        return expression_apply.reset_expressions(self)

    def _item_default_params(self, exp: ExpressionInfo) -> dict[str, float]:
        return item_manager.item_default_params(self, exp)

    def enable_item(self, item_id: str, via_mode: bool = False) -> bool:
        return item_manager.enable_item(self, item_id, via_mode=via_mode)

    def disable_item(self, item_id: str) -> bool:
        return item_manager.disable_item(self, item_id)

    def get_active_items(self) -> list[str]:
        return item_manager.get_active_items(self)

    def available_modes(self) -> list[str]:
        return mode_manager.available_modes(self)

    def _mode_items(self, mode: str) -> list[str]:
        return mode_manager.mode_items(self, mode)

    def enable_mode(self, mode_name: str) -> bool:
        return mode_manager.enable_mode(self, mode_name)

    def disable_mode(self, mode_name: str) -> bool:
        return mode_manager.disable_mode(self, mode_name)

    def toggle_mode(self, mode_name: str) -> bool:
        return mode_manager.toggle_mode(self, mode_name)

    def get_active_modes(self) -> list[str]:
        return mode_manager.get_active_modes(self)

    def resize(self, width: int, height: int) -> None:
        live2d_render.resize_model(self, width, height)

    def update(self, delta_time: float) -> None:
        live2d_render.update_model(self, delta_time)

    def draw(self) -> None:
        live2d_render.draw_model(self)

    def drag(self, x: int, y: int, width: int = 0, height: int = 0) -> None:
        live2d_render.drag_tracking(self, x, y, width, height)

    def set_expression(self, emotion: str) -> None:
        expression_manager.set_expression(self, emotion)

    def _set_expression_params(self, emotion: str) -> None:
        expression_manager.set_expression_params(self, emotion)

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
