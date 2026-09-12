"""AI VTuber - Live2D Avatar Module using live2d-py"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class Live2DAvatar:
    """Live2D avatar using live2d-py library.
    
    Supports:
    - Configurable model path
    - Idle animation
    - Blinking
    - Talking animation (lip sync)
    - Expressions
    """

    def __init__(self, config: dict) -> None:
        self.model_path: str = config.get("model_path", "")
        self.scale: float = config.get("scale", 2.0)
        self.expressions_map: dict[str, str] = config.get("expressions", {})

        self._live2d = None
        self._model = None
        self._is_talking: bool = False
        self._current_expression: str = "neutral"
        self._mouth_value: float = 0.0
        self._blink_timer: float = 0.0
        self._blink_interval: float = 3.0  # seconds between blinks
        self._blink_duration: float = 0.15  # blink duration in seconds
        self._is_blinking: bool = False
        self._initialized: bool = False

        self._load_model()

    def _load_model(self) -> None:
        """Load the Live2D model."""
        try:
            import live2d.v3 as live2d
            self._live2d = live2d
        except ImportError:
            try:
                import live2d.v2 as live2d
                self._live2d = live2d
                logger.info("Using Live2D v2 (Cubism 2.x model)")
            except ImportError:
                logger.error(
                    "live2d-py not installed. Install with: pip install live2d-py\n"
                    "Or download wheel from: https://github.com/EasyLive2D/live2d-py/releases"
                )
                raise

        # Initialize live2d
        live2d.init()

        if self.model_path and os.path.exists(self.model_path):
            try:
                self._model = live2d.LAppModel()
                self._model.LoadModelJson(self.model_path)
                self._initialized = True
                logger.info(f"Live2D model loaded: {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load Live2D model: {e}")
                self._initialized = False
        else:
            logger.warning(
                f"Live2D model path not set or not found: '{self.model_path}'. "
                "Set 'avatar.model_path' in config.yaml to a valid .model3.json file."
            )
            self._initialized = False

    def gl_init(self) -> None:
        """Initialize OpenGL for Live2D rendering. Call after OpenGL context is created."""
        if self._live2d and self._initialized:
            self._live2d.glInit()

    def resize(self, width: int, height: int) -> None:
        """Resize the model viewport."""
        if self._model:
            self._model.Resize(width, height)

    def update(self, delta_time: float) -> None:
        """Update model state (animations, blinking, lip sync).
        
        Args:
            delta_time: Time since last update in seconds.
        """
        if not self._initialized or not self._model:
            return

        # Update blinking
        self._update_blink(delta_time)

        # Update lip sync
        self._update_lip_sync(delta_time)

        # Update model
        self._model.Update()

    def draw(self) -> None:
        """Draw the Live2D model."""
        if not self._initialized or not self._model:
            return
        self._model.Draw()

    def clear_buffer(self) -> None:
        """Clear the rendering buffer."""
        if self._live2d:
            self._live2d.clearBuffer()

    def set_expression(self, emotion: str) -> None:
        """Set the avatar's expression based on emotion.
        
        Args:
            emotion: One of neutral, happy, excited, thinking, surprised, sad, angry, sleepy
        """
        if not self._initialized or not self._model:
            return

        self._current_expression = emotion
        expression_name = self.expressions_map.get(emotion, "neutral")

        try:
            # Try to load expression file if available
            # Expressions are typically stored alongside the model
            if self.model_path:
                model_dir = os.path.dirname(self.model_path)
                exp_file = os.path.join(model_dir, f"{expression_name}.exp3.json")
                if os.path.exists(exp_file):
                    self._model.LoadExpression(exp_file)
                    logger.debug(f"Expression set: {emotion} -> {expression_name}")
                    return

            # Fallback: set parameters directly based on emotion
            self._set_expression_params(emotion)

        except Exception as e:
            logger.debug(f"Could not set expression '{emotion}': {e}")
            self._set_expression_params(emotion)

    def _set_expression_params(self, emotion: str) -> None:
        """Set expression via model parameters (fallback when no expression files)."""
        if not self._model:
            return

        # Map emotions to approximate parameter values
        # These are common Live2D parameter IDs
        param_mappings = {
            "neutral": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0, "ParamMouthOpenY": 0.0},
            "happy": {"ParamEyeLOpen": 1.0, "ParamEyeROpen": 0.8, "ParamMouthOpenY": 0.3, "ParamBrowLY": 0.8},
            "excited": {"ParamEyeLOpen": 1.2, "ParamEyeROpen": 1.2, "ParamMouthOpenY": 0.5, "ParamBrowLY": 1.0},
            "thinking": {"ParamEyeLOpen": 0.7, "ParamEyeROpen": 1.0, "ParamBrowLY": -0.5},
            "surprised": {"ParamEyeLOpen": 1.3, "ParamEyeROpen": 1.3, "ParamMouthOpenY": 0.7, "ParamBrowLY": 1.0},
            "sad": {"ParamEyeLOpen": 0.6, "ParamEyeROpen": 0.6, "ParamBrowLY": -0.8, "ParamMouthOpenY": 0.0},
            "angry": {"ParamEyeLOpen": 0.8, "ParamEyeROpen": 0.8, "ParamBrowLY": -1.0, "ParamMouthOpenY": 0.1},
            "sleepy": {"ParamEyeLOpen": 0.3, "ParamEyeROpen": 0.3, "ParamBrowLY": -0.5},
        }

        params = param_mappings.get(emotion, param_mappings["neutral"])
        for param_id, value in params.items():
            try:
                self._model.SetParameterFloat(param_id, value)
            except Exception:
                pass  # Parameter might not exist in this model

    def set_talking(self, talking: bool) -> None:
        """Set talking state for lip sync animation.
        
        Args:
            talking: True if avatar should animate mouth.
        """
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
            # Blink in progress
            if self._blink_timer >= self._blink_duration:
                self._is_blinking = False
                self._blink_timer = 0.0
                try:
                    self._model.SetParameterFloat("ParamEyeLOpen", 1.0)
                    self._model.SetParameterFloat("ParamEyeROpen", 1.0)
                except Exception:
                    pass
        elif self._blink_timer >= self._blink_interval:
            # Start blink
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
            # Simulate mouth movement with a sine wave
            import math
            import time
            t = time.time()
            # Vary mouth opening with multiple frequencies for natural look
            mouth = (math.sin(t * 12.0) * 0.3 +
                    math.sin(t * 7.5) * 0.2 +
                    math.sin(t * 18.0) * 0.1 + 0.4)
            mouth = max(0.0, min(1.0, mouth))
            self._mouth_value = mouth

            try:
                self._model.SetParameterFloat("ParamMouthOpenY", mouth)
            except Exception:
                pass
        else:
            if self._mouth_value > 0.01:
                self._mouth_value *= 0.8  # Smooth close
                try:
                    self._model.SetParameterFloat("ParamMouthOpenY", self._mouth_value)
                except Exception:
                    pass

    def drag(self, x: int, y: int) -> None:
        """Handle mouse drag for eye tracking."""
        if self._model:
            try:
                self._model.Drag(x, y)
            except Exception:
                pass

    def dispose(self) -> None:
        """Clean up Live2D resources."""
        if self._live2d:
            try:
                self._live2d.dispose()
            except Exception:
                pass
        self._model = None
        self._initialized = False
        logger.info("Live2D avatar disposed")

    @property
    def is_initialized(self) -> bool:
        """Check if avatar is initialized and ready."""
        return self._initialized

    @property
    def is_talking(self) -> bool:
        """Check if avatar is currently talking."""
        return self._is_talking
