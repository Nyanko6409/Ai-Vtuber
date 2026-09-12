"""AI VTuber - Live2D Avatar Module using live2d-py

Handles model loading, rendering, expressions, blinking, and lip sync.
Uses pathlib for robust path handling (including WSL /mnt/ paths).
"""

import logging
import math
import time
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Emotion → expression file name mapping (configurable)
DEFAULT_EXPRESSIONS: dict[str, str] = {
    "neutral": "neutral",
    "happy": "happy",
    "excited": "happy",
    "thinking": "neutral",
    "surprised": "surprised",
    "sad": "sad",
    "angry": "angry",
    "sleepy": "sleepy",
}

# Emotion → parameter overrides (fallback when no .exp3.json files exist)
EMOTION_PARAMS: dict[str, dict[str, float]] = {
    "neutral": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0, "ParamMouthOpenY": 0.0},
    "happy": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 0.8, "ParamMouthOpenY": 0.3, "ParamBrowLY": 0.8},
    "excited": {"ParamEyeLOpen": 1.2, "ParamEyeROpen": 1.2, "ParamMouthOpenY": 0.5, "ParamBrowLY": 1.0},
    "thinking": {"ParamEyeLOpen": 0.7, "ParamEyeROpen": 1.0, "ParamBrowLY": -0.5},
    "surprised": {"ParamEyeLOpen": 1.3, "ParamEyeROpen": 1.3, "ParamMouthOpenY": 0.7, "ParamBrowLY": 1.0},
    "sad": {"ParamEyeLOpen": 0.6, "ParamEyeROpen": 0.6, "ParamBrowLY": -0.8, "ParamMouthOpenY": 0.0},
    "angry": {"ParamEyeLOpen": 0.8, "ParamEyeROpen": 0.8, "ParamBrowLY": -1.0, "ParamMouthOpenY": 0.1},
    "sleepy": {"ParamEyeLOpen": 0.3, "ParamEyeROpen": 0.3, "ParamBrowLY": -0.5},
}


def _resolve_model_path(raw_path: str) -> Optional[Path]:
    """Resolve and validate a Live2D model path.

    Handles:
    - Empty / missing paths
    - WSL /mnt/... paths
    - Paths with spaces
    - Both .model3.json (Cubism 3+) and .model.json (Cubism 2)

    Returns the resolved Path or None if invalid.
    """
    if not raw_path or not raw_path.strip():
        return None

    p = Path(raw_path).expanduser().resolve()

    if not p.exists():
        logger.error(f"Live2D model path does not exist: {p}")
        return None

    if not p.is_file():
        logger.error(f"Live2D model path is not a file: {p}")
        return None

    suffix = p.suffix.lower()
    if suffix not in (".json",):
        logger.error(f"Live2D model must be a .json file, got: {suffix} ({p})")
        return None

    # Verify referenced assets exist
    model_dir = p.parent
    missing = []

    # Check for textures directory
    textures_dir = model_dir / (p.stem + "." + "png")  # common pattern
    # The .model3.json references files relatively; we just check the dir exists
    if not model_dir.is_dir():
        missing.append(str(model_dir))

    if missing:
        logger.warning(f"Live2D model references missing assets: {missing}")

    return p


