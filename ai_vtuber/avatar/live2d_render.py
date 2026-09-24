"""AI VTuber - Live2D OpenGL rendering helpers.

Rendering-side support for :class:`ai_vtuber.avatar.live2d.Live2DAvatar`:

* per-frame model update (runtime ``Update`` + blink / lip-sync overrides),
* framebuffer clearing and model drawing with zoom / offset transforms,
* viewport resize and mouse-driven eye/head tracking (``drag``).

All functions take the avatar instance (duck-typed) and operate on its
rendering state attributes (``_model``, ``_live2d``, ``_initialized``,
``_offset_x/_offset_y``, ``_zoom``, ...).  They NEVER import live2d-py at
module level — the native module is only ever reached through the avatar's
already-imported ``_live2d`` handle, so importing this file stays safe on
machines without a GPU runtime.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resize_model(avatar: Any, width: int, height: int) -> None:
    """Resize the model viewport."""
    if avatar._model:
        try:
            avatar._model.Resize(width, height)
        except Exception as e:
            logger.error(f"Live2D resize failed: {e}")


def update_model(avatar: Any, delta_time: float) -> None:
    """Update model state."""
    if not avatar._initialized or not avatar._model:
        return
    try:
        avatar._model.Update()                  # recalc breathing/motion/physics first
        avatar._update_blink(delta_time)        # then apply our overrides
        avatar._update_lip_sync(delta_time)
    except Exception as e:
        logger.error(f"Live2D update error: {e}")


def draw_model(avatar: Any) -> None:
    """Draw the Live2D model with zoom and position transforms."""
    if not avatar._initialized or not avatar._model:
        return
    try:
        # FIX: Clear buffer before drawing to ensure correct background color compositing
        # Without this, LAppModel.Draw() renders against its own default white buffer
        avatar._live2d.clearBuffer()
        # Use live2d-py's native transform methods instead of OpenGL matrices
        # LAppModel.SetOffset(x, y) expects screen-space pixel coordinates
        # LAppModel.SetScale(scale) expects a multiplier (1.0 = normal size)
        avatar._model.SetOffset(avatar._offset_x, avatar._offset_y)
        avatar._model.SetScale(avatar._zoom)
        avatar._model.Draw()
    except Exception as e:
        logger.error(f"Live2D draw error: {e}")
        try:
            avatar._model.Draw()
        except Exception as e:
            logger.debug(f"Live2D fallback draw failed: {e}")


def drag_tracking(avatar: Any, x: int, y: int,
                  width: int = 0, height: int = 0) -> None:
    """Handle mouse movement for eye tracking - makes avatar look at cursor.

    Args:
        x: Mouse X position in screen coordinates
        y: Mouse Y position in screen coordinates
        width: OpenGL widget width (for normalization)
        height: OpenGL widget height (for normalization)
    """
    if not avatar._initialized or not avatar._model:
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
        avatar._model.SetParameterValue(avatar._param_eye_ball_x, norm_x * 0.8)
        avatar._model.SetParameterValue(avatar._param_eye_ball_y, norm_y * 0.8)

        # Set head angle for more natural looking
        # Angle values typically range from -30 to 30 degrees
        avatar._model.SetParameterValue(avatar._param_angle_x, norm_x * 20.0)
        avatar._model.SetParameterValue(avatar._param_angle_y, norm_y * 15.0)

    except Exception as e:
        logger.debug(f"Eye tracking error: {e}")
