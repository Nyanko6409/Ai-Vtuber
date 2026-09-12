"""AI VTuber - Live2D Avatar Module

Handles Live2D model loading, rendering, expressions, and animations.
CRITICAL: Checks Python/native compatibility BEFORE importing to prevent SIGSEGV.
"""

import logging
import math
import sys
import time
from pathlib import Path
from typing import Optional, Any

import numpy as np

logger = logging.getLogger(__name__)

# Emotion → expression file name mapping
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

# Emotion → parameter overrides
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


def _resolve_model_path(raw_path: str) -> Optional[Path]:
    """Resolve and validate a Live2D model path."""
    if not raw_path or not raw_path.strip():
        return None

    p = Path(raw_path).expanduser().resolve()

    if not p.exists():
        logger.error(f"Live2D model path does not exist: {p}")
        return None

    if not p.is_file():
        logger.error(f"Live2D model path is not a file: {p}")
        return None

    if p.suffix.lower() != ".json":
        logger.error(f"Live2D model must be a .json file, got: {p.suffix}")
        return None

    return p


class Live2DAvatar:
    """Live2D avatar using live2d-py library.
    
    CRITICAL: Checks Python/native compatibility BEFORE importing to prevent SIGSEGV.
    """

    def __init__(self, config: dict) -> None:
        self.model_path_raw: str = config.get("model_path", "")
        self.scale: float = config.get("scale", 2.0)
        self.expressions_map: dict[str, str] = {
            **DEFAULT_EXPRESSIONS,
            **config.get("expressions", {}),
        }

        self._live2d: Any = None
        self._live2d_version: int = 0
        self._model: Any = None

        self._is_talking: bool = False
        self._current_expression: str = "neutral"
        self._mouth_value: float = 0.0
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

        # CRITICAL: Check compatibility BEFORE importing
        self._safe_import_live2d()

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
            self._update_blink(delta_time)
            self._update_lip_sync(delta_time)
            self._model.Update()
        except Exception as e:
            logger.error(f"Live2D update error: {e}")

    def draw(self) -> None:
        """Draw the Live2D model with zoom and position transforms."""
        if not self._initialized or not self._model:
            return
        try:
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
            except Exception:
                pass

    def set_expression(self, emotion: str) -> None:
        """Set avatar expression based on emotion."""
        if not self._initialized or not self._model:
            return

        self._current_expression = emotion
        expression_name = self.expressions_map.get(emotion, "neutral")

        # Try loading expression file
        if self._model_path:
            model_dir = self._model_path.parent
            for search_dir in [model_dir, model_dir / "expressions", model_dir / "Exp"]:
                exp_file = search_dir / f"{expression_name}.exp3.json"
                if exp_file.exists():
                    try:
                        self._model.LoadExpression(str(exp_file))
                        logger.debug(f"Expression loaded: {exp_file}")
                        return
                    except Exception:
                        pass

        # Fallback: set parameters directly
        self._set_expression_params(emotion)

    def _set_expression_params(self, emotion: str) -> None:
        """Set expression via model parameters."""
        if not self._model:
            return
        params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["neutral"])
        for param_id, value in params.items():
            try:
                self._model.SetParameterValueById(param_id, value)
            except Exception:
                pass

    def set_talking(self, talking: bool) -> None:
        """Set talking state for lip sync."""
        self._is_talking = talking
        if not talking and self._model:
            self._mouth_value = 0.0
            try:
                self._model.SetParameterValueById("ParamMouthOpenY", 0.0)
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
                    self._model.SetParameterValueById("ParamEyeLOpen", 1.0)
                    self._model.SetParameterValueById("ParamEyeROpen", 1.0)
                except Exception:
                    pass
        elif self._blink_timer >= self._blink_interval:
            self._is_blinking = True
            self._blink_timer = 0.0
            try:
                self._model.SetParameterValueById("ParamEyeLOpen", 0.0)
                self._model.SetParameterValueById("ParamEyeROpen", 0.0)
            except Exception:
                pass

    def _update_lip_sync(self, delta_time: float) -> None:
        """Update lip sync animation driven by actual TTS audio amplitude."""
        if not self._model:
            return

        if self._is_talking and self._lipsync_audio is not None:
            elapsed = time.time() - self._lipsync_start
            offset = int(elapsed * self._lipsync_rate)
            offset = min(offset, len(self._lipsync_audio))
            chunk = self._lipsync_audio[self._lipsync_last_offset:offset]
            self._lipsync_last_offset = offset
            if len(chunk) > 0:
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                mouth = max(0.0, min(1.0, rms * 4.0))
                self._mouth_value = mouth
                try:
                    self._model.SetParameterValueById("ParamMouthOpenY", mouth)
                except Exception:
                    pass
        else:
            if self._mouth_value > 0.01:
                self._mouth_value *= 0.8
                try:
                    self._model.SetParameterValueById("ParamMouthOpenY", self._mouth_value)
                except Exception:
                    pass

    def start_lip_sync(self, audio_data: np.ndarray, sample_rate: int) -> None:
        """Begin real lip sync driven by actual TTS audio amplitude."""
        self._lipsync_audio = audio_data
        self._lipsync_rate = sample_rate
        self._lipsync_start = time.time()
        self._lipsync_last_offset = 0
        self._is_talking = True

    def drag(self, x: int, y: int) -> None:
        """Handle mouse drag for eye tracking."""
        if self._model:
            try:
                self._model.Drag(x, y)
            except Exception:
                pass

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
        logger.debug(f"Offset Y: {self._offset_y:.1f}")

    def move_down(self, amount: float = 10.0) -> None:
        """Move model down."""
        self._offset_y += amount
        logger.debug(f"Offset Y: {self._offset_y:.1f}")

    def move_left(self, amount: float = 10.0) -> None:
        """Move model left."""
        self._offset_x -= amount
        logger.debug(f"Offset X: {self._offset_x:.1f}")

    def move_right(self, amount: float = 10.0) -> None:
        """Move model right."""
        self._offset_x += amount
        logger.debug(f"Offset X: {self._offset_x:.1f}")

    def move_by(self, dx: float, dy: float) -> None:
        """Move model by delta x and y (for mouse dragging).
        
        SetOffset expects screen-space pixel coordinates.
        We apply a sensitivity factor to make dragging feel natural.
        """
        # Sensitivity factor: 0.01 = very slow/precise movement, 1.0 = 1:1 movement
        sensitivity = 0.01
        self._offset_x += dx * sensitivity
        self._offset_y += dy * sensitivity
        logger.debug(f"Offset X: {self._offset_x:.1f}, Y: {self._offset_y:.1f}")

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
            except Exception:
                pass
        self._model = None
        self._initialized = False
        self._gl_initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_talking(self) -> bool:
        return self._is_talking

    @property
    def error_message(self) -> Optional[str]:
        return self._error_message