class Live2DAvatar:
    """Live2D avatar using live2d-py library.

    Lifecycle:
        1. __init__()  – import live2d module, parse config (NO model loading yet)
        2. init_gl()   – call AFTER OpenGL context exists; loads model here
        3. resize()    – set viewport
        4. update() / draw() – per-frame
        5. dispose()   – cleanup

    Public interface:
        avatar.set_expression("happy")
        avatar.set_talking(True)
        avatar.set_talking(False)
    """

    def __init__(self, config: dict) -> None:
        self.model_path_raw: str = config.get("model_path", "")
        self.scale: float = config.get("scale", 2.0)
        self.expressions_map: dict[str, str] = {
            **DEFAULT_EXPRESSIONS,
            **config.get("expressions", {}),
        }

        # Module references (set in _import_live2d)
        self._live2d: Any = None
        self._live2d_version: int = 0  # 2 or 3
        self._model: Any = None

        # Runtime state
        self._is_talking: bool = False
        self._current_expression: str = "neutral"
        self._mouth_value: float = 0.0
        self._blink_timer: float = 0.0
        self._blink_interval: float = 3.0
        self._blink_duration: float = 0.15
        self._is_blinking: bool = False
        self._initialized: bool = False
        self._gl_initialized: bool = False

        # Resolved path (validated later in init_gl)
        self._model_path: Optional[Path] = None

        # Import the live2d module early so we fail fast if not installed
        self._import_live2d()

    # ------------------------------------------------------------------
    # Module import
    # ------------------------------------------------------------------
    def _import_live2d(self) -> None:
        """Import live2d-py. Try v3 first (Cubism 3+), then v2."""
        try:
            import live2d.v3 as live2d
            self._live2d = live2d
            self._live2d_version = 3
            logger.info("live2d-py loaded (Cubism v3)")
        except ImportError:
            try:
                import live2d.v2 as live2d
                self._live2d = live2d
                self._live2d_version = 2
                logger.info("live2d-py loaded (Cubism v2)")
            except ImportError:
                logger.error(
                    "live2d-py is not installed.\n"
                    "  Install from PyPI:  pip install live2d-py\n"
                    "  Or download wheel:  https://github.com/EasyLive2D/live2d-py/releases\n"
                    "  NOTE: On Linux x64 the v3 module may need to be built from source."
                )
                raise

    # ------------------------------------------------------------------
    # OpenGL-dependent initialization (call AFTER pygame window created)
    # ------------------------------------------------------------------
    def init_gl(self) -> bool:
        """Initialize Live2D after the OpenGL context exists.

        This is where the model is actually loaded, because live2d-py
        requires a valid OpenGL context to compile shaders / upload textures.

        Returns True on success, False on failure.
        """
        if self._live2d is None:
            logger.error("Cannot init_gl: live2d module not loaded")
            return False

        if self._gl_initialized:
            return self._initialized

        try:
            # 1. Initialize the live2d system
            self._live2d.init()
            logger.debug("live2d.init() called")

            # 2. Initialize OpenGL resources (shaders, etc.)
            self._live2d.glInit()
            logger.debug("live2d.glInit() called")
            self._gl_initialized = True

        except Exception as e:
            logger.error(f"live2d OpenGL initialization failed: {e}", exc_info=True)
            return False

        # 3. Resolve and validate model path
        self._model_path = _resolve_model_path(self.model_path_raw)
        if self._model_path is None:
            logger.warning(
                "No Live2D model configured. Set 'avatar.model_path' in config.yaml.\n"
                "The window will show the UI overlay only."
            )
            self._initialized = False
            return False

        # 4. Load the model
        try:
            model_path_str = str(self._model_path)
            logger.info(f"Loading Live2D model: {model_path_str}")

            self._model = self._live2d.LAppModel()
            self._model.LoadModelJson(model_path_str)

            self._initialized = True
            logger.info(f"Live2D model loaded successfully: {self._model_path.name}")

            # Log available motions/expressions for debugging
            self._log_model_info()

        except Exception as e:
            logger.error(
                f"Failed to load Live2D model '{self._model_path}': {e}",
                exc_info=True,
            )
            self._initialized = False
            return False

        return True

    def _log_model_info(self) -> None:
        """Log available motions/expressions for debugging."""
        if not self._model:
            return
        try:
            # Try to enumerate motion groups
            if hasattr(self._model, 'GetMotionGroupCount'):
                count = self._model.GetMotionGroupCount()
                logger.debug(f"Model has {count} motion groups")
            if hasattr(self._model, 'GetExpressionCount'):
                count = self._model.GetExpressionCount()
                logger.debug(f"Model has {count} expressions")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Viewport
    # ------------------------------------------------------------------
    def resize(self, width: int, height: int) -> None:
        """Resize the model viewport. Call after init_gl()."""
        if self._model:
            try:
                self._model.Resize(width, height)
            except Exception as e:
                logger.error(f"Live2D resize failed: {e}")

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self, delta_time: float) -> None:
        """Update model state (animations, blinking, lip sync)."""
        if not self._initialized or not self._model:
            return
        try:
            self._update_blink(delta_time)
            self._update_lip_sync(delta_time)
            self._model.Update()
        except Exception as e:
            logger.error(f"Live2D update error: {e}")

    def draw(self) -> None:
        """Draw the Live2D model."""
        if not self._initialized or not self._model:
            return
        try:
            self._model.Draw()
        except Exception as e:
            logger.error(f"Live2D draw error: {e}")

    # ------------------------------------------------------------------
    # Clear buffer helper
    # ------------------------------------------------------------------
    def clear_buffer(self) -> None:
        """Clear the OpenGL color/depth buffer."""
        if self._live2d:
            try:
                self._live2d.clearBuffer()
            except Exception as e:
                logger.error(f"clearBuffer failed: {e}")

    # ------------------------------------------------------------------
    # Expressions
    # ------------------------------------------------------------------
    def set_expression(self, emotion: str) -> None:
        """Set the avatar's expression based on emotion tag.

        Args:
            emotion: One of neutral, happy, excited, thinking,
                     surprised, sad, angry, sleepy.
        """
        if not self._initialized or not self._model:
            return

        self._current_expression = emotion
        expression_name = self.expressions_map.get(emotion, "neutral")

        # Strategy 1: Try loading an .exp3.json file from the model directory
        if self._model_path:
            model_dir = self._model_path.parent

            # Search in common expression directories
            search_dirs = [
                model_dir,
                model_dir / "expressions",
                model_dir / "Exp",
            ]

            for search_dir in search_dirs:
                exp_file = search_dir / f"{expression_name}.exp3.json"
                if exp_file.exists():
                    try:
                        self._model.LoadExpression(str(exp_file))
                        logger.debug(f"Expression loaded: {exp_file}")
                        return
                    except Exception as e:
                        logger.debug(f"Failed to load expression file {exp_file}: {e}")

            # Also try the model's built-in expression system
            try:
                if hasattr(self._model, 'SetExpression'):
                    self._model.SetExpression(expression_name)
                    logger.debug(f"Expression set by name: {expression_name}")
                    return
            except Exception:
                pass

        # Strategy 2: Fallback – set parameters directly
        self._set_expression_params(emotion)

    def _set_expression_params(self, emotion: str) -> None:
        """Set expression via model parameters (fallback)."""
        if not self._model:
            return
        params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["neutral"])
        for param_id, value in params.items():
            try:
                self._model.SetParameterFloat(param_id, value)
            except Exception:
                pass  # Parameter might not exist in this model

    # ------------------------------------------------------------------
    # Talking / Lip sync
    # ------------------------------------------------------------------
    def set_talking(self, talking: bool) -> None:
        """Set talking state for lip sync animation."""
        self._is_talking = talking
        if not talking:
            self._mouth_value = 0.0
            if self._model:
                try:
                    self._model.SetParameterFloat("ParamMouthOpenY", 0.0)
                except Exception:
                    pass

    def _update_blink(self, delta_time: float) -> None:
        """Update blink animation."""
        if not self._model:
            return

        self._blink_timer += delta_time

        if self._is_blinking:
            if self._blink_timer >= self._blink_duration:
                self._is_blinking = False
                self._blink_timer = 0.0
                try:
                    self._model.SetParameterFloat("ParamEyeLOpen", 1.0)
                    self._model.SetParameterFloat("ParamEyeROpen", 1.0)
                except Exception:
                    pass
        elif self._blink_timer >= self._blink_interval:
            self._is_blinking = True
            self._blink_timer = 0.0
            try:
                self._model.SetParameterFloat("ParamEyeLOpen", 0.0)
                self._model.SetParameterFloat("ParamEyeROpen", 0.0)
            except Exception:
                pass

    def _update_lip_sync(self, delta_time: float) -> None:
        """Update lip sync animation while talking."""
        if not self._model:
            return

        if self._is_talking:
            t = time.time()
            mouth = (
                math.sin(t * 12.0) * 0.3
                + math.sin(t * 7.5) * 0.2
                + math.sin(t * 18.0) * 0.1
                + 0.4
            )
            mouth = max(0.0, min(1.0, mouth))
            self._mouth_value = mouth
            try:
                self._model.SetParameterFloat("ParamMouthOpenY", mouth)
            except Exception:
                pass
        else:
            if self._mouth_value > 0.01:
                self._mouth_value *= 0.8
                try:
                    self._model.SetParameterFloat("ParamMouthOpenY", self._mouth_value)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------
    def drag(self, x: int, y: int) -> None:
        """Handle mouse drag for eye tracking."""
        if self._model:
            try:
                self._model.Drag(x, y)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def dispose(self) -> None:
        """Clean up Live2D resources."""
        if self._live2d:
            try:
                self._live2d.dispose()
            except Exception:
                pass
        self._model = None
        self._initialized = False
        self._gl_initialized = False
        logger.info("Live2D avatar disposed")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def is_initialized(self) -> bool:
        """Check if avatar model is loaded and ready to render."""
        return self._initialized

    @property
    def is_talking(self) -> bool:
        return self._is_talking
